"""Часть 18: справка, журнал аудита, пользователи, пароли, обновления."""

import csv
import io
import secrets
import string
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from server import tokens
from server.deps import get_db, get_current_user, is_admin, revoke_user_sessions
from app_core.version import APP_VERSION

router = APIRouter(prefix="/api", tags=["help"])


# ── Версия и обновления ──


def parse_version(value: str):
    """('2','4','0') -> (2,4,0); нечисловые части (sha) игнорируем после build."""
    parts = []
    for chunk in str(value).split("."):
        nums = "".join(ch for ch in chunk if ch.isdigit())
        if nums:
            parts.append(int(nums))
        else:
            break
    return tuple(parts) or (0,)


def is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


@router.get("/help/version")
def version():
    return {
        "version": APP_VERSION,
        "name": "ОхранаТруда Про",
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }


class UpdateIn(BaseModel):
    manifest_url: str = ""


DEFAULT_MANIFEST = "https://kipsway.github.io/suot-enterprise/downloads/index.json"


@router.post("/update/check")
def update_check(
    body: UpdateIn = None, db=Depends(get_db), user=Depends(get_current_user)
):
    # Кастомный URL манифеста разрешён только администратору: иначе любой
    # вошедший пользователь мог бы заставить сервер запросить произвольный
    # URL (SSRF). Остальные используют настроенный URL или URL по умолчанию.
    if is_admin(user) and body and (body.manifest_url or "").strip():
        url = body.manifest_url.strip()
    else:
        url = db.get_setting("update_manifest_url", "")
    if not url:
        url = DEFAULT_MANIFEST
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "Некорректный URL манифеста")
    try:
        r = httpx.get(url, timeout=8.0)
        r.raise_for_status()
        manifest = r.json()
        latest = str(manifest.get("version", "")).strip()
    except Exception as e:
        return {"status": "unreachable", "current": APP_VERSION, "error": str(e)[:200]}
    if not latest:
        return {"status": "invalid_manifest", "current": APP_VERSION}
    # download URL: явное поле "url" или приоритетный артефакт (установщик .exe)
    download_url = str(manifest.get("url", "") or "").strip()
    if not download_url:
        base = url.rsplit("/", 1)[0]
        releases = manifest.get("releases", [])
        for ext in (".exe", ".zip"):
            for rel in releases or []:
                fname = str(rel.get("file", "") or "")
                if fname.lower().endswith(ext):
                    download_url = f"{base}/{fname.lstrip('/')}"
                    break
            if download_url:
                break
    notes = str(manifest.get("notes", "") or "").strip()
    if not notes and manifest.get("history"):
        hist = manifest["history"]
        if isinstance(hist, list) and hist:
            notes = "История версий:\n" + "\n".join(
                f"- {h.get('version', '')} ({h.get('date', '')}): {h.get('file', '')}"
                for h in hist[-5:]
            )
    return {
        "status": "ok",
        "current": APP_VERSION,
        "latest": latest,
        "up_to_date": not is_newer(latest, APP_VERSION),
        "notes": notes[:1000],
        "download_url": download_url,
    }


class OpenUpdateIn(BaseModel):
    url: str = ""


@router.post("/update/open")
def open_update_form(body: OpenUpdateIn, user=Depends(get_current_user)):
    import webbrowser
    import threading

    target = (body.url or "").strip()
    if not target.startswith(("http://", "https://")):
        raise HTTPException(400, "Некорректный URL")
    threading.Thread(target=lambda: webbrowser.open(target), daemon=True).start()
    return {"ok": True}


@router.post("/admin/update_url")
def set_update_url(body: UpdateIn, db=Depends(get_db), user=Depends(get_current_user)):
    if not is_admin(user):
        raise HTTPException(403, "Только администратор")
    url = (body.manifest_url or "").strip()
    if url and not url.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "URL должен начинаться с http:// или https://")
    db.upsert_setting("update_manifest_url", url)
    return {"ok": True}


@router.get("/admin/update_url")
def get_update_url(db=Depends(get_db), user=Depends(get_current_user)):
    if not is_admin(user):
        raise HTTPException(403, "Только администратор")
    return {"manifest_url": db.get_setting("update_manifest_url", "")}


# ── Журнал аудита ──


