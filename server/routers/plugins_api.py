"""Реестр плагинов (Часть 19) + Capability v2 (Блок 8).
v1: JSON-манифесты в web/plugins/ (commands/toolbar с behavior).
v2: manifest_version=2, capabilities, settings_schema, min_app_version;
проверка схемы (validate), гранты на write-возможности, per-user настройки."""

import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app_core.version import APP_VERSION
from server.deps import get_db, get_current_user, is_admin

router = APIRouter(prefix="/api/plugins", tags=["plugins"])

PLUGINS_DIR = Path(__file__).resolve().parents[2] / "web" / "plugins"

MANIFEST_VERSION = 2

# Известные возможности. Write-набор требует гранта администратора.
KNOWN_CAPABILITIES = {
    "table.read",
    "table.write",
    "clipboard",
    "reports.run",
    "documents.read",
}
WRITE_CAPABILITIES = {"table.write"}

# Поведение -> требуемые возможности (зеркало в web/js/part19.js).
BEHAVIOR_CAPS = {
    "copy_tsv": ["table.read", "clipboard"],
    "overdue_label": ["table.write"],
}

# Встроенные плагины поставки: файлы лежат рядом с кодом приложения,
# доверие — как коду (кто может писать в web/plugins/, тот владеет ФС).
# Дефолтные гранты сидируются в БД один раз (ключ plugins_grants отсутствует)
# и дальше отзываются/выдаются администратором как обычные.
BUNDLED_IDS = {"copy-tsv", "quick-overdue", "template-plugin"}

# v1-манифесты без capabilities: legacy-набор с варнингом.
LEGACY_CAPS = ["table.read", "table.write", "clipboard"]

SETTING_TYPES = {"string", "number", "boolean", "select"}


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


# ── Capability v2 ──


def _parse_ver(v: str):
    parts = []
    for chunk in str(v or "").strip().split(".")[:3]:
        num = "".join(ch for ch in chunk if ch.isdigit())
        if not chunk or not num:
            return None
        parts.append(int(num))
    if not parts:
        return None
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _declared_caps(manifest: dict) -> list:
    caps = manifest.get("capabilities", [])
    if not isinstance(caps, list):
        return []
    return [c for c in caps if isinstance(c, str)]


def _grants(db) -> dict:
    raw = db.get_setting("plugins_grants", None)
    if raw is None:
        # Первый запуск: дефолтные гранты встроенным плагинам.
        seed = {}
        for p in _scan():
            if p["id"] in BUNDLED_IDS:
                declared = _declared_caps(p)
                if p.get("manifest_version", 1) != MANIFEST_VERSION or not declared:
                    declared = LEGACY_CAPS
                write = sorted({c for c in declared if c in WRITE_CAPABILITIES})
                if write:
                    seed[p["id"]] = write
        db.upsert_setting("plugins_grants", json.dumps(seed))
        return seed
    try:
        v = json.loads(raw)
        return v if isinstance(v, dict) else {}
    except (ValueError, TypeError):
        return {}


def _effective(pid: str, manifest: dict, db) -> dict:
    """Эффективные возможности: safe — всегда, write — только по гранту
    (дефолтные гранты бандлов сидируются в БД и отзываются)."""
    declared = _declared_caps(manifest)
    if manifest.get("manifest_version", 1) != MANIFEST_VERSION or not declared:
        declared = LEGACY_CAPS
    granted = [c for c in declared if c not in WRITE_CAPABILITIES]
    stored = _grants(db).get(pid, [])
    for c in declared:
        if c in WRITE_CAPABILITIES and c in stored:
            granted.append(c)
    needs = [c for c in declared if c in WRITE_CAPABILITIES and c not in granted]
    return {"granted": sorted(set(granted)), "needs_grant": sorted(set(needs))}


def _compat(manifest: dict) -> str:
    need = manifest.get("min_app_version", "")
    if not need:
        return "ok"
    want = _parse_ver(need)
    if want is None:
        return "bad-version"
    have = _parse_ver(APP_VERSION)
    return "ok" if have and have >= want else "app-update-required"


