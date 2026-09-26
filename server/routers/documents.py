"""Documents Center (Блок 7): версии шаблонов печати, очередь печати,
сохранённые отчёты. Владелец — только свои объекты (админ — все)."""

import io
import json
import os
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app_core.config import RUNTIME_PATHS
from server.deps import get_db, get_current_user, is_admin
from server.routers.print_api import _template_owner, datetime_now
from server.routers.print_pdf import (
    _add_watermark,
    _html_to_pdf,
    _merge_pdfs,
    _render_record,
)
from services.database import DatabaseManager

router = APIRouter(prefix="/api/documents", tags=["documents"])

_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="suot-print")
_JOB_LOCK = threading.Lock()
_RUNNING = set()

MAX_JOB_RECORDS = 200
MAX_VERSIONS = 50


def _ensure(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS doc_template_versions ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, template_id INTEGER NOT NULL, "
        "version INTEGER NOT NULL, name TEXT DEFAULT '', html_content TEXT DEFAULT '', "
        "page_size TEXT DEFAULT 'A4', orientation TEXT DEFAULT 'portrait', "
        "margins TEXT DEFAULT '20mm', created_by INTEGER DEFAULT 0, "
        "created_at TEXT DEFAULT '')"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS print_jobs ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER DEFAULT 0, "
        "name TEXT DEFAULT '', template_id INTEGER DEFAULT 0, table_name TEXT DEFAULT '', "
        "record_ids_json TEXT DEFAULT '[]', watermark TEXT DEFAULT '', merge INTEGER DEFAULT 1, "
        "page_size TEXT DEFAULT 'A4', orientation TEXT DEFAULT 'portrait', "
        "margins TEXT DEFAULT '15mm', status TEXT DEFAULT 'queued', "
        "done INTEGER DEFAULT 0, total INTEGER DEFAULT 0, "
        "result_path TEXT DEFAULT '', result_kind TEXT DEFAULT '', "
        "error TEXT DEFAULT '', created_at TEXT DEFAULT '', updated_at TEXT DEFAULT '')"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS saved_reports ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER DEFAULT 0, "
        "name TEXT DEFAULT '', table_name TEXT DEFAULT '', spec_json TEXT DEFAULT '{}', "
        "created_at TEXT DEFAULT '', updated_at TEXT DEFAULT '')"
    )
    db.commit()


def _job_owner(db, jid: int, user: dict) -> Dict[str, Any]:
    row = db.fetch_one("SELECT * FROM print_jobs WHERE id=?", (jid,))
    if not row:
        raise HTTPException(404, "Задание не найдено")
    d = dict(row)
    if int(d.get("user_id") or 0) != int(user["id"]) and not is_admin(user):
        raise HTTPException(403, "Нет доступа к заданию")
    return d


def _report_owner(db, rid: int, user: dict) -> Dict[str, Any]:
    row = db.fetch_one("SELECT * FROM saved_reports WHERE id=?", (rid,))
    if not row:
        raise HTTPException(404, "Отчёт не найден")
    d = dict(row)
    if int(d.get("user_id") or 0) != int(user["id"]) and not is_admin(user):
        raise HTTPException(403, "Нет доступа к отчёту")
    return d


def _job_dir(jid: int) -> str:
    base = os.path.join(str(RUNTIME_PATHS.export_dir), "print_jobs")
    os.makedirs(base, exist_ok=True)
    d = os.path.join(base, f"job_{jid}")
    os.makedirs(d, exist_ok=True)
    return d


def _set_job(db, jid: int, **kw):
    kw["updated_at"] = datetime_now()
    cols = ", ".join(f"{k}=?" for k in kw)
    db.execute(f"UPDATE print_jobs SET {cols} WHERE id=?", (*kw.values(), jid))
    db.commit()


def recover_pending_print_jobs(db) -> int:
    """Сброс зависших running в queued + перезапуск (как jobs.recover_pending)."""
    try:
        _ensure(db)
    except Exception:
        return 0
    rows = db.fetch_all("SELECT id FROM print_jobs WHERE status='running'")
    n = 0
    for r in rows:
        try:
            _set_job(db, r["id"], status="queued")
            _submit(int(r["id"]))
            n += 1
        except Exception:
            continue
    return n


