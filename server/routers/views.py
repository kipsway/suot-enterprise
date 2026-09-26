"""Сохранённые виды таблиц (SUOT Next, Query Engine).

Виды хранятся на сервере (таблица user_views) с изоляцией по владельцу:
пользователь видит свои (+ общие user_id=0), администратор — все.
Клиент зеркалит в localStorage как оффлайн-кэш.
"""

import re
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from server.deps import get_db, get_current_user, is_admin
from services.database import DatabaseManager

router = APIRouter(prefix="/api/views", tags=["views"])

SCOPE_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
MAX_QUERY_BYTES = 8192


def _check_scope(scope: str) -> str:
    scope = (scope or "").strip()
    if not SCOPE_RE.match(scope):
        raise HTTPException(400, "Некорректный scope таблицы")
    return scope


def _check_name(name: str) -> str:
    name = (name or "").strip()
    if not name or len(name) > 80:
        raise HTTPException(400, "Имя вида: 1–80 символов")
    return name


def _check_query(query: Any) -> Dict[str, Any]:
    if not isinstance(query, dict):
        raise HTTPException(400, "query должен быть объектом")
    import json as _json

    raw = _json.dumps(query, ensure_ascii=False)
    if len(raw.encode("utf-8")) > MAX_QUERY_BYTES:
        raise HTTPException(400, "Вид слишком большой (макс. 8 КБ)")
    allowed = {
        "q",
        "filters",
        "smartFilter",
        "sortBy",
        "order",
        "density",
        "hidden",
        "hiddenUser",
        "page_size",
    }
    return {k: v for k, v in query.items() if k in allowed}


def _out(row: dict) -> dict:
    return {
        "id": row["id"],
        "scope": row["scope"],
        "name": row["name"],
        "query": row.get("query") or {},
        "user_id": row.get("user_id", 0),
    }


@router.get("")
def list_views(scope: str, db=Depends(get_db), user=Depends(get_current_user)):
    scope = _check_scope(scope)
    rows = db.list_views(scope, int(user["id"]), is_admin(user))
    return {"items": [_out(r) for r in rows]}


class ViewIn(BaseModel):
    scope: str
    name: str
    query: Dict[str, Any] = {}


@router.post("", status_code=201)
def create_view(body: ViewIn, db=Depends(get_db), user=Depends(get_current_user)):
    scope = _check_scope(body.scope)
    name = _check_name(body.name)
    query = _check_query(body.query)
    res = db.create_view(scope, name, query, int(user["id"]))
    return {"id": res["id"]}


class ViewUpdate(BaseModel):
    name: Optional[str] = None
    query: Optional[Dict[str, Any]] = None


@router.put("/{vid}")
def update_view(
    vid: int, body: ViewUpdate, db=Depends(get_db), user=Depends(get_current_user)
):
    name = _check_name(body.name) if body.name is not None else None
    query = _check_query(body.query) if body.query is not None else None
    if name is None and query is None:
        raise HTTPException(400, "Нечего обновлять")
    try:
        ok = db.update_view(vid, int(user["id"]), is_admin(user), name, query)
    except PermissionError:
        raise HTTPException(403, "Нет доступа к чужому виду")
    if not ok:
        raise HTTPException(404, "Вид не найден")
    return {"ok": True}


@router.delete("/{vid}")
def delete_view(vid: int, db=Depends(get_db), user=Depends(get_current_user)):
    try:
        ok = db.delete_view(vid, int(user["id"]), is_admin(user))
    except PermissionError:
        raise HTTPException(403, "Нет доступа к чужому виду")
    if not ok:
        raise HTTPException(404, "Вид не найден")
    return {"ok": True}
