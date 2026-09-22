"""Пользовательские колонки для системных таблиц (личные, per-user)."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from server.deps import get_db, get_current_user, is_admin
from services.database import DatabaseManager
from app_core.utils import JsonUtils

router = APIRouter(prefix="/api/ucols", tags=["ucols"])

ALLOWED_TYPES = {
    "Текст",
    "Число",
    "Дата",
    "Годен до",
    "Дата проведения",
    "Статус",
    "Чекбокс",
    "Деньги",
    "Вычисляемая",
}


def _table_ok(table: str) -> None:
    if table.startswith("u_") or table not in DatabaseManager.JSON_TABLES:
        raise HTTPException(404, "Колонки поддерживаются для системных таблиц")


def _sys_names(db: DatabaseManager, table: str) -> set:
    return {c["name"] for c in db.get_columns_config(table)}


class ColIn(BaseModel):
    name: str
    type: str = "Текст"
    template: str = ""


class ColPatch(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    template: Optional[str] = None
    visible: Optional[bool] = None


@router.get("/{table}")
def list_cols(table: str, db=Depends(get_db), user=Depends(get_current_user)):
    _table_ok(table)
    rows = db.fetch_all(
        "SELECT id, name, type, template, position, visible FROM user_columns "
        "WHERE table_key=? AND user_id=? ORDER BY position, id",
        (table, int(user["id"])),
    )
    return {"items": [dict(r) for r in rows]}


@router.post("/{table}", status_code=201)
def add_col(
    table: str, body: ColIn, db=Depends(get_db), user=Depends(get_current_user)
):
    _table_ok(table)
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Укажите название колонки")
    if body.type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Тип не поддерживается: {body.type}")
    if body.type == "Вычисляемая" and "{" not in (body.template or ""):
        raise HTTPException(400, "Для вычисляемой колонки укажите шаблон с {Колонка}")
    if name in _sys_names(db, table):
        raise HTTPException(409, "Колонка с таким именем уже есть в таблице")
    dup = db.fetch_one(
        "SELECT id FROM user_columns WHERE table_key=? AND user_id=? AND name=?",
        (table, int(user["id"]), name),
    )
    if dup:
        raise HTTPException(409, "У вас уже есть колонка с таким именем")
    pos = db.fetch_one(
        "SELECT COALESCE(MAX(position), 0) AS p FROM user_columns "
        "WHERE table_key=? AND user_id=?",
        (table, int(user["id"])),
    )["p"]
    cur = db.execute(
        "INSERT INTO user_columns (table_key, name, type, template, "
        "position, user_id) VALUES (?, ?, ?, ?, ?, ?)",
        (table, name, body.type, body.template or "", int(pos) + 1, int(user["id"])),
    )
    db.commit()
    return {"id": int(cur.lastrowid)}


@router.put("/{table}/{col_id}")
def patch_col(
    table: str,
    col_id: int,
    body: ColPatch,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    _table_ok(table)
    row = db.fetch_one(
        "SELECT * FROM user_columns WHERE id=? AND table_key=? AND user_id=?",
        (col_id, table, int(user["id"])),
    )
    if not row:
        raise HTTPException(404, "Колонка не найдена")
    name = body.name.strip() if body.name is not None else row["name"]
    if body.name is not None and name != row["name"]:
        if name in _sys_names(db, table):
            raise HTTPException(409, "Имя занято системной колонкой")
        dup = db.fetch_one(
            "SELECT id FROM user_columns WHERE table_key=? AND user_id=? "
            "AND name=? AND id!=?",
            (table, int(user["id"]), name, col_id),
        )
        if dup:
            raise HTTPException(409, "У вас уже есть такая колонка")
    ctype = body.type if body.type is not None else row["type"]
    if ctype not in ALLOWED_TYPES:
        raise HTTPException(400, "Тип не поддерживается")
    template = body.template if body.template is not None else row["template"]
    visible = 1 if (body.visible if body.visible is not None else row["visible"]) else 0
    db.execute(
        "UPDATE user_columns SET name=?, type=?, template=?, visible=? WHERE id=?",
        (name, ctype, template or "", visible, col_id),
    )
    db.commit()
    return {"ok": True}


@router.delete("/{table}/{col_id}")
def del_col(
    table: str, col_id: int, db=Depends(get_db), user=Depends(get_current_user)
):
    _table_ok(table)
    row = db.fetch_one(
        "SELECT name FROM user_columns WHERE id=? AND table_key=? AND user_id=?",
        (col_id, table, int(user["id"])),
    )
    if not row:
        raise HTTPException(404, "Колонка не найдена")
    db.execute("DELETE FROM user_columns WHERE id=?", (col_id,))
    db.commit()
    return {"ok": True, "note": "значения в записях сохранены, но скрыты"}


@router.post("/{table}/{col_id}/duplicate", status_code=201)
def dup_col(
    table: str,
    col_id: int,
    body: ColIn,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """Дублирование колонки: определение + КОПИЯ ДАННЫХ из исходной."""
    _table_ok(table)
    src = db.fetch_one(
        "SELECT * FROM user_columns WHERE id=? AND table_key=? AND user_id=?",
        (col_id, table, int(user["id"])),
    )
    if not src:
        raise HTTPException(404, "Колонка не найдена")
    new_name = body.name.strip()
    if not new_name:
        raise HTTPException(400, "Укажите имя копии")
    if new_name in _sys_names(db, table):
        raise HTTPException(409, "Имя занято системной колонкой")
    dup = db.fetch_one(
        "SELECT id FROM user_columns WHERE table_key=? AND user_id=? AND name=?",
        (table, int(user["id"]), new_name),
    )
    if dup:
        raise HTTPException(409, "У вас уже есть такая колонка")

    pos = db.fetch_one(
        "SELECT COALESCE(MAX(position), 0) AS p FROM user_columns "
        "WHERE table_key=? AND user_id=?",
        (table, int(user["id"])),
    )["p"]
    cur = db.execute(
        "INSERT INTO user_columns (table_key, name, type, template, "
        "position, user_id) VALUES (?, ?, ?, ?, ?, ?)",
        (
            table,
            new_name,
            src["type"],
            src["template"] or "",
            int(pos) + 1,
            int(user["id"]),
        ),
    )
    new_id = int(cur.lastrowid)

    # копия данных (только записи пользователя)
    if src["type"] != "Вычисляемая":
        uid = int(user["id"])
        scope = "1=1" if is_admin(user) else "(user_id=? OR user_id=0)"
        rows = db.fetch_all(f"SELECT id, data_json FROM {table} WHERE {scope}", (uid,))
        for r in rows:
            try:
                data = JsonUtils.loads(r["data_json"] or "{}")
                if not isinstance(data, dict):
                    continue
            except Exception:
                continue
            if src["name"] in data:
                data[new_name] = data[src["name"]]
                db.execute(
                    f"UPDATE {table} SET data_json=? WHERE id=?",
                    (JsonUtils.dumps(data), r["id"]),
                )
        db.commit()
    return {"id": new_id}
