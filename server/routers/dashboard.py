"""Дашборд, календарь, таймлайн — агрегаты по всем таблицам."""

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from server.deps import get_db, get_current_user, is_admin
from services.database import DatabaseManager

router = APIRouter(prefix="/api/dash", tags=["dashboard"])

DATE_FIELDS = {
    "employees": [("Дата медосмотра", "Медосмотр"), ("Дата проведения", "Инструктаж")],
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


def _period_start(period: str) -> str:
    now = datetime.now()
    deltas = {"today": 0, "week": 7, "month": 30, "year": 365}
    if period in deltas:
        return (now - timedelta(days=deltas[period])).strftime("%Y-%m-%d")
    return "2000-01-01"


def _parse_ru(s: str) -> Optional[datetime]:
    for f in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(s or "").strip(), f)
        except (ValueError, TypeError):
            continue
    return None


@router.get("/stats")
def stats(period: str = "all", db=Depends(get_db), user=Depends(get_current_user)):
    uid = None if is_admin(user) else int(user["id"])
    admin = is_admin(user)
    period_from = _period_start(period)
    counts: Dict[str, int] = {}
    overdue: List[Dict[str, Any]] = []
    recent: List[Dict[str, Any]] = []
    top_cats: Dict[str, int] = {}

    for table in sorted(DatabaseManager.JSON_TABLES):
        try:
            rows, total = db.query_json_records(
                table, owner_id=uid, is_admin=admin, page_size=5000
            )
            counts[table] = total
        except Exception:
            counts[table] = 0
            continue
        for r in rows:
            dj = r.get("data_json") or {}
            status = str(dj.get("Статус", "")).strip().lower()
            is_done = status in DONE_SET
            created = r.get("created_at") or ""
            if created >= period_from:
                recent.append(
                    {
                        "table": table,
                        "id": r["id"],
                        "title": str(
                            dj.get(
                                "ФИО",
                                dj.get(
                                    "Описание",
                                    dj.get("Наименование", dj.get("title", "")),
                                ),
                            )
                        )[:60],
                        "date": created[:10],
                    }
                )
            # просрочки
            for fld, label in DATE_FIELDS.get(table, []):
                dv = dj.get(fld)
                if not dv:
                    continue
                d = _parse_ru(dv)
                if not d or d >= datetime.now():
                    continue
                if is_done:
                    continue
                days = (datetime.now() - d).days
                overdue.append(
                    {
                        "table": table,
                        "id": r["id"],
                        "label": label,
                        "title": str(
                            dj.get(
                                "ФИО",
                                dj.get(
                                    "Описание",
                                    dj.get(
                                        "Наименование",
                                        dj.get("title", dj.get("Номер наряда", "")),
                                    ),
                                ),
                            )
                        )[:60],
                        "date": dv,
                        "days_overdue": days,
                    }
                )
            # топ категорий нарушений
            if table == "violations":
                cat = str(dj.get("Категория риска", "")).strip()
                if cat:
                    top_cats[cat] = top_cats.get(cat, 0) + 1

    overdue.sort(key=lambda x: -x["days_overdue"])
    recent.sort(key=lambda x: x.get("date", ""), reverse=True)
    safety = max(0, min(100, 100 - len(overdue) * 2))
    return {
        "counts": counts,
        "overdue": overdue[:20],
        "overdue_total": len(overdue),
        "recent": recent[:15],
        "safety": safety,
        "top_categories": sorted(top_cats.items(), key=lambda x: -x[1])[:6],
        "period": period,
    }


class RescheduleIn(BaseModel):
    table: str
    record_id: int
    field: str
    new_date: str  # ДД.ММ.ГГГГ


@router.post("/reschedule")
def reschedule(body: RescheduleIn, db=Depends(get_db), user=Depends(get_current_user)):
    if body.table not in DatabaseManager.JSON_TABLES:
        raise HTTPException(404, "Неизвестная таблица")
    uid = int(user["id"])
    admin = is_admin(user)
    rec = db.get_json_record(body.table, body.record_id)
    if not rec:
        raise HTTPException(404, "Запись не найдена")
    raw = db.fetch_one(
        f"SELECT user_id FROM {body.table} WHERE id=?", (body.record_id,)
    )
    owner = int(raw["user_id"] or 0) if raw else 0
    if owner != 0 and owner != uid and not admin:
        raise HTTPException(403, "Нет доступа")
    d = _parse_ru(body.new_date)
    if not d:
        raise HTTPException(400, "Неверный формат даты")
    data = dict(rec.get("data_json") or {})
    data[body.field] = body.new_date
    db.save_json_record(body.table, body.record_id, data, user_id=uid)
    return {"ok": True, "date": body.new_date}


@router.get("/calendar")
def calendar_events(
    start: str = "", end: str = "", db=Depends(get_db), user=Depends(get_current_user)
):
    uid = None if is_admin(user) else int(user["id"])
    admin = is_admin(user)
    events: List[Dict[str, Any]] = []
    now = datetime.now()
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
            is_done = status in DONE_SET
            for fld, label in DATE_FIELDS.get(table, []):
                dv = dj.get(fld)
                if not dv:
                    continue
                d = _parse_ru(dv)
                if not d:
                    continue
                ds = d.strftime("%Y-%m-%d")
                if start and ds < start:
                    continue
                if end and ds > end:
                    continue
                overdue = d < now and not is_done
                events.append(
                    {
                        "table": table,
                        "id": r["id"],
                        "field": fld,
                        "label": label,
                        "date": ds,
                        "title": str(
                            dj.get(
                                "ФИО",
                                dj.get(
                                    "Описание",
                                    dj.get(
                                        "Наименование",
                                        dj.get("title", dj.get("Номер наряда", "")),
                                    ),
                                ),
                            )
                        )[:60],
                        "overdue": overdue,
                        "done": is_done,
                    }
                )
    events.sort(key=lambda x: x["date"])
    return {"events": events}
