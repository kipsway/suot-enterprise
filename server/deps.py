"""Общие зависимости FastAPI: база данных и текущий пользователь."""

from fastapi import Depends, HTTPException, Request

from server import tokens
from services.database import DatabaseManager


def get_db():
    yield DatabaseManager()


def get_current_user(request: Request, db=Depends(get_db)) -> dict:
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.startswith("Bearer ") else ""
    if not token:
        raise HTTPException(401, "Требуется авторизация")
    uid = tokens.verify(db, token)
    if uid is None:
        raise HTTPException(401, "Сессия истекла, войдите заново")
    try:
        th = tokens.token_hash(token)
        sess = db.fetch_one(
            "SELECT revoked, expires_at FROM sessions WHERE token_hash=?", (th,)
        )
        if sess and (
            sess["revoked"]
            or (
                sess.get("expires_at")
                and sess["expires_at"]
                < __import__("datetime").datetime.now().isoformat(timespec="seconds")
            )
        ):
            raise HTTPException(401, "Сессия завершена")
    except HTTPException:
        raise
    except Exception:
        pass  # старая версия без таблицы сессий
    u = db.fetch_one("SELECT * FROM users WHERE id=?", (uid,))
    if not u:
        raise HTTPException(401, "Пользователь не найден")
    if not u.get("is_active", 1):
        raise HTTPException(403, "Аккаунт заблокирован")
    try:
        db.execute(
            "UPDATE sessions SET last_seen=datetime('now') WHERE token_hash=?",
            (tokens.token_hash(token),),
        )
        db.commit()
    except Exception:
        pass
    return dict(u)


def is_admin(user: dict) -> bool:
    return user.get("role") == "Administrator"


def revoke_user_sessions(db, user_id: int, except_token_hash: str = "") -> None:
    """Отозвать все сессии пользователя (кроме указанной).

    Вызывать при смене/сбросе пароля и блокировке, чтобы украденный
    токен не переживал смену пароля. Терпим к БД без таблицы sessions.
    """
    try:
        if except_token_hash:
            db.execute(
                "UPDATE sessions SET revoked=1 WHERE user_id=? AND token_hash!=?",
                (int(user_id), except_token_hash),
            )
        else:
            db.execute("UPDATE sessions SET revoked=1 WHERE user_id=?", (int(user_id),))
        db.commit()
    except Exception:
        pass
