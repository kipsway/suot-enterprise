"""Редактор печати: шаблоны, переменные, предпросмотр, копирование, экспорт/импорт."""

import html as _html
import json
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from server.deps import get_db, get_current_user, is_admin
from services.database import DatabaseManager
from app_core.utils import JsonUtils

router = APIRouter(prefix="/api/print", tags=["print"])


def _template_owner(db, tid: int, user: dict) -> Dict[str, Any]:
    row = db.fetch_one("SELECT * FROM print_templates WHERE id=?", (tid,))
    if not row:
        raise HTTPException(404, "Шаблон не найден")
    d = dict(row)
    if (
        d.get("created_by")
        and int(d["created_by"]) != int(user["id"])
        and not is_admin(user)
        and not d.get("is_public")
    ):
        raise HTTPException(403, "Нет доступа к шаблону")
    return d


class TemplateIn(BaseModel):
    name: str
    category: str = ""
    html_content: str = ""
    page_size: str = "A4"
    orientation: str = "portrait"
    margins: str = "20mm"
    is_public: bool = False


def _ensure_cols(db):
    cols = {r["name"] for r in db.fetch_all("PRAGMA table_info(print_templates)")}
    if "category" not in cols:
        db.execute("ALTER TABLE print_templates ADD COLUMN category TEXT DEFAULT ''")
    if "page_size" not in cols:
        db.execute("ALTER TABLE print_templates ADD COLUMN page_size TEXT DEFAULT 'A4'")
    if "orientation" not in cols:
        db.execute(
            "ALTER TABLE print_templates ADD COLUMN orientation TEXT DEFAULT 'portrait'"
        )
    if "margins" not in cols:
        db.execute("ALTER TABLE print_templates ADD COLUMN margins TEXT DEFAULT '20mm'")
    if "is_public" not in cols:
        db.execute("ALTER TABLE print_templates ADD COLUMN is_public INTEGER DEFAULT 0")
    if "created_by" not in cols:
        db.execute(
            "ALTER TABLE print_templates ADD COLUMN created_by INTEGER DEFAULT 0"
        )
    if "updated_at" not in cols:
        db.execute("ALTER TABLE print_templates ADD COLUMN updated_at TEXT DEFAULT ''")
    db.commit()


@router.get("/templates")
def list_templates(db=Depends(get_db), user=Depends(get_current_user)):
    _ensure_cols(db)
    uid = int(user["id"])
    rows = db.fetch_all(
        "SELECT id, name, category, page_size, orientation, is_public, "
        "created_by, updated_at FROM print_templates "
        "WHERE created_by=? OR created_by=0 OR is_public=1 "
        "ORDER BY updated_at DESC, id DESC",
        (uid,),
    )
    return {"items": [dict(r) for r in rows]}


@router.get("/templates/{tid}")
def get_template(tid: int, db=Depends(get_db), user=Depends(get_current_user)):
    _ensure_cols(db)
    d = _template_owner(db, tid, user)
    return {"template": d}


@router.post("/templates", status_code=201)
def create_template(
    body: TemplateIn, db=Depends(get_db), user=Depends(get_current_user)
):
    _ensure_cols(db)
    if not body.name.strip():
        raise HTTPException(400, "Укажите название")
    now = datetime_now()
    cur = db.execute(
        "INSERT INTO print_templates (name, category, html_content, "
        "page_size, orientation, margins, is_public, created_by, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            body.name.strip(),
            body.category,
            body.html_content,
            body.page_size,
            body.orientation,
            body.margins,
            1 if body.is_public else 0,
            int(user["id"]),
            now,
        ),
    )
    db.commit()
    return {"id": int(cur.lastrowid)}


@router.put("/templates/{tid}")
def update_template(
    tid: int, body: TemplateIn, db=Depends(get_db), user=Depends(get_current_user)
):
    _ensure_cols(db)
    d = _template_owner(db, tid, user)
    if int(d.get("created_by") or 0) != int(user["id"]) and not is_admin(user):
        raise HTTPException(403, "Только автор или админ может редактировать")
    db.execute(
        "UPDATE print_templates SET name=?, category=?, html_content=?, "
        "page_size=?, orientation=?, margins=?, is_public=?, updated_at=? "
        "WHERE id=?",
        (
            body.name.strip(),
            body.category,
            body.html_content,
            body.page_size,
            body.orientation,
            body.margins,
            1 if body.is_public else 0,
            datetime_now(),
            tid,
        ),
    )
    db.commit()
    return {"ok": True}


