"""Часть 17: API настроек и кастомизации (внешний вид, хоткеи, экспорт/импорт).

Настройки хранятся per-user в таблице settings под ключами
"user:{id}:*" — JSON-строки.
"""

import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from server.deps import get_db, get_current_user

router = APIRouter(prefix="/api/settings", tags=["settings"])

APPEARANCE_DEFAULTS: Dict[str, Any] = {
    "theme": "auto",  # auto|dark|light|ocean|forest|sunset
    "accent": "#6366F1",
    "font_family": "system",  # system|serif|mono|rounded
    "font_scale": 1.0,  # 0.9 .. 1.25
    "glass": True,  # акриловое стекло
    "density": "comfortable",  # compact|comfortable|spacious
    "radius": "md",  # sm|md|lg
    "watermark": "",  # текст водяного знака по умолчанию
    "custom_css": "",  # Часть 22: пользовательский CSS
    "show_counters": False,  # Часть 22: счётчики в меню (выкл. по умолчанию)
}

THEMES = ("auto", "dark", "light", "ocean", "forest", "sunset")

HOTKEYS_DEFAULTS: Dict[str, str] = {
    "palette": "Ctrl+K",
    "new_record": "Ctrl+N",
    "search": "Ctrl+F",
    "help": "F1",
    "theme_toggle": "Ctrl+Shift+T",
    "ai_chat": "Ctrl+I",
    "export_table": "Ctrl+E",
    "refresh": "F5",
}


def _ukey(user_id: int, name: str) -> str:
    return f"user:{user_id}:{name}"


def _load(db, user_id: int, name: str, defaults: Dict) -> Dict[str, Any]:
    raw = db.get_setting(_ukey(user_id, name), None)
    if not raw:
        return dict(defaults)
    try:
        data = json.loads(raw)
        return {**defaults, **data} if isinstance(data, dict) else dict(defaults)
    except (ValueError, TypeError):
        return dict(defaults)


def _save(db, user_id: int, name: str, data: Dict) -> None:
    db.upsert_setting(_ukey(user_id, name), json.dumps(data, ensure_ascii=False))


# ── Внешний вид ──


class AppearanceIn(BaseModel):
    theme: str = "dark"
    accent: str = "#6366F1"
    font_family: str = "system"
    font_scale: float = 1.0
    glass: bool = True
    density: str = "comfortable"
    radius: str = "md"
    watermark: str = ""
    custom_css: str = ""
    show_counters: bool = False


@router.get("/appearance")
def get_appearance(db=Depends(get_db), user=Depends(get_current_user)):
    return _load(db, int(user["id"]), "appearance", APPEARANCE_DEFAULTS)


@router.post("/appearance")
def save_appearance(
    body: AppearanceIn, db=Depends(get_db), user=Depends(get_current_user)
):
    if body.theme not in THEMES:
        raise HTTPException(400, "Неизвестная тема")
    if not 0.8 <= body.font_scale <= 1.4:
        raise HTTPException(400, "Масштаб шрифта: 0.8..1.4")
    if body.density not in ("compact", "comfortable", "spacious"):
        raise HTTPException(400, "Неизвестная плотность")
    if body.radius not in ("sm", "md", "lg"):
        raise HTTPException(400, "Неизвестный радиус")
    if len(body.custom_css) > 20000:
        raise HTTPException(400, "CSS слишком большой (лимит 20К)")
    data = body.dict()
    _save(db, int(user["id"]), "appearance", data)
    return {"ok": True, **data}


# ── Хоткеи ──


class HotkeysIn(BaseModel):
    hotkeys: Dict[str, str]


@router.get("/hotkeys")
def get_hotkeys(db=Depends(get_db), user=Depends(get_current_user)):
    return _load(db, int(user["id"]), "hotkeys", HOTKEYS_DEFAULTS)


@router.post("/hotkeys")
def save_hotkeys(body: HotkeysIn, db=Depends(get_db), user=Depends(get_current_user)):
    clean = {}
    for k, v in body.hotkeys.items():
        if k not in HOTKEYS_DEFAULTS:
            continue
        v = (v or "").strip()
        if v and len(v) <= 24:
            clean[k] = v
    _save(db, int(user["id"]), "hotkeys", clean)
    return {"ok": True, "hotkeys": {**HOTKEYS_DEFAULTS, **clean}}


# ── Сброс ──


@router.post("/reset")
def reset_all(db=Depends(get_db), user=Depends(get_current_user)):
    uid = int(user["id"])
    for name in ("appearance", "hotkeys"):
        db.upsert_setting(_ukey(uid, name), "")
    return {"ok": True, "appearance": APPEARANCE_DEFAULTS, "hotkeys": HOTKEYS_DEFAULTS}


# ── Экспорт / импорт ──


@router.get("/export")
def export_settings(db=Depends(get_db), user=Depends(get_current_user)):
    uid = int(user["id"])
    payload = {
        "_format": "suot-settings",
        "_version": 1,
        "appearance": _load(db, uid, "appearance", APPEARANCE_DEFAULTS),
        "hotkeys": _load(db, uid, "hotkeys", HOTKEYS_DEFAULTS),
    }
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="suot-settings.json"'},
    )


class ImportIn(BaseModel):
    appearance: Dict[str, Any] = {}
    hotkeys: Dict[str, Any] = {}


@router.post("/import")
def import_settings(body: ImportIn, db=Depends(get_db), user=Depends(get_current_user)):
    uid = int(user["id"])
    applied = {}
    if body.appearance:
        merged = {**APPEARANCE_DEFAULTS}
        for k in APPEARANCE_DEFAULTS:
            if k in body.appearance:
                merged[k] = body.appearance[k]
        _save(db, uid, "appearance", merged)
        applied["appearance"] = merged
    if body.hotkeys:
        merged_h = {**HOTKEYS_DEFAULTS}
        for k in HOTKEYS_DEFAULTS:
            if k in body.hotkeys and isinstance(body.hotkeys[k], str):
                v = body.hotkeys[k].strip()
                if v and len(v) <= 24:
                    merged_h[k] = v
        _save(db, uid, "hotkeys", merged_h)
        applied["hotkeys"] = merged_h
    if not applied:
        raise HTTPException(400, "Нет распознанных настроек")
    return {"ok": True, "applied": list(applied)}