@router.get("/events")
def list_events(
    q: str = "",
    severity: str = "",
    username: str = "",
    limit: int = 100,
    offset: int = 0,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    limit = max(1, min(limit, 500))
    where, params = [], []
    if not is_admin(user):
        where.append("username=?")
        params.append(user["username"])
    elif username:
        where.append("username=?")
        params.append(username)
    if q:
        where.append("(event LIKE ? OR details LIKE ?)")
        like = f"%{q}%"
        params += [like, like]
    if severity:
        where.append("severity=?")
        params.append(severity)
    wsql = (" WHERE " + " AND ".join(where)) if where else ""
    total = db.fetch_one(f"SELECT COUNT(*) AS n FROM audit_log{wsql}", params)["n"]
    rows = db.fetch_all(
        f"SELECT id, timestamp, event, severity, username, details "
        f"FROM audit_log{wsql} ORDER BY id DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    )
    items = []
    for r in rows:
        d = r["details"] or "{}"
        items.append(
            {
                "id": r["id"],
                "timestamp": r["timestamp"],
                "event": r["event"],
                "severity": r["severity"],
                "username": r["username"],
                "details": d,
            }
        )
    return {"items": items, "total": total}


@router.get("/events/export.csv")
def export_events(db=Depends(get_db), user=Depends(get_current_user)):
    if not is_admin(user):
        rows = db.fetch_all(
            "SELECT timestamp, event, severity, username FROM audit_log "
            "WHERE username=? ORDER BY id DESC",
            (user["username"],),
        )
    else:
        rows = db.fetch_all(
            "SELECT timestamp, event, severity, username FROM audit_log "
            "ORDER BY id DESC"
        )
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Время", "Событие", "Важность", "Пользователь"])
    for r in rows:
        w.writerow([r["timestamp"], r["event"], r["severity"], r["username"]])
    return Response(
        content="\ufeff" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="audit.csv"'},
    )


# ── Пользователи (админ) ──


@router.get("/admin/users")
def admin_users(db=Depends(get_db), user=Depends(get_current_user)):
    if not is_admin(user):
        raise HTTPException(403, "Только администратор")
    rows = db.fetch_all(
        "SELECT id, username, full_name, role, is_active FROM users ORDER BY id"
    )
    counts = {
        r["user_id"]: r["n"]
        for r in db.fetch_all(
            "SELECT user_id, COUNT(*) AS n FROM records GROUP BY user_id"
        )
    }
    out = []
    for u in rows:
        out.append(
            {
                "id": u["id"],
                "username": u["username"],
                "full_name": u.get("full_name") or "",
                "role": u["role"],
                "active": bool(u["is_active"]),
                "records": counts.get(u["id"], 0),
            }
        )
    return {"users": out}


class RoleIn(BaseModel):
    role: str


@router.post("/admin/users/{uid}/role")
def set_role(
    uid: int, body: RoleIn, db=Depends(get_db), user=Depends(get_current_user)
):
    if not is_admin(user):
        raise HTTPException(403, "Только администратор")
    from services.permissions import UserPermissions

    valid_roles = set(UserPermissions.roles()) | {"user"}
    if body.role not in valid_roles:
        raise HTTPException(400, f"Роль: {' | '.join(sorted(valid_roles))}")
    target = db.fetch_one("SELECT * FROM users WHERE id=?", (uid,))
    if not target:
        raise HTTPException(404, "Не найден")
    if uid == int(user["id"]) and body.role != "Administrator":
        raise HTTPException(400, "Нельзя снять роль с себя")
    db.execute("UPDATE users SET role=? WHERE id=?", (body.role, uid))
    db.commit()
    db.log_event(
        f"Role changed: {target['username']} -> {body.role}",
        "INFO",
        {"by": user["username"]},
    )
    return {"ok": True}


class BlockIn(BaseModel):
    blocked: bool


@router.post("/admin/users/{uid}/block")
def block_user(
    uid: int, body: BlockIn, db=Depends(get_db), user=Depends(get_current_user)
):
    if not is_admin(user):
        raise HTTPException(403, "Только администратор")
    if uid == int(user["id"]):
        raise HTTPException(400, "Нельзя заблокировать себя")
    target = db.fetch_one("SELECT * FROM users WHERE id=?", (uid,))
    if not target:
        raise HTTPException(404, "Не найден")
    db.execute(
        "UPDATE users SET is_active=? WHERE id=?", (0 if body.blocked else 1, uid)
    )
    if body.blocked:
        db.execute("UPDATE users SET session_token='' WHERE id=?", (uid,))
        revoke_user_sessions(db, uid)
    db.commit()
    verb = "blocked" if body.blocked else "unblocked"
    db.log_event(
        f"User {verb}: {target['username']}",
        "WARN" if body.blocked else "INFO",
        {"by": user["username"]},
    )
    return {"ok": True}


@router.post("/admin/users/{uid}/reset_password")
def reset_password(uid: int, db=Depends(get_db), user=Depends(get_current_user)):
    if not is_admin(user):
        raise HTTPException(403, "Только администратор")
    target = db.fetch_one("SELECT * FROM users WHERE id=?", (uid,))
    if not target:
        raise HTTPException(404, "Не найден")
    alphabet = string.ascii_letters + string.digits
    new_pwd = "".join(secrets.choice(alphabet) for _ in range(10))
    from services.security import SecurityEngine as SE

    pwd_hash, salt = SE.generate_hash(new_pwd)
    db.execute(
        "UPDATE users SET password_hash=?, salt=?, session_token='' WHERE id=?",
        (pwd_hash, salt, uid),
    )
    revoke_user_sessions(db, uid)
    db.commit()
    db.log_event(
        f"Password reset: {target['username']}", "WARN", {"by": user["username"]}
    )
    return {"ok": True, "new_password": new_pwd}


def SecurityEngineHash(password: str):
    from services.security import SecurityEngine

    return SecurityEngine.generate_hash(password)


# ── Смена своего пароля ──


class ChangePwdIn(BaseModel):
    old_password: str
    new_password: str


@router.post("/auth/change_password")
def change_password(
    body: ChangePwdIn,
    request: Request,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    row = db.fetch_one("SELECT * FROM users WHERE id=?", (int(user["id"]),))
    if not row:
        raise HTTPException(404, "Пользователь не найден")
    from services.security import SecurityEngine

    if not SecurityEngine.verify(row["password_hash"], row["salt"], body.old_password):
        raise HTTPException(400, "Старый пароль неверен")
    if not SecurityEngine.valid_password(body.new_password):
        raise HTTPException(400, "Пароль: минимум 6 символов")
    pwd_hash, salt = SecurityEngine.generate_hash(body.new_password)
    db.execute(
        "UPDATE users SET password_hash=?, salt=? WHERE id=?",
        (pwd_hash, salt, int(user["id"])),
    )
    # Отзываем все чужие сессии, текущую сохраняем (пользователь остаётся в системе).
    auth = request.headers.get("Authorization", "")
    cur = auth[7:].strip() if auth.startswith("Bearer ") else ""
    revoke_user_sessions(db, int(user["id"]), tokens.token_hash(cur) if cur else "")
    db.commit()
    db.log_event(f"Password changed: {row['username']}", "INFO", {})
    return {"ok": True}
