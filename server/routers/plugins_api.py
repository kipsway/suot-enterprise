"""Часть 19: реестр плагинов (JSON-манифесты в web/plugins/)."""

import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from server.deps import get_db, get_current_user, is_admin

router = APIRouter(prefix="/api/plugins", tags=["plugins"])

PLUGINS_DIR = Path(__file__).resolve().parents[2] / "web" / "plugins"


def _scan() -> list:
    items = []
    if PLUGINS_DIR.is_dir():
        for f in sorted(PLUGINS_DIR.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("id") and isinstance(data.get("commands", []), list):
                    data["_file"] = f.name
                    items.append(data)
            except Exception:
                continue
    return items


def _disabled(db) -> list:
    raw = db.get_setting("plugins_disabled", "[]")
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else []
    except (ValueError, TypeError):
        return []


def _forced(db) -> list:
    raw = db.get_setting("plugins_force_enabled", "[]")
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else []
    except (ValueError, TypeError):
        return []


def _is_enabled(pid: str, manifest: dict, db) -> bool:
    if pid in _forced(db):
        return True
    if pid in _disabled(db):
        return False
    return manifest.get("enabled_by_default", True) is not False


@router.get("")
def list_plugins(db=Depends(get_db), user=Depends(get_current_user)):
    out = []
    for p in _scan():
        out.append(
            {
                "id": p["id"],
                "name": p.get("name", p["id"]),
                "version": p.get("version", "1.0"),
                "description": p.get("description", ""),
                "author": p.get("author", ""),
                "enabled": _is_enabled(p["id"], p, db),
                "commands": len(p.get("commands", [])),
                "toolbar": len(p.get("toolbar", [])),
            }
        )
    return {"items": out}


class ToggleIn(BaseModel):
    enabled: bool


@router.post("/{pid}/toggle")
def toggle(
    pid: str, body: ToggleIn, db=Depends(get_db), user=Depends(get_current_user)
):
    if not is_admin(user):
        raise HTTPException(403, "Только администратор")
    manifests = {p["id"]: p for p in _scan()}
    if pid not in manifests:
        raise HTTPException(404, "Плагин не найден")
    disabled = set(_disabled(db))
    forced = set(_forced(db))
    if body.enabled:
        disabled.discard(pid)
        if manifests[pid].get("enabled_by_default", True) is False:
            forced.add(pid)
        else:
            forced.discard(pid)
    else:
        disabled.add(pid)
        forced.discard(pid)
    db.upsert_setting("plugins_disabled", json.dumps(sorted(disabled)))
    db.upsert_setting("plugins_force_enabled", json.dumps(sorted(forced)))
    return {"ok": True, "enabled": body.enabled}


@router.get("/raw")
def raw_manifests(db=Depends(get_db), user=Depends(get_current_user)):
    """Полные манифесты ВКЛЮЧЁННЫХ плагинов для фронтенда."""
    enabled = [p for p in _scan() if _is_enabled(p["id"], p, db)]
    return {"items": enabled}