@router.delete("/templates/{tid}")
def delete_template(tid: int, db=Depends(get_db), user=Depends(get_current_user)):
    _ensure_cols(db)
    d = _template_owner(db, tid, user)
    if int(d.get("created_by") or 0) != int(user["id"]) and not is_admin(user):
        raise HTTPException(403, "Только автор или админ может удалить")
    db.execute("DELETE FROM print_templates WHERE id=?", (tid,))
    db.commit()
    return {"ok": True}


@router.post("/templates/{tid}/copy", status_code=201)
def copy_template(tid: int, db=Depends(get_db), user=Depends(get_current_user)):
    _ensure_cols(db)
    src = _template_owner(db, tid, user)
    now = datetime_now()
    cur = db.execute(
        "INSERT INTO print_templates (name, category, html_content, "
        "page_size, orientation, margins, is_public, created_by, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)",
        (
            src["name"] + " (копия)",
            src.get("category", ""),
            src["html_content"],
            src.get("page_size", "A4"),
            src.get("orientation", "portrait"),
            src.get("margins", "20mm"),
            int(user["id"]),
            now,
        ),
    )
    db.commit()
    return {"id": int(cur.lastrowid)}


# ── Экспорт/импорт шаблона как JSON-файла (предложение 3) ──


@router.get("/templates/{tid}/export")
def export_template(tid: int, db=Depends(get_db), user=Depends(get_current_user)):
    d = _template_owner(db, tid, user)
    data = {
        "name": d["name"],
        "category": d.get("category", ""),
        "html_content": d["html_content"],
        "page_size": d.get("page_size", "A4"),
        "orientation": d.get("orientation", "portrait"),
        "margins": d.get("margins", "20mm"),
        "_export": "suot_template_v1",
    }
    return data


class ImportTplIn(BaseModel):
    name: str
    category: str = ""
    html_content: str
    page_size: str = "A4"
    orientation: str = "portrait"
    margins: str = "20mm"


@router.post("/import_template", status_code=201)
def import_template(
    body: ImportTplIn, db=Depends(get_db), user=Depends(get_current_user)
):
    _ensure_cols(db)
    now = datetime_now()
    cur = db.execute(
        "INSERT INTO print_templates (name, category, html_content, "
        "page_size, orientation, margins, is_public, created_by, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)",
        (
            body.name,
            body.category,
            body.html_content,
            body.page_size,
            body.orientation,
            body.margins,
            int(user["id"]),
            now,
        ),
    )
    db.commit()
    return {"id": int(cur.lastrowid)}


# ── Переменные ──


@router.get("/variables/{table}")
def variables(table: str, db=Depends(get_db), user=Depends(get_current_user)):
    if table not in DatabaseManager.JSON_TABLES:
        raise HTTPException(404, "Неизвестная таблица")
    cols = db.get_columns_config(table)
    sys_vars = [
        {"key": f"{{{c['name']}}}", "name": c["name"], "group": "Поля записи"}
        for c in cols
        if c["name"] != "ID"
    ]
    common = [
        {"key": "{today}", "name": "Дата печати", "group": "Общие"},
        {"key": "{username}", "name": "Пользователь", "group": "Общие"},
        {"key": "{app_name}", "name": "Название приложения", "group": "Общие"},
    ]
    return {"items": sys_vars + common}


# ── Предпросмотр с данными ──


class PreviewIn(BaseModel):
    html_content: str
    table: str
    record_id: int = 0


@router.post("/preview")
def preview(body: PreviewIn, db=Depends(get_db), user=Depends(get_current_user)):
    uid = int(user["id"])
    admin = is_admin(user)
    data: Dict[str, Any] = {}
    if body.record_id:
        # IDOR-фикс (аудит 7.2 п.3): предпросмотр только своих записей.
        if not db.user_can_access(body.table, body.record_id, uid, admin):
            raise HTTPException(403, "Нет доступа к записи")
        if body.table in DatabaseManager.JSON_TABLES:
            rec = db.get_json_record(body.table, body.record_id)
            if rec:
                data = rec.get("data_json") or {}
        else:
            rec = db.get_custom_record(body.table, body.record_id)
            if rec:
                data = rec.get("data_json") or {}
    data["today"] = datetime_now()[:10]
    data["username"] = user["username"]
    data["app_name"] = "СУОТ Enterprise"
    html = body.html_content
    for k, v in data.items():
        # Значения записей — произвольный ввод пользователей: экранируем,
        # иначе Stored-XSS в предпросмотре (рендерится через x-html).
        html = html.replace("{" + k + "}", _html.escape(str(v or ""), quote=False))
    import re

    html = re.sub(r"\{[^}]+\}", "—", html)
    return {"html": html}


def datetime_now() -> str:
    from datetime import datetime as dt

    return dt.now().strftime("%Y-%m-%d %H:%M:%S")
