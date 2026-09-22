"""Часть 28: Инструменты — погода (open-meteo, кэш 30 мин), калькулятор дат,
макросы v1 («Конец месяца»). Все эндпоинты требуют авторизацию."""

import json
import time
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from server.deps import get_db, get_current_user

router = APIRouter(prefix="/api/tools", tags=["tools"])

# ── Кэш погоды (in-memory, per-city) ──
_WEATHER_CACHE: Dict[str, Dict[str, Any]] = {}
_WEATHER_TTL = 30 * 60  # 30 минут


def _wcache_key(city: str) -> str:
    return (city or "").strip().lower()


def _city_setting(user_id: int) -> str:
    return f"user:{user_id}:weather_city"


def get_weather_city(db, user_id: int) -> str:
    return (db.get_setting(_city_setting(user_id), "") or "").strip()


def save_weather_city(db, user_id: int, city: str) -> None:
    db.upsert_setting(_city_setting(user_id), (city or "").strip())


# ── Погода ──


class CityIn(BaseModel):
    city: str = ""


@router.post("/weather/city")
def set_weather_city(body: CityIn, db=Depends(get_db), user=Depends(get_current_user)):
    city = (body.city or "").strip()[:80]
    save_weather_city(db, int(user["id"]), city)
    return {"ok": True, "city": city}


@router.get("/weather")
async def get_weather(db=Depends(get_db), user=Depends(get_current_user)):
    """Погода через open-meteo (без ключа). Геокодинг → forecast.
    Кэш 30 минут. При недоступности сети — вежливая ошибка."""
    import httpx

    city = get_weather_city(db, int(user["id"]))
    if not city:
        return {
            "ok": False,
            "tip": "Укажите город в настройках (Инструменты → Погода)",
            "error": "no_city",
        }
    key = _wcache_key(city)
    cached = _WEATHER_CACHE.get(key)
    if cached and time.time() - cached["ts"] < _WEATHER_TTL:
        return {**cached["data"], "cached": True}

    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            # Геокодинг города
            gc = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city, "count": 1, "language": "ru", "format": "json"},
            )
            gc.raise_for_status()
            found = (gc.json().get("results") or [])[:1]
            if not found:
                return {"ok": False, "error": "city_not_found", "city": city}
            place = found[0]
            lat, lon = place["latitude"], place["longitude"]
            fc = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current_weather": "true",
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "timezone": "auto",
                    "forecast_days": 5,
                },
            )
            fc.raise_for_status()
            data = fc.json()
    except Exception as e:
        return {
            "ok": False,
            "error": str(e)[:200],
            "city": city,
            "tip": "Проверьте интернет и город в настройках",
        }

    current = data.get("current_weather") or {}
    daily = data.get("daily") or {}
    dates = daily.get("time") or []
    days = []
    for i, d in enumerate(dates):
        days.append(
            {
                "date": d,
                "tmax": (daily.get("temperature_2m_max") or [None] * len(dates))[i],
                "tmin": (daily.get("temperature_2m_min") or [None] * len(dates))[i],
                "precip": (
                    daily.get("precipitation_probability_max") or [None] * len(dates)
                )[i],
            }
        )
    forecast = {
        "ok": True,
        "city": city,
        "place": place.get("name") or city,
        "region": place.get("admin1") or "",
        "current": {
            "temp": current.get("temperature"),
            "wind": current.get("windspeed"),
            "code": current.get("weathercode"),
            "time": current.get("time"),
        },
        "days": days,
    }
    _WEATHER_CACHE[key] = {"ts": time.time(), "data": forecast}
    return forecast


# ── Калькулятор дат ──


class DateOpIn(BaseModel):
    op: str  # seniority | workdays | diff_days | month_end
    a: str = ""  # ISO yyyy-mm-dd
    b: str = ""  # ISO yyyy-mm-dd (для workdays/diff) или кол-во лет для seniority
    years: int = 0
    months: int = 0


def _parse_iso(s: str) -> Optional[date]:
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _month_end(d: date) -> date:
    nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return nxt - timedelta(days=1)


@router.post("/datecalc")
def datecalc(body: DateOpIn, db=Depends(get_db), user=Depends(get_current_user)):
    op = body.op
    today = date.today()

    if op == "month_end":
        ref = _parse_iso(body.a) or today
        return {"ok": True, "op": op, "result": _month_end(ref).isoformat()}

    if op == "diff_days":
        a, b = _parse_iso(body.a), _parse_iso(body.b)
        if not a or not b:
            return {"ok": False, "error": "Нужны две даты"}
        return {"ok": True, "op": op, "result": abs((b - a).days)}

    if op == "workdays":
        a, b = _parse_iso(body.a), _parse_iso(body.b)
        if a and not b:
            b = today
        if not a or not b:
            return {"ok": False, "error": "Нужна дата начала"}
        if b < a:
            a, b = b, a
        n = 0
        d = a
        while d <= b:
            if d.weekday() < 5:
                n += 1
            d += timedelta(days=1)
        return {"ok": True, "op": op, "result": n}

    if op == "seniority":
        start = _parse_iso(body.a)
        if not start:
            return {"ok": False, "error": "Нужна дата начала стажа"}
        end = _parse_iso(body.b) or today
        if end < start:
            return {"ok": False, "error": "Дата окончания раньше начала"}
        years = end.year - start.year
        months = end.month - start.month
        days = end.day - start.day
        if days < 0:
            months -= 1
            prev = end - timedelta(days=end.day)
            days = (end - prev).days
        if months < 0:
            years -= 1
            months += 12
        return {
            "ok": True,
            "op": op,
            "years": years,
            "months": months,
            "days": days,
            "result": f"{years} г. {months} мес. {days} дн.",
        }

    return {"ok": False, "op": op, "error": "Неизвестная операция"}


# ── Макросы v1 ──


class MacroRunIn(BaseModel):
    name: str


MACROS: Dict[str, Dict[str, Any]] = {
    "month_end": {
        "name": "month_end",
        "title": "Конец месяца",
        "description": "Подставить последний день текущего месяца",
    },
}


@router.get("/macros")
def macros_list(db=Depends(get_db), user=Depends(get_current_user)):
    return {"items": [MACROS[k] for k in MACROS]}


@router.post("/macros/run")
def macros_run(body: MacroRunIn, db=Depends(get_db), user=Depends(get_current_user)):
    if body.name not in MACROS:
        return {"ok": False, "error": "Макрос не найден"}
    return {
        "ok": True,
        "name": body.name,
        "result": _month_end(date.today()).isoformat(),
    }
