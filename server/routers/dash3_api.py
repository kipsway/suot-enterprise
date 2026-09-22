"""Дашборд 3.0 (Часть 24): «Мои задачи сегодня», лента активности из audit_log,
ярлыки видов. Дополняет существующий dashboard.py."""

from datetime import datetime, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from server.deps import get_db, get_current_user, is_admin
from services.database import DatabaseManager

router = APIRouter(prefix="/api/dash", tags=["dashboard3"])

DATE_FIELDS = {
    "violations": [("Срок устранения", "Срок нарушения")],
    "ppe": [("Срок замены", "Замена СИЗ")],
    "training": [("Срок действия", "Обучение")],
    "permits": [("Дата окончания", "Допуск")],
    "work_orders": [("Срок выполнения", "Наряд")],
    "ppe_inspections": [("Дата следующего осмотра", "Осмотр СИЗ")],
}

DONE_SET = {
    "устранено",
    "исполнено",
    "resolved",
    "соответствует",
    "выполнено",
    "готово",
    "закрыто",
    "done",
    "архив",
    "уволен",
    "отменено",
    "closed",
    "pass",
}


def _parse_ru(s) -> datetime | None:
    for f in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(s or "").strip(), f)
        except (ValueError, TypeError):
            continue
    return None


def _title_of(dj: dict) -> str:
    for k in (
        "ФИО",
        "Описание",
        "Наименование",
        "title",
        "Название",
        "Тема",
        "Номер наряда",
    ):
        if dj.get(k):
            return str(dj[k])[:80]
    return ""


def _overdue_of(table, dj):
    for fld, label in DATE_FIELDS.get(table, []):
        dv = dj.get(fld)
        d = _parse_ru(dv)
        if not d:
            continue
        status = str(dj.get("Статус", "")).lower()
        if status in DONE_SET:
            continue
        days = (d.date() - datetime.now().date()).days
        if days < 3:
            return {"field": fld, "label": label, "date": dv, "days": days}
    return None


@router.get("/permissions")
def dash_permissions(user=Depends(get_current_user)):
    return {"admin": is_admin(user), "user_id": int(user["id"])}


@router.get("/tasks")
def my_tasks(db=Depends(get_db), user=Depends(get_current_user)):
    """«Мои задачи сегодня»: CAPA + наряды + просрочки/близкие сроки +
    события календаря на сегодня."""
    uid = None if is_admin(user) else int(user["id"])
    admin = is_admin(user)
    today = datetime.now().date().isoformat()
    tasks: List[Dict[str, Any]] = []

    # CAPA с дедлайном
    try:
        where, params = (
            ("1=1", []) if admin else ("(user_id=? OR user_id=0)", [int(user["id"])])
        )
        rows = db.fetch_all(
            f"SELECT id, title, severity, status, deadline, assigned_to "
            f"FROM capa_records WHERE {where} ORDER BY deadline",
            tuple(params),
        )
        for r in rows:
            status = str(r["status"] or "").lower()
            if status in ("closed", "done", "закрыто", "архив"):
                continue
            dl = r["deadline"] or ""
            d = _parse_ru(dl)
            if not d:
                continue
            days = (d.date() - datetime.now().date()).days
            if days > 3:
                continue
            tasks.append(
                {
                    "type": "task",
                    "kind": "CAPA",
                    "section": "capa",
                    "id": r["id"],
                    "title": str(r["title"] or "")[:80],
                    "date": dl,
                    "days": days,
                    "overdue": days < 0,
                    "status": str(r["status"] or ""),
                }
            )
    except Exception:
        pass

    # JSON-таблицы: просрочки и ближайшие сроки
    for table in sorted(DatabaseManager.JSON_TABLES):
        try:
            rows, _ = db.query_json_records(
                table, owner_id=uid, is_admin=admin, page_size=5000
            )
        except Exception:
            continue
        for r in rows:
            dj = r.get("data_json") or {}
            hit = _overdue_of(table, dj)
            if not hit:
                continue
            if hit["days"] == 3:
                continue  # не «сегодня» (край — 2 дня)
            tasks.append(
                {
                    "type": "task",
                    "kind": hit["label"],
                    "section": table,
                    "id": r["id"],
                    "title": _title_of(dj) or f"#{r['id']}",
                    "date": hit["date"],
                    "days": hit["days"],
                    "overdue": hit["days"] < 0,
                    "status": str(dj.get("Статус", "") or ""),
                }
            )
    # событие сегодня из календаря
    try:
        import server.routers.dashboard as dashmod

        ev = dashmod.calendar_events(start=today, end=today, db=db, user=user)
        for e in ev["events"]:
            tasks.append(
                {
                    "type": "event",
                    "kind": "Событие",
                    "section": e["table"],
                    "id": e["id"],
                    "title": e["title"],
                    "date": e["date"],
                    "days": 0,
                    "overdue": e.get("overdue", False),
                    "status": "",
                }
            )
    except Exception:
        pass

    tasks.sort(key=lambda t: (t["overdue"], t["days"]))
    return {"tasks": tasks[:50], "today": today}


@router.get("/activity")
def activity(limit: int = 30, db=Depends(get_db), user=Depends(get_current_user)):
    rows = db.fetch_all(
        "SELECT id, timestamp, event, severity, username, details "
        "FROM audit_log ORDER BY id DESC LIMIT ?",
        (min(100, max(1, int(limit))),),
    )
    return {"items": [dict(r) for r in rows]}
