"""Аутентификация: регистрация, вход, профиль, публичный выбор языка."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from server.tokens import issue, verify, token_hash
from server.deps import get_db, get_current_user
from services.security import SecurityEngine, RateLimiter

router = APIRouter(prefix="/api/auth", tags=["auth"])
_limiter = RateLimiter()


class RegisterIn(BaseModel):
    username: str
    password: str
    full_name: str = ""
    remember: bool = True


class LoginIn(BaseModel):
    username: str
    password: str
    remember: bool = True


def _client_info(request: Request) -> dict:
    ua = (request.headers.get("user-agent") or "")[:200]
    ip = request.client.host if request.client else ""
    if request.headers.get("x-forwarded-for"):
        ip = request.headers["x-forwarded-for"].split(",")[0].strip()
    return {"ip": ip[:64], "user_agent": ua}


def _register_session(db, user_id: int, token: str, ttl_days: float, req: Request):
    info = _client_info(req)
    try:
        db.execute(
            "INSERT INTO sessions (user_id, token_hash, ip, user_agent, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                user_id,
                token_hash(token),
                info["ip"],
                info["user_agent"],
                _iso_expiry(ttl_days),
            ),
        )
        db.commit()
    except Exception:
        pass


def _iso_expiry(ttl_days: float) -> str:
    from datetime import datetime, timedelta

    return (datetime.now() + timedelta(days=ttl_days)).isoformat(timespec="seconds")


def _ttl_days(remember: bool) -> float:
    return 30 if remember else 0.5


class LanguageIn(BaseModel):
    language: str  # "ru" | "en"


def _user_payload(u: dict) -> dict:
    return {
        "id": u["id"],
        "username": u["username"],
        "full_name": u.get("full_name") or "",
        "role": u.get("role", "user"),
    }


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, db=Depends(get_db)):
    username = body.username.strip()
    if len(username) < 3:
        raise HTTPException(400, "Имя пользователя: минимум 3 символа")
    if not SecurityEngine.valid_password(body.password):
        raise HTTPException(400, "Пароль: минимум 6 символов")
    existing = db.fetch_one(
        "SELECT id FROM users WHERE lower(username)=lower(?)", (username,)
    )
    if existing:
        raise HTTPException(409, "Пользователь с таким именем уже существует")

    count = db.fetch_one("SELECT COUNT(*) AS n FROM users")["n"]
    role = "Administrator" if count == 0 else "user"
    pwd_hash, salt = SecurityEngine.generate_hash(body.password)
    cur = db.execute(
        "INSERT INTO users (username, password_hash, salt, role, full_name) "
        "VALUES (?, ?, ?, ?, ?)",
        (username, pwd_hash, salt, role, body.full_name.strip()),
    )
    db.commit()
    user_id = int(cur.lastrowid)
    db.log_event(
        f"Web registration: {username}",
        "INFO",
        {"username": username, "role": role},
        username=username,
    )
    ttl = _ttl_days(body.remember)
    token = issue(db, user_id, ttl_days=ttl)
    _register_session(db, user_id, token, ttl, request)
    return {
        "token": token,
        "user": _user_payload(
            {
                "id": user_id,
                "username": username,
                "full_name": body.full_name,
                "role": role,
            }
        ),
    }


@router.post("/login")
def login(body: LoginIn, request: Request, db=Depends(get_db)):
    locked, remaining = _limiter.check_login(body.username)
    if locked:
        raise HTTPException(
            429, f"Слишком много попыток. Повторите через {remaining} с."
        )
    u = db.fetch_one(
        "SELECT * FROM users WHERE lower(username)=lower(?)", (body.username.strip(),)
    )
    if not u or not SecurityEngine.verify(u["password_hash"], u["salt"], body.password):
        _limiter.record_login(body.username)
        db.log_event(
            f"Failed web login: {body.username}", "WARNING", username=body.username
        )
        raise HTTPException(401, "Неверное имя пользователя или пароль")
    if not u.get("is_active", 1):
        raise HTTPException(403, "Аккаунт заблокирован")
    _limiter.clear_login(body.username)
    db.log_event(
        f"Web login: {u['username']}",
        "INFO",
        {"role": u.get("role")},
        username=u["username"],
    )
    ttl = _ttl_days(body.remember)
    token = issue(db, u["id"], ttl_days=ttl)
    _register_session(db, u["id"], token, ttl, request)
    return {
        "token": token,
        "user": _user_payload(dict(u)),
    }


@router.get("/me")
def me(user=Depends(get_current_user)):
    return {"user": _user_payload(user)}


# ── Per-user язык и формат даты ──


def _locale_key(user_id: int, name: str) -> str:
    return f"user:{user_id}:{name}"


class LocaleIn(BaseModel):
    language: str = ""
    date_format: str = ""


@router.get("/locale")
def get_locale(db=Depends(get_db), user=Depends(get_current_user)):
    lang = db.get_setting(_locale_key(int(user["id"]), "lang"), "")
    date_fmt = db.get_setting(_locale_key(int(user["id"]), "date_format"), "")
    return {
        "language": lang or db.get_setting("app_language", "ru"),
        "date_format": date_fmt or "DD.MM.YYYY",
    }


@router.post("/locale")
def save_locale(body: LocaleIn, db=Depends(get_db), user=Depends(get_current_user)):
    uid = int(user["id"])
    out = {}
    if body.language:
        if body.language not in ("ru", "en"):
            raise HTTPException(400, "Язык должен быть ru или en")
        db.upsert_setting(_locale_key(uid, "lang"), body.language)
        out["language"] = body.language
    if body.date_format:
        if body.date_format not in ("DD.MM.YYYY", "YYYY-MM-DD"):
            raise HTTPException(400, "Формат даты: DD.MM.YYYY или YYYY-MM-DD")
        db.upsert_setting(_locale_key(uid, "date_format"), body.date_format)
        out["date_format"] = body.date_format
    if not out:
        raise HTTPException(400, "Нет полей")
    db.log_event("Locale updated", "INFO", {"fields": list(out)})
    return {"ok": True, **out}


# ── Активные сессии ──


@router.get("/sessions")
def list_sessions(db=Depends(get_db), user=Depends(get_current_user)):
    """Список активных сессий текущего пользователя (IP, браузер, метки)."""
    rows = db.fetch_all(
        "SELECT id, ip, user_agent, created_at, last_seen, expires_at, revoked "
        "FROM sessions WHERE user_id=? ORDER BY id DESC",
        (int(user["id"]),),
    )
    from datetime import datetime

    now = datetime.now().isoformat(timespec="seconds")
    out = []
    for s in rows:
        expired = bool(s["expires_at"]) and s["expires_at"] < now
        out.append(
            {
                "id": s["id"],
                "ip": s["ip"] or "",
                "user_agent": s["user_agent"] or "",
                "created_at": s["created_at"],
                "last_seen": s["last_seen"],
                "expires_at": s["expires_at"] or "",
                "revoked": bool(s["revoked"]) or expired,
                "current": False,
            }
        )
    return {"sessions": out}


@router.post("/sessions/{sid}/revoke")
def revoke_session(sid: int, db=Depends(get_db), user=Depends(get_current_user)):
    row = db.fetch_one(
        "SELECT * FROM sessions WHERE id=? AND user_id=?", (sid, int(user["id"]))
    )
    if not row:
        raise HTTPException(404, "Сессия не найдена")
    db.execute("UPDATE sessions SET revoked=1 WHERE id=?", (sid,))
    db.commit()
    db.log_event("Session revoked", "INFO", {"session_id": sid})
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    """Завершить текущую сессию по переданному токену."""
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.startswith("Bearer ") else ""
    if token:
        db.execute(
            "UPDATE sessions SET revoked=1 WHERE user_id=? AND token_hash=?",
            (int(user["id"]), token_hash(token)),
        )
        db.commit()
    db.log_event("Logout", "INFO", {"username": user["username"]})
    return {"ok": True}


@router.post("/language")
def set_language(body: LanguageIn, db=Depends(get_db)):
    if body.language not in ("ru", "en"):
        raise HTTPException(400, "Язык должен быть ru или en")
    db.upsert_setting("app_language", body.language)
    return {"ok": True, "language": body.language}
