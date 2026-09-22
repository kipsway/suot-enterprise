"""Календарь+Время (Часть 25): события CRUD, категории, ДР сотрудников,
агенда дня, повторяющиеся события и напоминания для колокольчика."""

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from server.deps import get_db, get_current_user, is_admin
from services.database import DatabaseManager

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

REPEAT_VALUES = {"", "none", "daily", "weekly", "monthly", "yearly"}
CAT_COLOR = "#4F8DFF"


class EventIn(BaseModel):
    title: str
    date: str
    time: str = ""
    all_day: bool = False
    category_id: int = 0
    color: str = ""
    repeat: str = ""
    remind_min: int = 0
    note: str = ""
    location: str = ""


class CategoryIn(BaseModel):
    name: str
    color: str = CAT_COLOR


def _norm_date(d: str) -> str:
    """Принимает YYYY-MM-DD или DD.MM.YYYY → YYYY-MM-DD."""
    d = (d or "").strip()
    for f in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(d, f).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
    raise HTTPException(400, f"Неверная дата: {d}")


def _expand_repeat(ev: Dict[str, Any], start: str, end: str) -> List[Dict[str, Any]]:
    """Развернуть повторяющееся событие (кроме yearly — без даты рождения)."""
    rep = str(ev.get("repeat") or "").strip()
    if rep in ("", "none", "yearly"):
        return [ev]
    d_i = datetime.strptime(ev["date"], "%Y-%m-%d").date()
    s_i = datetime.strptime(start, "%Y-%m-%d").date()
    e_i = datetime.strptime(end, "%Y-%m-%d").date()
    if d_i < s_i:
        d_i = s_i
    step = {"daily": 1, "weekly": 7, "monthly": 0}.get(rep)
    out: List[Dict[str, Any]] = []
    cur = d_i
    guard = 0
    while cur <= e_i and guard < 500:
        if rep == "monthly":
            cur = d_i.replace(day=cur.day) if cur.day <= d_i.day else cur
        clone = dict(ev)
        clone["date"] = cur.isoformat()
        clone["_instance"] = True
        out.append(clone)
        guard += 1
        if rep == "monthly":
            try:
                if cur.month == 12:
                    cur = date(cur.year + 1, 1, 1)
                else:
                    cur = date(cur.year, cur.month + 1, 1)
                # удержать день месяца в пределах диапазона
                last = cur.replace(day=28) + timedelta(days=4)
                last = last.replace(day=1) - timedelta(days=1)
                cur = cur.replace(day=min(d_i.day, last.day))
            except ValueError:
                cur = date(d_i.year + 1, 1, 1)
        else:
            cur = cur + timedelta(days=step)
        if cur == d_i:
            break
    return out if out else [ev]


