"""Часть 21: мастер первого запуска + восстановление пароля по вопросу."""

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from server import tokens
from server.deps import get_db, get_current_user, is_admin, revoke_user_sessions
from server.routers.auth import _limiter, _user_payload, _ttl_days
from services.security import SecurityEngine

router = APIRouter(prefix="/api/setup", tags=["setup"])

SEC_QUESTIONS = [
    "Девичья фамилия матери?",
    "Название первой школы?",
    "Кличка первого домашнего животного?",
    "Город, где вы родились?",
    "Ваш любимый фильм?",
]


def _users_count(db) -> int:
    return db.fetch_one("SELECT COUNT(*) AS n FROM users")["n"]


@router.get("/status")
def status(db=Depends(get_db)):
    """Публично: нужен ли мастер первого запуска."""
    return {
        "needed": _users_count(db) == 0,
        "org_name": db.get_setting("brand_org_name", ""),
        "logo": db.get_setting("brand_logo", ""),
    }


class SetupAdmin(BaseModel):
    org_name: str = ""
    logo: str = ""  # dataURL (необязательно)
    username: str
    password: str
    full_name: str = ""
    sec_question: str
    sec_answer: str
    theme: str = "dark"
    lang: str = "ru"
    load_demo: bool = False


@router.post("/admin")
def create_admin(body: SetupAdmin, db=Depends(get_db)):
    """Создание первого администратора. Работает только на пустой базе."""
    if _users_count(db) > 0:
        raise HTTPException(409, "Настройка уже выполнена")
    username = body.username.strip()
    if len(username) < 3:
        raise HTTPException(400, "Логин: минимум 3 символа")
    if not SecurityEngine.valid_password(body.password):
        raise HTTPException(400, "Пароль: минимум 6 символов")
    if not body.sec_question.strip() or len(body.sec_answer.strip()) < 2:
        raise HTTPException(400, "Задайте секретный вопрос и ответ")
    if username.lower() == "admin" and body.password == "admin":
        raise HTTPException(
            400, "Комбинация admin/admin запрещена из соображений безопасности"
        )
    if db.fetch_one("SELECT id FROM users WHERE lower(username)=lower(?)", (username,)):
        raise HTTPException(409, "Такой логин уже существует")

    pw_hash, salt = SecurityEngine.generate_hash(body.password)
    ans_hash, ans_salt = SecurityEngine.generate_hash(body.sec_answer.strip().lower())
    cur = db.execute(
        "INSERT INTO users (username, password_hash, salt, role, "
        "full_name, sec_question, sec_answer_hash, sec_salt) "
        "VALUES (?, ?, ?, 'Administrator', ?, ?, ?, ?)",
        (
            username,
            pw_hash,
            salt,
            body.full_name.strip(),
            body.sec_question.strip(),
            ans_hash,
            ans_salt,
        ),
    )
    db.commit()
    uid = int(cur.lastrowid)

    db.upsert_setting("brand_org_name", body.org_name.strip()[:80])
    if body.logo.startswith("data:image/"):
        db.upsert_setting("brand_logo", body.logo[:300_000])
    db.upsert_setting("theme", body.theme)
    db.upsert_setting("app_language", body.lang)
    db.log_event(
        f"Setup wizard: administrator '{username}' created",
        "INFO",
        {"username": username},
    )

    token = issue_token(db, uid)
    return {
        "token": token,
        "user": _user_payload(
            {
                "id": uid,
                "username": username,
                "full_name": body.full_name,
                "role": "Administrator",
            }
        ),
    }


def issue_token(db, uid):
    from server.tokens import issue

    return issue(db, uid, ttl_days=30)


# ── Восстановление пароля по секретному вопросу ──


class RecoverQ(BaseModel):
    username: str


@router.post("/recover/question")
def recover_question(body: RecoverQ, db=Depends(get_db)):
    locked, remaining = _limiter.check_login(body.username)
    if locked:
        raise HTTPException(
            429, f"Слишком много попыток. Повторите через {remaining} с."
        )
    u = db.fetch_one(
        "SELECT * FROM users WHERE lower(username)=lower(?)", (body.username.strip(),)
    )
    if not u or not u.get("sec_question"):
        _limiter.record_login(body.username)
        raise HTTPException(404, "Секретный вопрос не задан")
    return {"question": u["sec_question"]}


class RecoverReset(BaseModel):
    username: str
    answer: str
    new_password: str


@router.post("/recover/reset")
def recover_reset(body: RecoverReset, db=Depends(get_db)):
    locked, remaining = _limiter.check_login(body.username)
    if locked:
        raise HTTPException(
            429, f"Слишком много попыток. Повторите через {remaining} с."
        )
    u = db.fetch_one(
        "SELECT * FROM users WHERE lower(username)=lower(?)", (body.username.strip(),)
    )
    ok = False
    if u and u.get("sec_answer_hash"):
        try:
            ok = SecurityEngine.verify(
                u["sec_answer_hash"], u["sec_salt"], body.answer.strip().lower()
            )
        except Exception:
            ok = False
    if not ok:
        _limiter.record_login(body.username)
        db.log_event(f"Failed recovery attempt: {body.username}", "WARNING")
        raise HTTPException(401, "Неверный ответ на секретный вопрос")
    if not SecurityEngine.valid_password(body.new_password):
        raise HTTPException(400, "Пароль: минимум 6 символов")
    pw_hash, salt = SecurityEngine.generate_hash(body.new_password)
    db.execute(
        "UPDATE users SET password_hash=?, salt=?, session_token='' WHERE id=?",
        (pw_hash, salt, u["id"]),
    )
    revoke_user_sessions(db, u["id"])
    db.commit()
    _limiter.clear_login(body.username)
    db.log_event(f"Password recovered via secret question: {u['username']}", "WARN", {})
    token = issue_token(db, u["id"])
    return {"ok": True, "token": token, "user": _user_payload(dict(u))}


# ── Брендинг для шапки ──


@router.get("/branding")
def branding(user=Depends(get_current_user), db=Depends(get_db)):
    return {
        "org_name": db.get_setting("brand_org_name", ""),
        "logo": db.get_setting("brand_logo", ""),
    }


class Branding(BaseModel):
    org_name: str = ""
    logo: str = ""


@router.post("/branding")
def save_branding(body: Branding, user=Depends(get_current_user), db=Depends(get_db)):
    if not is_admin(user):
        raise HTTPException(403, "Только администратор")
    db.upsert_setting("brand_org_name", body.org_name.strip()[:80])
    if body.logo.startswith("data:image/") or body.logo == "":
        db.upsert_setting("brand_logo", body.logo[:300_000])
    return {"ok": True}
