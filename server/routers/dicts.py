"""Справочники: типы нарушений и шаблоны нарушений."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from server.deps import get_db, get_current_user, is_admin
from app_core.utils import JsonUtils

router = APIRouter(prefix="/api/dicts", tags=["dicts"])


class ViolationTypeIn(BaseModel):
    name: str
    risk_category: str = "Средняя"
    description: str = ""


def _only_admin(user):
    if not is_admin(user):
        raise HTTPException(403, "Только администратор может изменять справочники")


@router.get("/violation_types")
def list_types(db=Depends(get_db), user=Depends(get_current_user)):
    rows = db.fetch_all(
        "SELECT id, name, risk_category, description FROM violation_types ORDER BY name"
    )
    return {"items": [dict(r) for r in rows]}


@router.post("/violation_types", status_code=201)
def create_type(
    body: ViolationTypeIn, db=Depends(get_db), user=Depends(get_current_user)
):
    _only_admin(user)
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Укажите название типа")
    dup = db.fetch_one("SELECT id FROM violation_types WHERE name=?", (name,))
    if dup:
        raise HTTPException(409, "Такой тип уже существует")
    cur = db.execute(
        "INSERT INTO violation_types (name, risk_category, description) "
        "VALUES (?, ?, ?)",
        (name, body.risk_category, body.description),
    )
    db.commit()
    return {"id": int(cur.lastrowid)}


@router.put("/violation_types/{type_id}")
def update_type(
    type_id: int,
    body: ViolationTypeIn,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    _only_admin(user)
    exists = db.fetch_one("SELECT id FROM violation_types WHERE id=?", (type_id,))
    if not exists:
        raise HTTPException(404, "Тип не найден")
    name = body.name.strip()
    dup = db.fetch_one(
        "SELECT id FROM violation_types WHERE name=? AND id!=?", (name, type_id)
    )
    if dup:
        raise HTTPException(409, "Такой тип уже существует")
    db.execute(
        "UPDATE violation_types SET name=?, risk_category=?, description=? WHERE id=?",
        (name, body.risk_category, body.description, type_id),
    )
    db.commit()
    return {"ok": True}


@router.delete("/violation_types/{type_id}")
def delete_type(type_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    _only_admin(user)
    db.execute("DELETE FROM violation_types WHERE id=?", (type_id,))
    db.commit()
    return {"ok": True}


@router.get("/violation_templates")
def list_templates(db=Depends(get_db), user=Depends(get_current_user)):
    """Шаблоны нарушений (custom_templates): name + data_json."""
    rows = db.fetch_all(
        "SELECT id, name, data_json FROM custom_templates ORDER BY name"
    )
    items = []
    for r in rows:
        try:
            data = JsonUtils.loads(r["data_json"])
        except Exception:
            data = {}
        items.append({"id": r["id"], "name": r["name"], "data": data})
    return {"items": items}