def validate_manifest(data: dict) -> dict:
    """Проверка манифеста без побочных эффектов."""
    errors, warnings = [], []
    if not isinstance(data, dict):
        return {
            "ok": False,
            "errors": ["Манифест должен быть объектом"],
            "warnings": [],
        }
    if not data.get("id") or not isinstance(data.get("id"), str):
        errors.append("Поле id обязательно (строка)")
    for section in ("commands", "toolbar"):
        items = data.get(section, [])
        if not isinstance(items, list):
            errors.append(f"Поле {section} должно быть списком")
            continue
        for i, it in enumerate(items):
            if not isinstance(it, dict) or not it.get("behavior"):
                errors.append(f"{section}[{i}]: нужен behavior")
            elif it["behavior"] not in BEHAVIOR_CAPS:
                errors.append(
                    f"{section}[{i}]: неизвестное поведение "
                    f"«{it['behavior']}» (ядро: "
                    + ", ".join(sorted(BEHAVIOR_CAPS))
                    + ")"
                )
    caps = data.get("capabilities", None)
    if caps is None:
        warnings.append(
            "Нет capabilities — legacy v1, будет выдан набор " + ", ".join(LEGACY_CAPS)
        )
    elif not isinstance(caps, list):
        errors.append("Поле capabilities должно быть списком")
    else:
        for c in caps:
            if c not in KNOWN_CAPABILITIES:
                errors.append(
                    f"Неизвестная возможность «{c}» "
                    f"(известные: {', '.join(sorted(KNOWN_CAPABILITIES))})"
                )
    for b, need in BEHAVIOR_CAPS.items():
        used = any(
            isinstance(x, dict) and x.get("behavior") == b
            for sec in ("commands", "toolbar")
            for x in (data.get(sec) or [])
        )
        if used and caps is not None and isinstance(caps, list):
            missing = [c for c in need if c not in caps]
            if missing:
                errors.append(
                    f"Поведение «{b}» требует capabilities: " + ", ".join(missing)
                )
    schema = data.get("settings_schema", [])
    if schema:
        if not isinstance(schema, list):
            errors.append("Поле settings_schema должно быть списком")
        else:
            seen = set()
            for i, s in enumerate(schema):
                if not isinstance(s, dict) or not s.get("key"):
                    errors.append(f"settings_schema[{i}]: нужен key")
                    continue
                if s["key"] in seen:
                    errors.append(f"settings_schema[{i}]: дубль ключа «{s['key']}»")
                seen.add(s["key"])
                t = s.get("type", "string")
                if t not in SETTING_TYPES:
                    errors.append(
                        f"settings_schema[{i}]: неизвестный тип "
                        f"«{t}» (string|number|boolean|select)"
                    )
                if t == "select" and not isinstance(s.get("options"), list):
                    errors.append(f"settings_schema[{i}]: select требует options")
    mv = data.get("manifest_version", 1)
    if mv != MANIFEST_VERSION:
        warnings.append(
            f"manifest_version={mv}: legacy, рекомендуется {MANIFEST_VERSION}"
        )
    need = data.get("min_app_version", "")
    if need:
        if _parse_ver(need) is None:
            errors.append(f"min_app_version «{need}» не semver")
        elif _compat(data) != "ok":
            errors.append(f"Требуется приложение >= {need} (текущее {APP_VERSION})")
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "capabilities": _declared_caps(data) if not errors else [],
    }


