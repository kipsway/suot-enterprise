"""Напоминания: список просрочек/предстоящих + настройки lead days."""

from datetime import datetime, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from server.deps import get_db, get_current_user, is_admin
from services.database import DatabaseManager

router = APIRouter(prefix="/api/reminders", tags=["reminders"])

DATE_FIELDS = {
    "employees": [
        ("Дата медосмотра", "Медосмотр", "medical"),
        ("Дата проведения", "Инструктаж", "briefing"),
    ],
    "violations": [("Срок устранения", "Срок нарушения", "violation")],
    "ppe": [("Срок замены", "Замена СИЗ", "ppe")],
    "training": [("Срок действия", "Обучение", "training")],
    "permits": [("Дата окончания", "Допуск", "permit")],
    "work_orders": [("Срок выполнения", "Наряд", "work_order")],
    "ppe_inspections": [("Дата следующего осмотра", "Осмотр СИЗ", "ppe_inspection")],
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

DEFAULT_LEAD = {
    "medical": 30,
    "briefing": 14,
    "violation": 7,
    "ppe": 30,
    "training": 30,
    "permit": 14,
    "work_order": 7,
    "ppe_inspection": 14,
}


class LeadDaysIn(BaseModel):
    lead_days: Dict[str, int]  # {type_key: days}


@router.get("/settings")
def get_reminder_settings(db=Depends(get_db), user=Depends(get_current_user)):
    settings = {}
    for k, v in DEFAULT_LEAD.items():
        stored = db.get_setting(f"reminder_lead_{k}", str(v))
        settings[k] = int(stored)
    return {"settings": settings}


@router.post("/settings")
def save_reminder_settings(
    body: LeadDaysIn, db=Depends(get_db), user=Depends(get_current_user)
):
    if not is_admin(user):
        raise HTTPException(403, "Только администратор")
    for k, v in body.lead_days.items():
        if k in DEFAULT_LEAD and 0 <= v <= 365:
            db.upsert_setting(f"reminder_lead_{k}", str(int(v)))
    return {"ok": True, "settings": body.lead_days}


@router.get("/list")
def reminder_list(db=Depends(get_db), user=Depends(get_current_user)):
    uid = None if is_admin(user) else int(user["id"])
    admin = is_admin(user)
    lead_settings = {}
    for k, v in DEFAULT_LEAD.items():
        stored = db.get_setting(f"reminder_lead_{k}", str(v))
        lead_settings[k] = int(stored)
    now = datetime.now()
    items: List[Dict[str, Any]] = []
    overdue_count = 0
    upcoming_count = 0
    for table in sorted(DatabaseManager.JSON_TABLES):
        try:
            rows, _ = db.query_json_records(
                table, owner_id=uid, is_admin=admin, page_size=3000
            )
        except Exception:
            continue
        for r in rows:
            dj = r.get("data_json") or {}
            status = str(dj.get("Статус", "")).strip().lower()
            if status in DONE_SET:
                continue
            title = str(
                dj.get(
                    "ФИО",
                    dj.get(
                        "Описание",
                        dj.get(
                            "Наименование", dj.get("title", dj.get("Номер наряда", ""))
                        ),
                    ),
                )
            )[:60]
            for fld, label, type_key in DATE_FIELDS.get(table, []):
                dv = dj.get(fld)
                if not dv:
                    continue
                d = None
                for f in ("%d.%m.%Y", "%Y-%m-%d"):
                    try:
                        d = datetime.strptime(str(dv).strip(), f)
                        break
                    except (ValueError, TypeError):
                        continue
                if not d:
                    continue
                lead = lead_settings.get(type_key, 30)
                warn_from = now + __import__("datetime").timedelta(days=lead)
                if d < now:
                    days = (now - d).days
                    items.append(
                        {
                            "table": table,
                            "id": r["id"],
                            "type": type_key,
                            "label": label,
                            "title": title,
                            "date": dv,
                            "days": days,
                            "status": "overdue",
                        }
                    )
                    overdue_count += 1
                elif d <= warn_from:
                    days = (d - now).days
                    items.append(
                        {
                            "table": table,
                            "id": r["id"],
                            "type": type_key,
                            "label": label,
                            "title": title,
                            "date": dv,
                            "days": days,
                            "status": "upcoming",
                        }
                    )
                    upcoming_count += 1
    items.sort(key=lambda x: (0 if x["status"] == "overdue" else 1, x["days"]))
    # Часть 25: события календаря с напоминаниями (remind_min до начала)
    try:
        evs = db.calendar_list_events(None if admin else int(user["id"]), admin, "", "")
    except Exception:
        evs = []
    for ev in evs:
        try:
            d = datetime.strptime(str(ev.get("date") or "").strip(), "%Y-%m-%d")
        except (ValueError, TypeError):
            continue
        title = str(ev.get("title", ""))[:60]
        remind = int(ev.get("remind_min") or 0)
        ref = d - timedelta(minutes=remind) if remind > 0 else d
        if ref < now:
            days = (now - ref).days
            items.append(
                {
                    "table": "calendar",
                    "id": ev["id"],
                    "type": "calendar",
                    "label": "Событие",
                    "title": title,
                    "date": ev.get("date", ""),
                    "days": days,
                    "status": "overdue",
                }
            )
            overdue_count += 1
        elif ref <= now + timedelta(days=3):
            days = (ref - now).days
            items.append(
                {
                    "table": "calendar",
                    "id": ev["id"],
                    "type": "calendar",
                    "label": "Событие",
                    "title": title,
                    "date": ev.get("date", ""),
                    "days": days,
                    "status": "upcoming",
                }
            )
            upcoming_count += 1
    items.sort(key=lambda x: (0 if x["status"] == "overdue" else 1, x["days"]))
    return {
        "items": items[:30],
        "overdue_count": overdue_count,
        "upcoming_count": upcoming_count,
        "total": overdue_count + upcoming_count,
    }