def _iter_birthdays(
    db: DatabaseManager,
    user_id: int,
    is_admin: bool,
    start: str,
    end: str,
) -> List[Dict[str, Any]]:
    """Дни рождения сотрудников: поле «ДР» (ГГГГ-ММ-ДД или ДД.ММ.ГГГГ)."""
    if not start or not end:
        return []
    rows, _ = db.query_json_records(
        "employees", owner_id=user_id, is_admin=is_admin, page_size=3000
    )
    out: List[Dict[str, Any]] = []
    s_i = datetime.strptime(start, "%Y-%m-%d").date()
    e_i = datetime.strptime(end, "%Y-%m-%d").date()
    for r in rows:
        dj = r.get("data_json") or {}
        bd = str(dj.get("ДР", "")).strip()
        if not bd:
            continue
        try:
            bd_d = datetime.strptime(bd, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            try:
                bd_d = datetime.strptime(bd, "%d.%m.%Y").date()
            except (ValueError, TypeError):
                continue
        name = str(dj.get("ФИО", dj.get("ФИО сотрудника", ""))).strip() or f"#{r['id']}"
        # ближайшее вхождение даты рождения в диапазон (включая текущий год)
        year = s_i.year
        for _y in (year, year + 1, year - 1):
            try:
                cand = date(_y, bd_d.month, bd_d.day)
            except ValueError:
                cand = date(_y, 2, 28)
            if s_i <= cand <= e_i:
                out.append(
                    {
                        "title": "🎂 " + name,
                        "date": cand.isoformat(),
                        "all_day": True,
                        "repeat": "yearly",
                        "category_id": 0,
                        "color": "#9B59B6",
                        "source": "birthday",
                        "employee_id": r["id"],
                        "id": 0,
                        "_birthday": True,
                    }
                )
    return out


@router.get("/events")
def calendar_events(
    start: str = "",
    end: str = "",
    include_bdays: bool = "1",
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    uid = int(user["id"])
    admin = is_admin(user)
    try:
        events = db.calendar_list_events(uid, admin, start, end)
    except Exception as e:
        raise HTTPException(500, f"calendar list: {e}")
    # нормализация дат + дефолтные цвета
    cats = {c["id"]: c for c in db.calendar_list_categories(uid, admin)}
    norm: List[Dict[str, Any]] = []
    for ev in events:
        try:
            ev["date"] = _norm_date(ev["date"])
        except HTTPException:
            continue
        cid = int(ev.get("category_id") or 0)
        if cid and cid in cats:
            ev["color"] = ev.get("color") or cats[cid]["color"] or CAT_COLOR
        if not ev.get("color"):
            ev["color"] = CAT_COLOR
        if (
            include_bdays
            and str(ev.get("repeat")) == "yearly"
            and ev.get("source") == "birthday"
        ):
            norm.append(ev)
            continue
        norm.append(ev)
    # разворачиваем повторы и сортируем
    out: List[Dict[str, Any]] = []
    for ev in norm:
        if start and end and ev.get("repeat") not in ("", "none", "yearly"):
            out.extend(_expand_repeat(ev, start, end))
        else:
            out.append(ev)
    if start and end and include_bdays:
        bdays = _iter_birthdays(db, uid, admin, start, end)
        existing = {
            (e["date"], e.get("employee_id")) for e in out if e.get("_birthday")
        }
        for b in bdays:
            if (b["date"], b["employee_id"]) not in existing:
                out.append(b)
    out.sort(key=lambda x: (x["date"], x.get("time", "")))
    return {"events": out}


@router.post("/events")
def create_event(body: EventIn, db=Depends(get_db), user=Depends(get_current_user)):
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(400, "Укажите название события")
    uid = int(user["id"])
    ev_date = _norm_date(body.date)
    cats = {c["id"] for c in db.calendar_list_categories(uid, is_admin(user))}
    cid = int(body.category_id or 0)
    if cid and cid not in cats:
        raise HTTPException(400, "Категория не найдена")
    data: Dict[str, Any] = {
        "title": title[:120],
        "date": ev_date,
        "time": (body.time or "").strip()[:8],
        "all_day": bool(body.all_day),
        "category_id": cid,
        "color": (body.color or "").strip(),
        "repeat": body.repeat if body.repeat in REPEAT_VALUES else "",
        "remind_min": max(0, int(body.remind_min or 0)),
        "note": (body.note or "").strip(),
        "location": (body.location or "").strip(),
    }
    new_id = db.calendar_save_event(uid, 0, data)
    db.log_event("Calendar event created", "INFO", {"id": new_id, "title": title})
    return {"id": new_id, "event": data}


@router.put("/events/{event_id}")
def update_event(
    event_id: int,
    body: EventIn,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    uid = int(user["id"])
    admin = is_admin(user)
    all_events = db.calendar_list_events(uid, True, "", "")
    cur = next((e for e in all_events if e["id"] == event_id), None)
    if not cur:
        raise HTTPException(404, "Событие не найдено")
    if not admin and int(cur.get("user_id", 0)) not in (uid, 0):
        raise HTTPException(403, "Чужая запись")
    data: Dict[str, Any] = {
        "title": (body.title or "").strip()[:120],
        "date": _norm_date(body.date),
        "time": (body.time or "").strip()[:8],
        "all_day": bool(body.all_day),
        "category_id": int(body.category_id or 0),
        "color": (body.color or "").strip(),
        "repeat": body.repeat if body.repeat in REPEAT_VALUES else "",
        "remind_min": max(0, int(body.remind_min or 0)),
        "note": (body.note or "").strip(),
        "location": (body.location or "").strip(),
    }
    db.calendar_save_event(uid, event_id, data)
    db.log_event("Calendar event updated", "INFO", {"id": event_id})
    return {"ok": True, "event": data}


@router.delete("/events/{event_id}")
def delete_event(event_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    uid = int(user["id"])
    admin = is_admin(user)
    all_events = db.calendar_list_events(uid, True, "", "")
    cur = next((e for e in all_events if e["id"] == event_id), None)
    if not cur:
        raise HTTPException(404, "Событие не найдено")
    if not admin and int(cur.get("user_id", 0)) not in (uid, 0):
        raise HTTPException(403, "Чужая запись")
    db.calendar_delete_event(event_id)
    return {"ok": True}


@router.get("/categories")
def list_categories(db=Depends(get_db), user=Depends(get_current_user)):
    uid = int(user["id"])
    cats = db.calendar_list_categories(uid, is_admin(user))
    if not cats:
        db.calendar_seed_categories(uid)
        cats = db.calendar_list_categories(uid, is_admin(user))
    return {"categories": cats}


@router.post("/categories")
def create_category(
    body: CategoryIn, db=Depends(get_db), user=Depends(get_current_user)
):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(400, "Укажите название категории")
    cid = db.calendar_save_category(
        int(user["id"]),
        0,
        name[:60],
        (body.color or "").strip() or CAT_COLOR,
    )
    return {"id": cid}


@router.put("/categories/{cat_id}")
def update_category(
    cat_id: int, body: CategoryIn, db=Depends(get_db), user=Depends(get_current_user)
):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(400, "Укажите название категории")
    db.calendar_save_category(
        int(user["id"]),
        cat_id,
        name[:60],
        (body.color or "").strip() or CAT_COLOR,
    )
    return {"ok": True}


@router.delete("/categories/{cat_id}")
def delete_category(cat_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    ok = db.calendar_delete_category(cat_id, int(user["id"]))
    if not ok:
        raise HTTPException(404, "Категория не найдена")
    db.log_event("Calendar category deleted", "INFO", {"id": cat_id})
    return {"ok": True}


@router.get("/agenda")
def agenda(day: str = "", db=Depends(get_db), user=Depends(get_current_user)):
    """Агенда дня: события календаря + напоминания по другим модулям."""
    uid = int(user["id"])
    admin = is_admin(user)
    day = _norm_date(day) if day else date.today().isoformat()
    events = db.calendar_list_events(uid, admin, day, day)
    cats = {c["id"]: c for c in db.calendar_list_categories(uid, admin)}
    items: List[Dict[str, Any]] = []
    for ev in events:
        ev["date"] = _norm_date(ev.get("date", day))
        if ev["date"] != day:
            continue
        cid = int(ev.get("category_id") or 0)
        color = (
            ev.get("color") or (cats[cid]["color"] if cid in cats else "") or CAT_COLOR
        )
        items.append(
            {
                "type": "event",
                "id": ev["id"],
                "title": ev.get("title", ""),
                "time": ev.get("time", ""),
                "all_day": bool(ev.get("all_day")),
                "color": color,
                "note": ev.get("note", ""),
            }
        )
    # ДР сотрудников на этот день
    for b in _iter_birthdays(db, uid, admin, day, day):
        items.append(
            {
                "type": "birthday",
                "id": 0,
                "title": b["title"],
                "time": "",
                "all_day": True,
                "color": b["color"],
                "note": "",
            }
        )
    items.sort(key=lambda x: (0 if x["all_day"] else 1, x["time"], x["title"]))
    return {"day": day, "items": items}