@router.get("")
def list_plugins(db=Depends(get_db), user=Depends(get_current_user)):
    out = []
    for p in _scan():
        eff = _effective(p["id"], p, db)
        out.append(
            {
                "id": p["id"],
                "name": p.get("name", p["id"]),
                "name_en": p.get("name_en", p.get("name", p["id"])),
                "version": p.get("version", "1.0"),
                "description": p.get("description", ""),
                "description_en": p.get("description_en", p.get("description", "")),
                "author": p.get("author", ""),
                "enabled": _is_enabled(p["id"], p, db),
                "commands": len(p.get("commands", [])),
                "toolbar": len(p.get("toolbar", [])),
                "manifest_version": p.get("manifest_version", 1),
                "capabilities": _declared_caps(p),
                "granted_capabilities": eff["granted"],
                "needs_grant": bool(eff["needs_grant"]),
                "compat": _compat(p),
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
    """Полные манифесты ВКЛЮЧЁННЫХ плагинов для фронтенда + granted caps."""
    enabled = []
    for p in _scan():
        if not _is_enabled(p["id"], p, db):
            continue
        item = dict(p)
        item["granted_capabilities"] = _effective(p["id"], p, db)["granted"]
        enabled.append(item)
    return {"items": enabled}


class ValidateIn(BaseModel):
    manifest: dict


@router.post("/validate")
def validate(body: ValidateIn, user=Depends(get_current_user)):
    """Проверка манифеста без побочных эффектов (любой залогиненный)."""
    return validate_manifest(body.manifest)


class GrantsIn(BaseModel):
    grants: list


@router.post("/{pid}/grants")
def set_grants(
    pid: str, body: GrantsIn, db=Depends(get_db), user=Depends(get_current_user)
):
    """Гранты write-возможностей — только администратор."""
    if not is_admin(user):
        raise HTTPException(403, "Только администратор")
    manifests = {p["id"]: p for p in _scan()}
    if pid not in manifests:
        raise HTTPException(404, "Плагин не найден")
    declared = _declared_caps(manifests[pid])
    if manifests[pid].get("manifest_version", 1) != MANIFEST_VERSION or not declared:
        declared = LEGACY_CAPS
    clean = []
    for c in body.grants or []:
        if c not in KNOWN_CAPABILITIES:
            raise HTTPException(400, f"Неизвестная возможность «{c}»")
        if c not in declared:
            raise HTTPException(400, f"Плагин не декларирует «{c}»")
        clean.append(c)
    grants = _grants(db)
    grants[pid] = sorted(set(clean))
    db.upsert_setting("plugins_grants", json.dumps(grants))
    return {"ok": True, "granted": grants[pid]}


def _settings_key(pid: str, uid: int) -> str:
    return f"plugin_settings_{pid}_{uid}"


def _schema_of(pid: str, db) -> list:
    for p in _scan():
        if p["id"] == pid:
            schema = p.get("settings_schema", [])
            return schema if isinstance(schema, list) else []
    return []


@router.get("/{pid}/settings")
def get_settings(pid: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Настройки текущего пользователя + схема (дефолты из манифеста)."""
    schema = _schema_of(pid, db)
    if not any(p["id"] == pid for p in _scan()):
        raise HTTPException(404, "Плагин не найден")
    try:
        stored = json.loads(db.get_setting(_settings_key(pid, int(user["id"])), "{}"))
        stored = stored if isinstance(stored, dict) else {}
    except (ValueError, TypeError):
        stored = {}
    merged = {}
    for s in schema:
        if isinstance(s, dict) and s.get("key"):
            merged[s["key"]] = s.get("default")
    merged.update(stored)
    return {"settings": merged, "schema": schema}


@router.put("/{pid}/settings")
def put_settings(
    pid: str, body: dict, db=Depends(get_db), user=Depends(get_current_user)
):
    """Сохранить настройки с валидацией по схеме."""
    if not any(p["id"] == pid for p in _scan()):
        raise HTTPException(404, "Плагин не найден")
    schema = {
        s["key"]: s for s in _schema_of(pid, db) if isinstance(s, dict) and s.get("key")
    }
    if not isinstance(body, dict):
        raise HTTPException(400, "Объект настроек ожидался")
    clean = {}
    for k, v in body.items():
        if k not in schema:
            raise HTTPException(400, f"Неизвестный ключ «{k}»")
        t = schema[k].get("type", "string")
        if t == "boolean" and not isinstance(v, bool):
            raise HTTPException(400, f"«{k}» должен быть boolean")
        elif t == "number" and (not isinstance(v, (int, float)) or isinstance(v, bool)):
            raise HTTPException(400, f"«{k}» должен быть числом")
        elif t == "string" and not isinstance(v, str):
            raise HTTPException(400, f"«{k}» должен быть строкой")
        elif t == "select":
            opts = schema[k].get("options", [])
            if v not in opts:
                raise HTTPException(400, f"«{k}» должен быть одним из {opts}")
        clean[k] = v
    try:
        stored = json.loads(db.get_setting(_settings_key(pid, int(user["id"])), "{}"))
        stored = stored if isinstance(stored, dict) else {}
    except (ValueError, TypeError):
        stored = {}
    stored.update(clean)
    db.upsert_setting(
        _settings_key(pid, int(user["id"])), json.dumps(stored, ensure_ascii=False)
    )
    return {"ok": True, "settings": stored}
