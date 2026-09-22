"""HMAC-подписанные токены аутентификации (stdlib-only, JWT-совместимый формат)."""

import hmac, hashlib, base64, json, time, secrets
from typing import Optional

_SECRET_CACHE: Optional[bytes] = None


def token_hash(token: str) -> str:
    """Чистый хэш токена для таблицы активных сессий."""
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def _get_secret(db) -> bytes:
    global _SECRET_CACHE
    if _SECRET_CACHE is None:
        s = db.get_setting("web_token_secret")
        if not s:
            s = secrets.token_hex(32)
            db.upsert_setting("web_token_secret", s)
        _SECRET_CACHE = str(s).encode("utf-8")
    return _SECRET_CACHE


def issue(db, user_id: int, ttl_days: int = 30) -> str:
    exp = int(time.time()) + ttl_days * 86400
    # jti делает каждый токен уникальным: без него два входа в одну секунду
    # давали бы побайтово одинаковые токены (неотличимые сессии, общий отзыв).
    payload = base64.urlsafe_b64encode(
        json.dumps(
            {"uid": int(user_id), "exp": exp, "jti": secrets.token_hex(8)}
        ).encode()
    ).rstrip(b"=")
    sig = hmac.new(_get_secret(db), payload, hashlib.sha256).hexdigest()
    return f"{payload.decode('ascii')}.{sig}"


def verify(db, token: str) -> Optional[int]:
    try:
        payload_str, sig = token.strip().split(".", 1)
        payload = payload_str.encode("ascii")
        good = hmac.new(_get_secret(db), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, good):
            return None
        pad = b"=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload + pad))
        if int(data.get("exp", 0)) < time.time():
            return None
        return int(data["uid"])
    except Exception:
        return None
