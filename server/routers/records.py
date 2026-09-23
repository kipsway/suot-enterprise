"""Запись-уровень: заметки, связи между записями, история изменений."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from server.deps import get_db, get_current_user, is_admin
from services.database import DatabaseManager

router = APIRouter(prefix="/api/record", tags=["record"])


def _access(db: DatabaseManager, table: str, record_id: int, user: dict) -> None:
    """Проверка доступа к записи (владелец / админ / общая)."""
    if table not in DatabaseManager.JSON_TABLES:
        raise HTTPException(404, f"Неизвестная таблица: {table}")
    owner = db.record_owner_id(table, record_id)
    if owner is None:
        raise HTTPException(404, "Запись не найдена")
    if owner != 0 and owner != int(user["id"]) and not is_admin(user):
        raise HTTPException(403, "Нет доступа к записи")


class NoteIn(BaseModel):
    title: str = ""
    content: str = ""


class LinkIn(BaseModel):
    target_table: str
    target_id: int
    link_type: str = "related"


# ── Заметки ──


@router.get("/{table}/{record_id}/notes")
def notes_list(
    table: str, record_id: int, db=Depends(get_db), user=Depends(get_current_user)
):
    _access(db, table, record_id, user)
    rows = db.get_notes(table, record_id)
    return {"items": [dict(r) for r in rows]}


@router.post("/{table}/{record_id}/notes", status_code=201)
def note_add(
    table: str,
    record_id: int,
    body: NoteIn,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    _access(db, table, record_id, user)
    if not body.content.strip() and not body.title.strip():
        raise HTTPException(400, "Пустая заметка")
    nid = db.save_note(table, record_id, body.title, body.content)
    return {"id": nid}


@router.delete("/notes/{note_id}")
def note_del(note_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    # IDOR-фикс (аудит 7.2 п.5): заметку можно удалить, только если есть
    # доступ к записи, к которой она привязана.
    note = db.fetch_one(
        "SELECT entity_type, entity_id FROM notes WHERE id=?", (note_id,)
    )
    if not note:
        raise HTTPException(404, "Заметка не найдена")
    if note["entity_type"] != "global":
        _access(db, note["entity_type"], int(note["entity_id"] or 0), user)
    ok = db.delete_note(note_id)
    if not ok:
        raise HTTPException(404, "Заметка не найдена")
    return {"ok": True}


# ── Связи ──


@router.get("/{table}/{record_id}/links")
def links_list(
    table: str, record_id: int, db=Depends(get_db), user=Depends(get_current_user)
):
    _access(db, table, record_id, user)
    links = db.get_record_links(table, record_id)
    items = []
    for l in links:
        d = dict(l)
        # человекочитаемое имя связанной записи
        d["target_name"] = db.get_linked_record_name(d["target_table"], d["target_id"])
        items.append(d)
    return {"items": items}


@router.post("/{table}/{record_id}/links", status_code=201)
def link_add(
    table: str,
    record_id: int,
    body: LinkIn,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    _access(db, table, record_id, user)
    if body.target_table not in DatabaseManager.JSON_TABLES:
        raise HTTPException(400, "Неверная целевая таблица")
    # IDOR-фикс (аудит 7.2 п.5): целевая запись тоже должна быть доступна.
    _access(db, body.target_table, body.target_id, user)
    dup = db.fetch_one(
        "SELECT id FROM record_links WHERE source_table=? AND source_id=? "
        "AND target_table=? AND target_id=?",
        (table, record_id, body.target_table, body.target_id),
    )
    if dup:
        raise HTTPException(409, "Такая связь уже есть")
    ok = db.add_record_link(
        table, record_id, body.target_table, body.target_id, body.link_type
    )
    if not ok:
        raise HTTPException(500, "Не удалось создать связь")
    return {"ok": True}


@router.delete("/links/{link_id}")
def link_del(link_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    # IDOR-фикс (аудит 7.2 п.5): связь можно удалить, только если есть
    # доступ к записи-источнику.
    link = db.fetch_one(
        "SELECT source_table, source_id FROM record_links WHERE id=?", (link_id,)
    )
    if not link:
        raise HTTPException(404, "Связь не найдена")
    _access(db, link["source_table"], int(link["source_id"]), user)
    ok = db.remove_record_link(link_id)
    if not ok:
        raise HTTPException(404, "Связь не найдена")
    return {"ok": True}


# ── История изменений ──


@router.get("/{table}/{record_id}/history")
def history(
    table: str,
    record_id: int,
    limit: int = 100,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    _access(db, table, record_id, user)
    rows = db.fetch_all(
        "SELECT id, field, old_value, new_value, username, created_at "
        "FROM change_history WHERE table_name=? AND record_id=? "
        "ORDER BY id DESC LIMIT ?",
        (table, record_id, limit),
    )
    return {"items": [dict(r) for r in rows]}


@router.post("/{table}/{record_id}/history/{history_id}/rollback")
def history_rollback(
    table: str,
    record_id: int,
    history_id: int,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    _access(db, table, record_id, user)
    h = db.fetch_one(
        "SELECT * FROM change_history WHERE id=? AND table_name=? AND record_id=?",
        (history_id, table, record_id),
    )
    if not h:
        raise HTTPException(404, "Запись истории не найдена")
    ok = db.rollback_change(history_id)
    if not ok:
        raise HTTPException(500, "Не удалось откатить изменение")
    return {"ok": True}
