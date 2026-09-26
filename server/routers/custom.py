"""Пользовательские таблицы: реестр, корзина (30 дней), записи, перенос."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from server.deps import get_db, get_current_user, is_admin
from services.database import DatabaseManager
from app_core.utils import JsonUtils

router = APIRouter(prefix="/api/custom", tags=["custom"])

ALLOWED_TYPES = {
    "Текст",
    "Число",
    "Дата",
    "Годен до",
    "Дата проведения",
    "Статус",
    "Чекбокс",
    "Деньги",
}


def _tbl(db: DatabaseManager, key: str, user: dict) -> Dict[str, Any]:
    t = db.get_custom_table(key)
    if not t:
        raise HTTPException(404, "Таблица не найдена")
    owner = int(t["user_id"] or 0)
    if owner != 0 and owner != int(user["id"]) and not is_admin(user):
        raise HTTPException(403, "Нет доступа к таблице")
    return t


def _check_rec(db: DatabaseManager, key: str, rid: int, user: dict) -> None:
    _tbl(db, key, user)
    r = db.fetch_one(
        "SELECT user_id FROM custom_records WHERE id=? AND table_key=?", (rid, key)
    )
    if not r:
        raise HTTPException(404, "Запись не найдена")
    owner = int(r["user_id"] or 0)
    if owner != 0 and owner != int(user["id"]) and not is_admin(user):
        raise HTTPException(403, "Нет доступа к записи")


class TableIn(BaseModel):
    label: str
    icon: str = "database"
    color: str = "#6366F1"
    columns: List[Dict[str, Any]] = []


class ColumnsIn(BaseModel):
    columns: List[Dict[str, Any]]


class RecordIn(BaseModel):
    data: Dict[str, Any]


class BulkIn(BaseModel):
    ids: List[int]


class BulkEditIn(BaseModel):
    ids: List[int]
    field: str
    value: str


class LabelIn(BaseModel):
    color: str = ""


class TransferIn(BaseModel):
    from_key: str
    to_key: str
    ids: List[int]
    move: bool = True


# ═══ Реестр таблиц ═══


@router.get("/tables")
def tables_list(db=Depends(get_db), user=Depends(get_current_user)):
    items = db.get_custom_tables(int(user["id"]), is_admin(user))
    for t in items:
        try:
            t["columns"] = JsonUtils.loads(t.pop("columns_json") or "[]")
        except Exception:
            t["columns"] = []
    return {"items": items}


@router.post("/tables", status_code=201)
def table_create(body: TableIn, db=Depends(get_db), user=Depends(get_current_user)):
    if not body.label.strip():
        raise HTTPException(400, "Укажите название")
    cols = []
    for c in body.columns:
        name = str(c.get("name", "")).strip()
        if not name or name == "ID":
            continue
        ctype = c.get("type", "Текст")
        if ctype not in ALLOWED_TYPES:
            ctype = "Текст"
        cols.append({"name": name, "type": ctype, "visible": True})
    res = db.create_custom_table(
        body.label.strip(), body.icon, body.color, cols, int(user["id"])
    )
    db.log_event(f"Custom table created: {res['key']}", "INFO", {"label": body.label})
    return res


@router.put("/tables/{key}")
def table_update(
    key: str, body: TableIn, db=Depends(get_db), user=Depends(get_current_user)
):
    t = _tbl(db, key, user)
    cols = []
    for c in body.columns:
        name = str(c.get("name", "")).strip()
        if not name or name == "ID":
            continue
        ctype = c.get("type", "Текст")
        if ctype not in ALLOWED_TYPES:
            ctype = "Текст"
        cols.append({"name": name, "type": ctype, "visible": True})
    db.update_custom_table(
        int(t["id"]), body.label.strip(), body.icon, body.color, cols
    )
    return {"ok": True}


@router.delete("/tables/{key}")
def table_trash(key: str, db=Depends(get_db), user=Depends(get_current_user)):
    t = _tbl(db, key, user)
    db.soft_delete_custom_table(int(t["id"]))
    return {"ok": True}


@router.get("/trash")
def trash_list(db=Depends(get_db), user=Depends(get_current_user)):
    where, params = _own_sql_like(user)
    rows = db.fetch_all(
        f"SELECT id, key, label, icon, color, deleted_at FROM custom_tables "
        f"WHERE deleted_at != '' AND {where} ORDER BY deleted_at DESC",
        tuple(params),
    )
    return {"items": [dict(r) for r in rows]}


def _own_sql_like(user: dict):
    if is_admin(user):
        return "1=1", []
    return "(user_id=? OR user_id=0)", [int(user["id"])]


@router.post("/tables/{key}/restore")
def table_restore(key: str, db=Depends(get_db), user=Depends(get_current_user)):
    t = _tbl(db, key, user)
    db.restore_custom_table(int(t["id"]))
    return {"ok": True}


@router.delete("/tables/{key}/purge")
def table_purge(key: str, db=Depends(get_db), user=Depends(get_current_user)):
    t = _tbl(db, key, user)
    db.purge_custom_table(int(t["id"]))
    return {"ok": True}


# ═══ Записи (тот же контракт, что /api/data) ═══


@router.get("/meta/{key}")
def meta(key: str, db=Depends(get_db), user=Depends(get_current_user)):
    t = _tbl(db, key, user)
    try:
        cols = JsonUtils.loads(t["columns_json"] or "[]")
    except Exception:
        cols = []
    return {
        "table": key,
        "label": t["label"],
        "icon": t["icon"],
        "color": t["color"],
        "columns": [dict(c) for c in cols],
    }


@router.get("/records/{key}")
def rec_list(
    key: str,
    request: Request,
    page: int = 1,
    page_size: int = 50,
    q: str = "",
    sort_by: str = "",
    order: str = "asc",
    order_cast: str = "",
    smart_filter: str = "",
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    _tbl(db, key, user)
    filters: Dict[str, List[str]] = {}
    for k, v in request.query_params.multi_items():
        if k.startswith("f_") and v:
            filters[k[2:]] = [x for x in v.split(",") if x]
    rows, total = db.query_custom_records(
        key,
        int(user["id"]),
        is_admin(user),
        q=q.strip(),
        filters=filters,
        sort_by=sort_by,
        order=order,
        page=page,
        page_size=page_size,
        order_cast=order_cast,
        smart_filter=smart_filter.strip(),
    )
    items = [
        {
            "id": r["id"],
            "data": r.get("data_json") or {},
            "created_at": r.get("created_at"),
            "updated_at": r.get("updated_at"),
            "user_id": r.get("user_id", 0),
        }
        for r in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/values/{key}")
def rec_values(key: str, col: str, db=Depends(get_db), user=Depends(get_current_user)):
    _tbl(db, key, user)
    allowed = {c.get("name") for c in db.custom_columns(key) if c.get("name")}
    if col not in allowed:
        raise HTTPException(400, f"Неизвестная колонка: {col}")
    where, params = _own_sql_like(user)
    rows = db.fetch_all(
        f"SELECT DISTINCT json_extract(data_json, '$.\"{col}\"') AS v "
        f"FROM custom_records WHERE table_key=? AND {where} AND "
        f"data_json != '{{}}' LIMIT 300",
        (key, *params),
    )
    out = sorted(
        {
            str(r["v"]).strip()
            for r in rows
            if r["v"] is not None and str(r["v"]).strip()
        }
    )
    return {"column": col, "values": out[:300]}


@router.get("/record/{key}/{rid}")
def rec_get(key: str, rid: int, db=Depends(get_db), user=Depends(get_current_user)):
    _check_rec(db, key, rid, user)
    rec = db.get_custom_record(key, rid)
    return {
        "id": rec["id"],
        "data": rec.get("data_json") or {},
        "created_at": rec.get("created_at"),
        "updated_at": rec.get("updated_at"),
    }


@router.post("/records/{key}", status_code=201)
def rec_create(
    key: str, body: RecordIn, db=Depends(get_db), user=Depends(get_current_user)
):
    _tbl(db, key, user)
    return {"id": db.save_custom_record(key, 0, body.data, int(user["id"]))}


@router.put("/records/{key}/{rid}")
def rec_update(
    key: str,
    rid: int,
    body: RecordIn,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    _check_rec(db, key, rid, user)
    db.save_custom_record(key, rid, body.data, int(user["id"]))
    return {"id": rid, "ok": True}


@router.delete("/records/{key}/{rid}")
def rec_delete(key: str, rid: int, db=Depends(get_db), user=Depends(get_current_user)):
    _check_rec(db, key, rid, user)
    db.delete_custom_record(key, rid)
    return {"ok": True}


@router.post("/bulk_delete/{key}")
def rec_bulk_delete(
    key: str, body: BulkIn, db=Depends(get_db), user=Depends(get_current_user)
):
    _tbl(db, key, user)
    deleted = 0
    for rid in body.ids:
        try:
            _check_rec(db, key, int(rid), user)
            db.delete_custom_record(key, int(rid))
            deleted += 1
        except HTTPException:
            continue
    return {"deleted": deleted}


class BulkEditIn2(BulkEditIn):
    pass


@router.post("/bulk_edit/{key}")
def rec_bulk_edit(
    key: str, body: BulkEditIn, db=Depends(get_db), user=Depends(get_current_user)
):
    t = _tbl(db, key, user)
    try:
        cols = JsonUtils.loads(t["columns_json"] or "[]")
    except Exception:
        cols = []
    valid = {c.get("name") for c in cols} - {"ID"}
    if body.field not in valid:
        raise HTTPException(400, f"Неизвестная колонка: {body.field}")
    updated = 0
    for rid in body.ids:
        try:
            _check_rec(db, key, int(rid), user)
            rec = db.get_custom_record(key, int(rid))
            data = dict(rec.get("data_json") or {})
            data[body.field] = body.value
            db.save_custom_record(key, int(rid), data, int(user["id"]))
            updated += 1
        except HTTPException:
            continue
    return {"updated": updated}


@router.post("/duplicate/{key}/{rid}", status_code=201)
def rec_duplicate(
    key: str, rid: int, db=Depends(get_db), user=Depends(get_current_user)
):
    _check_rec(db, key, rid, user)
    rec = db.get_custom_record(key, rid)
    data = dict(rec.get("data_json") or {})
    cols = db.custom_columns(key)
    text_names = [c.get("name") for c in cols if c.get("type") == "Текст"]
    name_col = next((n for n in text_names if str(data.get(n, "") or "").strip()), None)
    if name_col is None and text_names:
        name_col = text_names[0]
    if name_col:
        base = str(data.get(name_col, "") or "")
        if "(копия)" not in base:
            data[name_col] = (base + " (копия)").strip()
    return {"id": db.save_custom_record(key, 0, data, int(user["id"]))}


@router.post("/label/{key}/{rid}")
def rec_label(
    key: str,
    rid: int,
    body: LabelIn,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    _check_rec(db, key, rid, user)
    rec = db.get_custom_record(key, rid)
    data = dict(rec.get("data_json") or {})
    if body.color:
        data["_label"] = body.color
    else:
        data.pop("_label", None)
    db.save_custom_record(key, rid, data, int(user["id"]))
    return {"ok": True, "color": body.color}


# ═══ Перенос записей между таблицами ═══


@router.post("/transfer")
def transfer(body: TransferIn, db=Depends(get_db), user=Depends(get_current_user)):
    if body.from_key == body.to_key:
        raise HTTPException(400, "Источник и приёмник совпадают")
    src_custom = body.from_key.startswith("u_")
    dst_custom = body.to_key.startswith("u_")
    if src_custom:
        _tbl(db, body.from_key, user)
    else:
        if body.from_key not in DatabaseManager.JSON_TABLES:
            raise HTTPException(404, "Исходная таблица не найдена")
    if dst_custom:
        dst_t = _tbl(db, body.to_key, user)
        try:
            dst_cols = {
                c.get("name") for c in JsonUtils.loads(dst_t["columns_json"] or "[]")
            }
        except Exception:
            dst_cols = set()
    else:
        if body.to_key not in DatabaseManager.JSON_TABLES:
            raise HTTPException(404, "Целевая таблица не найдена")
        dst_cols = {c["name"] for c in db.get_columns_config(body.to_key)} - {"ID"}

    moved = 0
    for rid in body.ids:
        rid = int(rid)
        if src_custom:
            try:
                _check_rec(db, body.from_key, rid, user)
            except HTTPException:
                continue
            rec = db.get_custom_record(body.from_key, rid)
            src_data = dict(rec.get("data_json") or {})
        else:
            # IDOR-фикс (аудит 7.2 п.4): из системной таблицы переносятся
            # только свои/общие записи.
            if not db.user_can_access(
                body.from_key, rid, int(user["id"]), is_admin(user)
            ):
                continue
            rec = db.get_json_record(body.from_key, rid)
            if not rec:
                continue
            src_data = dict(rec.get("data_json") or {})
        filtered = {
            k: v for k, v in src_data.items() if k in dst_cols and not k.startswith("_")
        }
        if not filtered:
            continue
        if dst_custom:
            db.save_custom_record(body.to_key, 0, filtered, int(user["id"]))
        else:
            db.save_json_record(body.to_key, 0, filtered, int(user["id"]))
        moved += 1
        if body.move:
            if src_custom:
                db.delete_custom_record(body.from_key, rid)
            else:
                row = db.fetch_one(
                    f"SELECT user_id FROM {body.from_key} WHERE id=?", (rid,)
                )
                owner = int(row["user_id"] or 0) if row else 0
                if owner in (0, int(user["id"])) or is_admin(user):
                    db.delete_json_record(body.from_key, rid)
    return {"moved": moved}