def purge_old_print_jobs(db, keep_days: int = 30, keep_last: int = 20) -> int:
    """Ретеншн результатов: история заданий хранится, файлы — нет.
    Чистим файлы старше keep_days и сверх keep_last свежих на пользователя."""
    import shutil

    try:
        _ensure(db)
    except Exception:
        return 0
    try:
        cutoff = (datetime.now() - timedelta(days=keep_days)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    except Exception:
        return 0
    rows = db.fetch_all(
        "SELECT id, user_id, result_path, updated_at FROM print_jobs "
        "WHERE result_path<>'' ORDER BY user_id, id DESC"
    )
    seen: Dict[int, int] = {}
    purged = 0
    for r in rows:
        d = dict(r)
        uid = int(d.get("user_id") or 0)
        seen[uid] = seen.get(uid, 0) + 1
        old = str(d.get("updated_at") or "") < cutoff
        if not old and seen[uid] <= keep_last:
            continue
        path = d.get("result_path") or ""
        try:
            if path and os.path.isfile(path):
                os.remove(path)
            parent = os.path.dirname(path)
            if parent and os.path.isdir(parent) and not os.listdir(parent):
                shutil.rmtree(parent, ignore_errors=True)
        except Exception:
            pass
        try:
            db.execute(
                "UPDATE print_jobs SET result_path='', result_kind='' WHERE id=?",
                (d["id"],),
            )
            purged += 1
        except Exception:
            continue
    try:
        db.commit()
    except Exception:
        pass
    return purged


# ═══ Версии шаблонов ═══


@router.get("/templates/{tid}/versions")
def list_versions(tid: int, db=Depends(get_db), user=Depends(get_current_user)):
    _ensure(db)
    _template_owner(db, tid, user)
    rows = db.fetch_all(
        "SELECT id, template_id, version, name, page_size, orientation, "
        "created_by, created_at FROM doc_template_versions "
        "WHERE template_id=? ORDER BY version DESC",
        (tid,),
    )
    return {"items": [dict(r) for r in rows]}


@router.get("/templates/{tid}/versions/{vid}")
def get_version(tid: int, vid: int, db=Depends(get_db), user=Depends(get_current_user)):
    _ensure(db)
    _template_owner(db, tid, user)
    row = db.fetch_one(
        "SELECT * FROM doc_template_versions WHERE id=? AND template_id=?",
        (vid, tid),
    )
    if not row:
        raise HTTPException(404, "Версия не найдена")
    return {"version": dict(row)}


class RestoreIn(BaseModel):
    version_id: int


@router.post("/templates/{tid}/restore", status_code=200)
def restore_version(
    tid: int, body: RestoreIn, db=Depends(get_db), user=Depends(get_current_user)
):
    """Откат шаблона к версии: текущий контент тоже сохраняется как версия."""
    from server.routers import print_api as _pa

    _ensure(db)
    tpl = _template_owner(db, tid, user)
    if int(tpl.get("created_by") or 0) != int(user["id"]) and not is_admin(user):
        raise HTTPException(403, "Только автор или админ может откатывать")
    row = db.fetch_one(
        "SELECT * FROM doc_template_versions WHERE id=? AND template_id=?",
        (body.version_id, tid),
    )
    if not row:
        raise HTTPException(404, "Версия не найдена")
    v = dict(row)
    _pa.snapshot_version(db, tid, int(user["id"]))
    db.execute(
        "UPDATE print_templates SET html_content=?, page_size=?, orientation=?, "
        "margins=?, updated_at=? WHERE id=?",
        (
            v["html_content"],
            v["page_size"],
            v["orientation"],
            v["margins"],
            datetime_now(),
            tid,
        ),
    )
    db.commit()
    return {"ok": True, "restored_version": v["version"]}


# ═══ Очередь печати ═══


class PrintJobIn(BaseModel):
    name: str = ""
    template_id: int
    table: str
    record_ids: List[int] = []
    watermark_text: str = ""
    merge: bool = True
    page_size: str = "A4"
    orientation: str = "portrait"
    margins: str = "15mm"


def _resolve_records(db, table: str, record_ids: List[int], uid: int, admin: bool):
    if table not in DatabaseManager.JSON_TABLES:
        raise HTTPException(404, "Неизвестная таблица")
    rows: List[Dict[str, Any]] = []
    if record_ids:
        for rid in record_ids[:MAX_JOB_RECORDS]:
            if not db.user_can_access(table, rid, uid, admin):
                continue
            rec = db.get_json_record(table, rid)
            if rec:
                rows.append(rec)
    else:
        rows = db.query_json_records(
            table,
            None if admin else uid,
            is_admin=admin,
            page_size=MAX_JOB_RECORDS,
        )[0]
    return rows


def _run_print_job(jid: int):
    """Воркер печати: DatabaseManager — синглтон, как в jobs.py."""
    from services.database import DatabaseManager as _DM

    db = _DM()
    try:
        job = dict(db.fetch_one("SELECT * FROM print_jobs WHERE id=?", (jid,)))
    except Exception:
        return
    _set_job(db, jid, status="running", done=0, error="")
    try:
        tpl = dict(
            db.fetch_one(
                "SELECT * FROM print_templates WHERE id=?", (job["template_id"],)
            )
        )
    except Exception:
        tpl = None
    if not tpl:
        _set_job(db, jid, status="error", error="Шаблон удалён")
        return
    uid = int(job["user_id"] or 0)
    try:
        admin_row = db.fetch_one("SELECT is_admin FROM users WHERE id=?", (uid,))
        admin = bool(admin_row and admin_row["is_admin"])
    except Exception:
        admin = False
    try:
        ids = json.loads(job.get("record_ids_json") or "[]")
    except (json.JSONDecodeError, TypeError):
        ids = []
    try:
        rows = _resolve_records(db, job["table_name"], ids, uid, admin)
    except HTTPException as e:
        _set_job(db, jid, status="error", error=e.detail)
        return
    if not rows:
        _set_job(db, jid, status="error", error="Нет записей для печати")
        return
    _set_job(db, jid, total=len(rows))
    outdir = _job_dir(jid)
    pdfs: List[str] = []
    cancelled = False
    for i, row in enumerate(rows):
        st = db.fetch_one("SELECT status FROM print_jobs WHERE id=?", (jid,))
        if not st or st["status"] != "running":
            cancelled = True
            break
        data = row.get("data_json") or {}
        data["username"] = ""
        html = _render_record(tpl.get("html_content") or "", dict(data))
        if job.get("watermark"):
            html = _add_watermark(html, text=job["watermark"])
        out = os.path.join(outdir, f"doc_{i:04d}.pdf")
        if _html_to_pdf(
            html,
            out,
            job.get("page_size") or "A4",
            job.get("orientation") or "portrait",
            job.get("margins") or "15mm",
        ):
            pdfs.append(out)
        _set_job(db, jid, done=len(pdfs))
    if cancelled:
        _set_job(db, jid, status="canceled")
        return
    if not pdfs:
        _set_job(
            db,
            jid,
            status="error",
            error="PDF не сгенерирован (Edge/Chromium недоступен?)",
        )
        return
    merge = bool(job.get("merge"))
    if len(pdfs) == 1 or not merge:
        if len(pdfs) == 1 and merge:
            final = os.path.join(outdir, "result.pdf")
            os.replace(pdfs[0], final)
            _set_job(db, jid, status="done", result_path=final, result_kind="pdf")
        else:
            zpath = os.path.join(outdir, "result.zip")
            with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
                for pf in pdfs:
                    zf.write(pf, os.path.basename(pf))
            _set_job(db, jid, status="done", result_path=zpath, result_kind="zip")
    else:
        merged = _merge_pdfs(pdfs)
        final = os.path.join(outdir, "result.pdf")
        with open(final, "wb") as f:
            f.write(merged)
        _set_job(db, jid, status="done", result_path=final, result_kind="pdf")


def _submit(jid: int):
    with _JOB_LOCK:
        if jid in _RUNNING:
            return
        _RUNNING.add(jid)

    def _wrap():
        try:
            _run_print_job(jid)
        finally:
            with _JOB_LOCK:
                _RUNNING.discard(jid)

    _POOL.submit(_wrap)


@router.post("/print/jobs", status_code=202)
def create_job(body: PrintJobIn, db=Depends(get_db), user=Depends(get_current_user)):
    _ensure(db)
    tpl = _template_owner(db, body.template_id, user)
    uid = int(user["id"])
    admin = is_admin(user)
    rows = _resolve_records(db, body.table, body.record_ids, uid, admin)
    if not rows:
        raise HTTPException(404, "Нет записей для печати")
    now = datetime_now()
    cur = db.execute(
        "INSERT INTO print_jobs (user_id, name, template_id, table_name, "
        "record_ids_json, watermark, merge, page_size, orientation, margins, "
        "status, done, total, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 0, ?, ?, ?)",
        (
            uid,
            body.name.strip() or tpl.get("name", ""),
            body.template_id,
            body.table,
            json.dumps([r["id"] for r in rows[:MAX_JOB_RECORDS]]),
            body.watermark_text,
            1 if body.merge else 0,
            body.page_size,
            body.orientation,
            body.margins,
            min(len(rows), MAX_JOB_RECORDS),
            now,
            now,
        ),
    )
    db.commit()
    jid = int(cur.lastrowid)
    _submit(jid)
    return {"job_id": jid, "status": "queued", "total": min(len(rows), MAX_JOB_RECORDS)}


@router.get("/print/jobs")
def list_jobs(db=Depends(get_db), user=Depends(get_current_user)):
    _ensure(db)
    if is_admin(user):
        rows = db.fetch_all(
            "SELECT j.*, u.username FROM print_jobs j "
            "LEFT JOIN users u ON u.id=j.user_id ORDER BY j.id DESC LIMIT 200"
        )
    else:
        rows = db.fetch_all(
            "SELECT j.*, u.username FROM print_jobs j "
            "LEFT JOIN users u ON u.id=j.user_id WHERE j.user_id=? "
            "ORDER BY j.id DESC LIMIT 200",
            (int(user["id"]),),
        )
    items = []
    for r in rows:
        d = dict(r)
        d.pop("result_path", None)
        items.append(d)
    return {"items": items}


@router.get("/print/jobs/{jid}")
def job_status(jid: int, db=Depends(get_db), user=Depends(get_current_user)):
    _ensure(db)
    d = _job_owner(db, jid, user)
    d.pop("result_path", None)
    return {"job": d}


@router.post("/print/jobs/{jid}/cancel")
def cancel_job(jid: int, db=Depends(get_db), user=Depends(get_current_user)):
    _ensure(db)
    d = _job_owner(db, jid, user)
    if d["status"] in ("done", "error", "canceled"):
        return {"ok": True, "status": d["status"]}
    _set_job(db, jid, status="canceled")
    return {"ok": True, "status": "canceled"}


@router.post("/print/jobs/{jid}/retry")
def retry_job(jid: int, db=Depends(get_db), user=Depends(get_current_user)):
    _ensure(db)
    d = _job_owner(db, jid, user)
    if d["status"] not in ("done", "error", "canceled"):
        raise HTTPException(409, "Задание ещё выполняется")
    _set_job(db, jid, status="queued", done=0, error="", result_path="", result_kind="")
    _submit(jid)
    return {"job_id": jid, "status": "queued"}


def _job_file(db, jid: int, user: dict):
    d = _job_owner(db, jid, user)
    if d["status"] != "done" or not d.get("result_path"):
        raise HTTPException(409, "Результат ещё не готов")
    path = d["result_path"]
    if not os.path.isfile(path):
        raise HTTPException(410, "Файл результата удалён")
    return d, path


@router.get("/print/jobs/{jid}/download")
def download_job(jid: int, db=Depends(get_db), user=Depends(get_current_user)):
    _ensure(db)
    d, path = _job_file(db, jid, user)
    with open(path, "rb") as f:
        data = f.read()
    kind = d.get("result_kind") or "pdf"
    return Response(
        data,
        media_type="application/pdf" if kind == "pdf" else "application/zip",
        headers={"Content-Disposition": f"attachment; filename=print_job_{jid}.{kind}"},
    )


@router.get("/print/jobs/{jid}/preview")
def preview_job(jid: int, db=Depends(get_db), user=Depends(get_current_user)):
    """Байты PDF для предпросмотра в iframe (только одиночный PDF)."""
    _ensure(db)
    d, path = _job_file(db, jid, user)
    if (d.get("result_kind") or "pdf") != "pdf":
        raise HTTPException(409, "Предпросмотр доступен только для одиночного PDF")
    with open(path, "rb") as f:
        data = f.read()
    return Response(data, media_type="application/pdf")


# ═══ Сохранённые отчёты ═══


class SavedReportIn(BaseModel):
    name: str
    table: str
    columns: List[str] = []
    filters: Dict[str, List[str]] = {}
    group_by: str = ""
    aggregate: str = "count"
    aggregate_field: str = ""
    q: str = ""


def _spec_of(body: SavedReportIn) -> Dict[str, Any]:
    return {
        "table": body.table,
        "columns": body.columns,
        "filters": body.filters,
        "group_by": body.group_by,
        "aggregate": body.aggregate,
        "aggregate_field": body.aggregate_field,
        "q": body.q,
    }


@router.get("/reports/saved")
def list_saved(db=Depends(get_db), user=Depends(get_current_user)):
    _ensure(db)
    if is_admin(user):
        rows = db.fetch_all(
            "SELECT s.*, u.username FROM saved_reports s "
            "LEFT JOIN users u ON u.id=s.user_id ORDER BY s.updated_at DESC"
        )
    else:
        rows = db.fetch_all(
            "SELECT s.*, u.username FROM saved_reports s "
            "LEFT JOIN users u ON u.id=s.user_id WHERE s.user_id=? "
            "ORDER BY s.updated_at DESC",
            (int(user["id"]),),
        )
    return {"items": [dict(r) for r in rows]}


@router.post("/reports/saved", status_code=201)
def create_saved(
    body: SavedReportIn, db=Depends(get_db), user=Depends(get_current_user)
):
    _ensure(db)
    if not body.name.strip():
        raise HTTPException(400, "Укажите название")
    if body.table not in DatabaseManager.JSON_TABLES:
        raise HTTPException(404, "Неизвестная таблица")
    now = datetime_now()
    cur = db.execute(
        "INSERT INTO saved_reports (user_id, name, table_name, spec_json, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            int(user["id"]),
            body.name.strip(),
            body.table,
            json.dumps(_spec_of(body), ensure_ascii=False),
            now,
            now,
        ),
    )
    db.commit()
    return {"id": int(cur.lastrowid)}


