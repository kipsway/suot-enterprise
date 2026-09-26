"""Серверные задачи массовых операций.

Задания выполняются в фоне и хранятся в памяти процесса. Это не меняет
существующие CRUD endpoints и изоляцию данных: перед каждым действием
повторно проверяется владелец записи и текущего пользователя.
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Any, Dict, List
from uuid import uuid4
import json, time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import io, csv

from server.deps import get_current_user, get_db, is_admin
from server.routers import data as data_router
from server.routers import custom as custom_router

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="suot-bulk")
_LOCK = Lock()
_JOBS: Dict[str, Dict[str, Any]] = {}


class BulkJobIn(BaseModel):
    kind: str
    target: str
    ids: List[int]
    field: str = ""
    value: str = ""


def _job(job_id: str, db=None) -> Dict[str, Any]:
    with _LOCK:
        item = _JOBS.get(job_id)
    if item:
        return item
    if db is not None:
        row = db.fetch_one("SELECT * FROM bulk_jobs WHERE id=?", (job_id,))
        if row:
            item = _hydrate(row)
            with _LOCK:
                _JOBS[job_id] = item
            return item
    raise HTTPException(404, "Задача не найдена")


def _cancelled(item: Dict[str, Any]) -> bool:
    with _LOCK:
        return bool(item["cancel_requested"])


def _persist(db, item: Dict[str, Any]) -> None:
    db.execute(
        "UPDATE bulk_jobs SET status=?, done=?, total=?, result_json=?, error=?, "
        "processed_ids_json=?, cancel_requested=?, started_at=?, finished_at=? WHERE id=?",
        (
            item.get("status", "queued"),
            int(item.get("done", 0)),
            int(item.get("total", 0)),
            json.dumps(item.get("result", {}), ensure_ascii=False),
            item.get("error", ""),
            json.dumps(item.get("processed_ids", []), ensure_ascii=False),
            1 if item.get("cancel_requested") else 0,
            item.get("started_at"),
            item.get("finished_at"),
            item["id"],
        ),
    )
    db.commit()


def recover_pending(db) -> int:
    rows = db.fetch_all("SELECT * FROM bulk_jobs WHERE status IN ('queued','running')")
    for row in rows:
        item = _hydrate(row)
        item["status"] = "queued"
        item["done"] = 0
        _set(item, db, status="queued", done=0)
        user = db.fetch_one("SELECT * FROM users WHERE id=?", (item["user_id"],))
        if user:
            _POOL.submit(_run, item, db, dict(user))
    return len(rows)


def _hydrate(row: dict) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "target": row["target"],
        "ids": json.loads(row.get("ids_json") or "[]"),
        "field": row.get("field", ""),
        "value": row.get("value", ""),
        "user_id": int(row["user_id"]),
        "processed_ids": json.loads(row.get("processed_ids_json") or "[]"),
        "status": row["status"],
        "done": int(row.get("done", 0)),
        "total": int(row.get("total", 0)),
        "result": json.loads(row.get("result_json") or "{}"),
        "error": row.get("error", ""),
        "cancel_requested": bool(row.get("cancel_requested")),
        "created_at": row.get("created_at"),
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
    }


def _set(item: Dict[str, Any], db=None, **values: Any) -> None:
    with _LOCK:
        item.update(values)
    if db is not None:
        _persist(db, item)


def _run(item: Dict[str, Any], db, user: dict) -> None:
    try:
        kind, target, ids = item["kind"], item["target"], item["ids"]
        done, result = 0, {}
        processed = set(item.get("processed_ids", []))
        pending = [rid for rid in ids if int(rid) not in processed]
        item["total"] = len(pending)
        _set(item, db, status="running", started_at=__import__("time").time())
        for rid in pending:
            if _cancelled(item):
                _set(
                    item,
                    db,
                    status="cancelled",
                    done=done,
                    finished_at=__import__("time").time(),
                )
                return
            if kind == "delete":
                if (
                    data_router._table(target)
                    not in data_router.DatabaseManager.JSON_TABLES
                ):
                    raise ValueError("unknown table")
                try:
                    raw = data_router._get_raw_row(db, target, int(rid))
                    data_router._check_access(raw, user)
                    if db.delete_json_record(target, int(rid)):
                        result["deleted"] = result.get("deleted", 0) + 1
                except Exception:
                    pass
            elif kind == "edit":
                valid = {
                    c["name"]
                    for c in db.get_columns_config(target)
                    if c["name"] != "ID"
                }
                if item["field"] not in valid:
                    raise ValueError("unknown field")
                try:
                    raw = data_router._get_raw_row(db, target, int(rid))
                    data_router._check_access(raw, user)
                    rec = db.get_json_record(target, int(rid))
                    data = dict(rec.get("data_json") or {})
                    data[item["field"]] = item["value"]
                    db.save_json_record(target, int(rid), data, user_id=int(user["id"]))
                    result["updated"] = result.get("updated", 0) + 1
                except Exception:
                    pass
            elif kind == "custom_delete":
                custom_router._check_rec(db, target, int(rid), user)
                db.delete_custom_record(target, int(rid))
                result["deleted"] = result.get("deleted", 0) + 1
            elif kind == "custom_edit":
                cols = __import__(
                    "app_core.utils", fromlist=["JsonUtils"]
                ).JsonUtils.loads(
                    custom_router._tbl(db, target, user)["columns_json"] or "[]"
                )
                if item["field"] not in {c.get("name") for c in cols} - {"ID"}:
                    raise ValueError("unknown field")
                custom_router._check_rec(db, target, int(rid), user)
                rec = db.get_custom_record(target, int(rid))
                data = dict(rec.get("data_json") or {})
                data[item["field"]] = item["value"]
                db.save_custom_record(target, int(rid), data, int(user["id"]))
                result["updated"] = result.get("updated", 0) + 1
            else:
                raise ValueError("unknown job kind")
            done += 1
            processed.add(int(rid))
            _set(item, db, done=done, processed_ids=list(processed))
        _set(
            item,
            db,
            status="completed",
            done=done,
            result=result,
            finished_at=__import__("time").time(),
        )
    except Exception as exc:
        _set(
            item,
            db,
            status="failed",
            error=str(exc),
            finished_at=__import__("time").time(),
        )


def _history_row(row: dict) -> dict:
    start, finish = row.get("started_at"), row.get("finished_at")
    duration = (
        round(
            max(
                0,
                (finish or time.time())
                - (start or row.get("created_at") or time.time()),
            ),
            3,
        )
        if (start or row.get("created_at"))
        else 0
    )
    return {
        "id": row["id"],
        "status": row["status"],
        "kind": row["kind"],
        "target": row["target"],
        "done": int(row.get("done", 0)),
        "total": int(row.get("total", 0)),
        "result": json.loads(row.get("result_json") or "{}"),
        "error": row.get("error", ""),
        "created_at": row.get("created_at"),
        "started_at": start,
        "finished_at": finish,
        "duration": duration,
        "username": row.get("username", ""),
    }


@router.get("/history")
def job_history(limit: int = 100, db=Depends(get_db), user=Depends(get_current_user)):
    limit = min(500, max(1, int(limit)))
    if is_admin(user):
        rows = db.fetch_all(
            "SELECT j.*, u.username FROM bulk_jobs j LEFT JOIN users u ON u.id=j.user_id "
            "ORDER BY j.created_at DESC LIMIT ?",
            (limit,),
        )
    else:
        rows = db.fetch_all(
            "SELECT j.*, u.username FROM bulk_jobs j LEFT JOIN users u ON u.id=j.user_id "
            "WHERE j.user_id=? ORDER BY j.created_at DESC LIMIT ?",
            (int(user["id"]), limit),
        )
    return {"items": [_history_row(r) for r in rows]}


@router.get("/export.csv")
def export_history(db=Depends(get_db), user=Depends(get_current_user)):
    if is_admin(user):
        rows = db.fetch_all(
            "SELECT j.*, u.username FROM bulk_jobs j LEFT JOIN users u ON u.id=j.user_id ORDER BY j.created_at DESC"
        )
    else:
        rows = db.fetch_all(
            "SELECT j.*, u.username FROM bulk_jobs j LEFT JOIN users u ON u.id=j.user_id WHERE j.user_id=? ORDER BY j.created_at DESC",
            (int(user["id"]),),
        )
    out = io.StringIO()
    out.write("\ufeff")
    writer = csv.writer(out, delimiter=";")
    writer.writerow(
        [
            "Дата",
            "Пользователь",
            "Операция",
            "Таблица",
            "Статус",
            "Готово",
            "Всего",
            "Ошибка",
            "Длительность, с",
        ]
    )
    for row in rows:
        x = _history_row(row)
        writer.writerow(
            [
                time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(x["created_at"] or time.time())
                ),
                x["username"],
                x["kind"],
                x["target"],
                x["status"],
                x["done"],
                x["total"],
                x["error"],
                x["duration"],
            ]
        )
    return StreamingResponse(
        iter([out.getvalue().encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=suot-bulk-jobs.csv"},
    )


@router.post("/bulk", status_code=202)
def create_bulk_job(
    body: BulkJobIn, db=Depends(get_db), user=Depends(get_current_user)
):
    if body.kind not in {"delete", "edit", "custom_delete", "custom_edit"}:
        raise HTTPException(400, "Неизвестный тип задачи")
    if not body.ids:
        raise HTTPException(400, "Список ids пуст")
    # Ранняя валидация цели: иначе задача молча упадёт в failed на первой записи.
    try:
        if body.kind in {"delete", "edit"}:
            data_router._table(body.target)
        else:
            custom_router._tbl(db, body.target, user)
    except HTTPException as e:
        if e.status_code == 404:
            raise HTTPException(400, f"Неверная цель: {e.detail}")
        raise
    job_id = uuid4().hex
    item = {
        "id": job_id,
        "kind": body.kind,
        "target": body.target,
        "ids": list(body.ids),
        "field": body.field,
        "value": body.value,
        "user_id": int(user["id"]),
        "status": "queued",
        "done": 0,
        "total": len(body.ids),
        "cancel_requested": False,
        "created_at": __import__("time").time(),
    }
    with _LOCK:
        _JOBS[job_id] = item
    db.execute(
        "INSERT INTO bulk_jobs (id,user_id,kind,target,ids_json,processed_ids_json,field,value,status,done,total,"
        "result_json,error,cancel_requested,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            job_id,
            int(user["id"]),
            body.kind,
            body.target,
            json.dumps(body.ids),
            "[]",
            body.field,
            body.value,
            "queued",
            0,
            len(body.ids),
            "{}",
            "",
            0,
            time.time(),
        ),
    )
    db.commit()
    _POOL.submit(_run, item, db, user)
    return {"job_id": job_id, "status": "queued", "total": len(body.ids)}


@router.get("/{job_id}")
def get_job(job_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    item = _job(job_id, db)
    if int(item["user_id"]) != int(user["id"]) and not is_admin(user):
        raise HTTPException(403, "Нет доступа к задаче")
    return {k: v for k, v in item.items() if k not in {"ids", "user_id"}}


@router.post("/{job_id}/retry")
def retry_job(job_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    item = _job(job_id, db)
    if int(item["user_id"]) != int(user["id"]) and not is_admin(user):
        raise HTTPException(403, "Нет доступа к задаче")
    if item["status"] not in {"failed", "cancelled"}:
        raise HTTPException(409, "Эту задачу нельзя повторить")
    if item.get("cancel_requested"):
        item["cancel_requested"] = False
    _set(item, db, status="queued", error="", done=0, finished_at=None)
    _POOL.submit(_run, item, db, user)
    return {"job_id": job_id, "status": "queued", "total": item["total"]}


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    item = _job(job_id, db)
    if int(item["user_id"]) != int(user["id"]) and not is_admin(user):
        raise HTTPException(403, "Нет доступа к задаче")
    with _LOCK:
        if item["status"] in {"queued", "running"}:
            item["cancel_requested"] = True
            _persist(db, item)
    return {"ok": True, "status": item["status"]}
