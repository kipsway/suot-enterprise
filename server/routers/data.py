"""Универсальный CRUD для JSON-таблиц с изоляцией данных по пользователю.

Администратор видит все записи; обычный пользователь — только свои.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from server.deps import get_db, get_current_user, is_admin
from services.database import DatabaseManager

router = APIRouter(prefix="/api", tags=["data"])

TABLE_LABELS_RU = {
    "employees": "Сотрудники",
    "violations": "Нарушения",
    "custom_ledger": "Реестр",
    "incidents": "Происшествия",
    "ppe": "СИЗ",
    "training": "Обучение",
    "permits": "Допуски",
    "work_orders": "Наряды",
    "ppe_inspections": "Осмотры СИЗ",
    "companies": "Компании",
}


class RecordIn(BaseModel):
    data: Dict[str, Any]


class BulkDeleteIn(BaseModel):
    ids: List[int]


def _table(name: str) -> str:
    if name not in DatabaseManager.JSON_TABLES:
        raise HTTPException(404, f"Неизвестная таблица: {name}")
    return name


def _owner_filter(user: dict) -> Optional[int]:
    """None → видеть всё (админ), иначе id владельца."""
    return None if is_admin(user) else int(user["id"])


def _out(row: dict) -> dict:
    return {
        "id": row["id"],
        "data": row.get("data_json") or {},
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "user_id": row.get("user_id", 0),
    }


def _get_raw_row(db: DatabaseManager, table: str, record_id: int) -> dict:
    r = db.fetch_one(f"SELECT id, user_id FROM {table} WHERE id=?", (record_id,))
    if not r:
        raise HTTPException(404, "Запись не найдена")
    return dict(r)


def _check_access(row: dict, user: dict) -> None:
    owner = int(row.get("user_id") or 0)
    if owner == 0 or owner == int(user["id"]) or is_admin(user):
        return
    raise HTTPException(403, "Нет доступа к чужой записи")


@router.get("/meta/tables")
def list_tables(user=Depends(get_current_user)):
    return {
        "tables": [
            {"key": k, "label_ru": v} for k, v in sorted(TABLE_LABELS_RU.items())
        ]
    }


@router.get("/meta/{table}")
def table_meta(table: str, db=Depends(get_db), user=Depends(get_current_user)):
    _table(table)
    cols = db.get_columns_config(table)
    return {
        "table": table,
        "label_ru": TABLE_LABELS_RU.get(table, table),
        "columns": [dict(c) for c in cols],
    }


@router.get("/data/{table}")
def list_records(
    table: str,
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
    _table(table)
    uid = _owner_filter(user)
    filters: Dict[str, List[str]] = {}
    for key, value in request.query_params.multi_items():
        if key.startswith("f_") and value:
            col = key[2:]
            filters[col] = [v for v in value.split(",") if v]
    rows, total = db.query_json_records(
        table,
        owner_id=uid,
        is_admin=is_admin(user),
        q=q.strip(),
        filters=filters,
        sort_by=sort_by,
        order=order,
        page=page,
        page_size=page_size,
        order_cast=order_cast,
        smart_filter=smart_filter,
    )
    return {
        "items": [_out(r) for r in rows],
        "total": total,
        "page": max(1, page),
        "page_size": page_size,
    }


@router.get("/data/{table}/values")
def column_values(
    table: str, col: str, db=Depends(get_db), user=Depends(get_current_user)
):
    _table(table)
    try:
        vals = db.distinct_column_values(
            table, col, _owner_filter(user), is_admin(user)
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"column": col, "values": vals}


@router.post("/data/{table}/bulk_delete")
def bulk_delete(
    table: str, body: BulkDeleteIn, db=Depends(get_db), user=Depends(get_current_user)
):
    _table(table)
    if not body.ids:
        raise HTTPException(400, "Список ids пуст")
    deleted = 0
    for rid in body.ids:
        try:
            raw = _get_raw_row(db, table, int(rid))
        except HTTPException:
            continue
        try:
            _check_access(raw, user)
        except HTTPException:
            continue
        if db.delete_json_record(table, int(rid)):
            deleted += 1
    return {"deleted": deleted}


@router.get("/me/counts")
def my_counts(db=Depends(get_db), user=Depends(get_current_user)):
    counts = db.count_records_for(int(user["id"]))
    try:
        counts.update(db.count_custom_for(int(user["id"])))
    except Exception:
        pass
    return {"counts": counts}


# ── Часть 5: дублирование, массовое редактирование, метки ──

COPY_SUFFIX = " (копия)"


@router.post("/data/{table}/{record_id}/duplicate", status_code=201)
def duplicate_record(
    table: str, record_id: int, db=Depends(get_db), user=Depends(get_current_user)
):
    _table(table)
    rec = db.get_json_record(table, record_id)
    if not rec:
        raise HTTPException(404, "Запись не найдена")
    raw = _get_raw_row(db, table, record_id)
    _check_access(raw, user)
    data = dict(rec.get("data_json") or {})
    # пометить копию в первом непустом текстовом поле
    cols = db.get_columns_config(table)
    text_names = [c["name"] for c in cols if c["type"] == "Текст" and c["name"] != "ID"]
    name_col = next((n for n in text_names if str(data.get(n, "") or "").strip()), None)
    if name_col is None and text_names:
        name_col = text_names[0]
    if name_col:
        base = str(data.get(name_col, "") or "")
        if COPY_SUFFIX not in base:
            data[name_col] = (base + COPY_SUFFIX).strip()
    new_id = db.save_json_record(table, 0, data, user_id=int(user["id"]))
    return {"id": new_id}


class BulkEditIn(BaseModel):
    ids: List[int]
    field: str
    value: str


@router.post("/data/{table}/bulk_edit")
def bulk_edit(
    table: str, body: BulkEditIn, db=Depends(get_db), user=Depends(get_current_user)
):
    _table(table)
    valid = {c["name"] for c in db.get_columns_config(table) if c["name"] != "ID"}
    if body.field not in valid:
        raise HTTPException(400, f"Неизвестная колонка: {body.field}")
    updated = 0
    for rid in body.ids:
        try:
            raw = _get_raw_row(db, table, int(rid))
            _check_access(raw, user)
        except HTTPException:
            continue
        rec = db.get_json_record(table, int(rid))
        if not rec:
            continue
        data = dict(rec.get("data_json") or {})
        data[body.field] = body.value
        db.save_json_record(table, int(rid), data, user_id=int(user["id"]))
        updated += 1
    return {"updated": updated}


ALLOWED_LABELS = {"", "red", "orange", "yellow", "green", "blue", "purple"}


class LabelIn(BaseModel):
    color: str = ""


@router.post("/data/{table}/{record_id}/label")
def set_label(
    table: str,
    record_id: int,
    body: LabelIn,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    _table(table)
    if body.color not in ALLOWED_LABELS:
        raise HTTPException(400, "Недопустимый цвет метки")
    raw = _get_raw_row(db, table, record_id)
    _check_access(raw, user)
    rec = db.get_json_record(table, record_id)
    data = dict(rec.get("data_json") or {})
    if body.color:
        data["_label"] = body.color
    else:
        data.pop("_label", None)
    db.save_json_record(table, record_id, data, user_id=int(user["id"]))
    return {"ok": True, "color": body.color}


@router.get("/data/{table}/duplicate_check")
def duplicate_check(
    table: str, request: Request, db=Depends(get_db), user=Depends(get_current_user)
):
    """Поиск похожей записи (violations: Дата+Фирма+Подразделение+Описание)."""
    _table(table)
    if table != "violations":
        return {"found": False}
    data = {k: v for k, v in request.query_params.items() if v}
    match = db.find_violation_duplicate(
        data, user_id=None if is_admin(user) else int(user["id"])
    )
    if match:
        return {
            "found": True,
            "id": match["id"],
            "preview": {
                k: str(match.get(k, ""))[:80] for k in ("Дата", "Фирма", "Описание")
            },
        }
    return {"found": False}


@router.get("/data/{table}/{record_id}")
def get_record(
    table: str, record_id: int, db=Depends(get_db), user=Depends(get_current_user)
):
    _table(table)
    rec = db.get_json_record(table, record_id)
    if not rec:
        raise HTTPException(404, "Запись не найдена")
    raw = _get_raw_row(db, table, record_id)
    _check_access(raw, user)
    return _out({**rec, "user_id": raw["user_id"]})


@router.post("/data/{table}", status_code=201)
def create_record(
    table: str, body: RecordIn, db=Depends(get_db), user=Depends(get_current_user)
):
    _table(table)
    try:
        new_id = db.save_json_record(table, 0, body.data, user_id=int(user["id"]))
    except ValueError as e:
        _map_save_error(e)
    return {"id": new_id}


@router.put("/data/{table}/{record_id}")
def update_record(
    table: str,
    record_id: int,
    body: RecordIn,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    _table(table)
    raw = _get_raw_row(db, table, record_id)
    _check_access(raw, user)
    try:
        db.save_json_record(table, record_id, body.data, user_id=int(user["id"]))
    except ValueError as e:
        _map_save_error(e)
    return {"id": record_id, "ok": True}


def _map_save_error(e: ValueError):
    msg = str(e)
    if msg == "DUPLICATE_COMPANY":
        raise HTTPException(409, "Компания с таким наименованием уже существует")
    if msg == "COMPANY_NAME_REQUIRED":
        raise HTTPException(400, "Укажите наименование компании")
    raise HTTPException(400, msg)


@router.delete("/data/{table}/{record_id}")
def delete_record(
    table: str, record_id: int, db=Depends(get_db), user=Depends(get_current_user)
):
    _table(table)
    raw = _get_raw_row(db, table, record_id)
    _check_access(raw, user)
    ok = db.delete_json_record(table, record_id)
    if not ok:
        raise HTTPException(500, "Не удалось удалить запись")
    return {"ok": True}