@router.put("/reports/saved/{rid}")
def update_saved(
    rid: int, body: SavedReportIn, db=Depends(get_db), user=Depends(get_current_user)
):
    _ensure(db)
    d = _report_owner(db, rid, user)
    if int(d.get("user_id") or 0) != int(user["id"]) and not is_admin(user):
        raise HTTPException(403, "Только автор или админ может редактировать")
    if body.table not in DatabaseManager.JSON_TABLES:
        raise HTTPException(404, "Неизвестная таблица")
    db.execute(
        "UPDATE saved_reports SET name=?, table_name=?, spec_json=?, "
        "updated_at=? WHERE id=?",
        (
            body.name.strip(),
            body.table,
            json.dumps(_spec_of(body), ensure_ascii=False),
            datetime_now(),
            rid,
        ),
    )
    db.commit()
    return {"ok": True}


@router.delete("/reports/saved/{rid}")
def delete_saved(rid: int, db=Depends(get_db), user=Depends(get_current_user)):
    _ensure(db)
    d = _report_owner(db, rid, user)
    if int(d.get("user_id") or 0) != int(user["id"]) and not is_admin(user):
        raise HTTPException(403, "Только автор или админ может удалить")
    db.execute("DELETE FROM saved_reports WHERE id=?", (rid,))
    db.commit()
    return {"ok": True}


@router.post("/reports/saved/{rid}/run")
def run_saved(rid: int, db=Depends(get_db), user=Depends(get_current_user)):
    from server.routers.search_reports import ReportIn, run_report

    _ensure(db)
    d = _report_owner(db, rid, user)
    try:
        spec = json.loads(d.get("spec_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(422, "Спека отчёта повреждена")
    body = ReportIn(
        table=spec.get("table") or d.get("table_name") or "",
        columns=spec.get("columns") or [],
        filters=spec.get("filters") or {},
        group_by=spec.get("group_by") or "",
        aggregate=spec.get("aggregate") or "count",
        aggregate_field=spec.get("aggregate_field") or "",
        q=spec.get("q") or "",
    )
    return run_report(body, db=db, user=user)


@router.get("/tables")
def doc_tables(user=Depends(get_current_user)):
    """JSON-таблицы, доступные для печати и отчётов."""
    return {"items": sorted(DatabaseManager.JSON_TABLES)}
