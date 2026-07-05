import os, hmac, hashlib, secrets, struct, time, base64, json, traceback
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timedelta
from app_core.config import AppConfig


TOTP_INTERVAL = 30
TOTP_DIGITS = 6
RATE_LIMIT_WINDOW = 300
RATE_LIMIT_MAX_ATTEMPTS = 5
LOCKOUT_DURATION = 900


def _totp_int(secret: bytes, timestamp: Optional[int] = None) -> int:
    counter = struct.pack(">Q", (timestamp or int(time.time())) // TOTP_INTERVAL)
    h = hmac.new(secret, counter, "sha1").digest()
    offset = h[-1] & 0x0F
    code = (struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** TOTP_DIGITS)
    return code


def _generate_totp_secret() -> bytes:
    return os.urandom(20)


def _secret_to_base32(secret: bytes) -> str:
    return base64.b32encode(secret).decode("ascii").rstrip("=")


class SecurityEngine:
    @staticmethod
    def generate_hash(password: str, salt: Optional[bytes] = None) -> Tuple[str, str]:
        safe_salt = salt if salt is not None else os.urandom(32)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 safe_salt, AppConfig.PBKDF2_ITERATIONS)
        return dk.hex(), safe_salt.hex()

    @staticmethod
    def verify(stored_hash: str, salt_hex: str, provided: str) -> bool:
        try:
            salt = bytes.fromhex(salt_hex)
            h, _ = SecurityEngine.generate_hash(provided, salt)
            return hmac.compare_digest(stored_hash, h)
        except Exception:
            return False

    @staticmethod
    def create_token(length: int = AppConfig.TOKEN_LENGTH) -> str:
        return secrets.token_hex(max(32, length) // 2)

    @staticmethod
    def valid_password(password: str) -> bool:
        return isinstance(password, str) and len(password) >= 6

    @staticmethod
    def generate_totp_secret_b32() -> str:
        return _secret_to_base32(_generate_totp_secret())

    @staticmethod
    def get_totp_uri(secret_b32: str, username: str, issuer: str = "SUOT Enterprise") -> str:
        return (f"otpauth://totp/{issuer}:{username}?secret={secret_b32}"
                f"&issuer={issuer}&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_INTERVAL}")

    @staticmethod
    def verify_totp(secret_b32: str, code: str) -> bool:
        try:
            padding = 8 - (len(secret_b32) % 8) if len(secret_b32) % 8 else 0
            secret = base64.b32decode(secret_b32 + "=" * padding)
            now = int(time.time())
            for offset in (-1, 0, 1):
                expected = _totp_int(secret, now + offset * TOTP_INTERVAL)
                if hmac.compare_digest(str(expected).zfill(TOTP_DIGITS), code.strip()):
                    return True
            return False
        except Exception:
            return False


class RateLimiter:
    def __init__(self) -> None:
        self._attempts: Dict[str, list] = {}

    def record_attempt(self, key: str) -> int:
        now = time.time()
        if key not in self._attempts:
            self._attempts[key] = []
        self._attempts[key].append(now)
        self._attempts[key] = [t for t in self._attempts[key]
                               if now - t < RATE_LIMIT_WINDOW]
        return len(self._attempts[key])

    def is_locked(self, key: str) -> Tuple[bool, int]:
        now = time.time()
        attempts = self._attempts.get(key, [])
        attempts = [t for t in attempts if now - t < RATE_LIMIT_WINDOW]
        self._attempts[key] = attempts
        if len(attempts) >= RATE_LIMIT_MAX_ATTEMPTS:
            elapsed = now - attempts[0]
            if elapsed < LOCKOUT_DURATION:
                remaining = int(LOCKOUT_DURATION - elapsed)
                return True, max(1, remaining)
            self._attempts[key] = []
        return False, 0

    def check_login(self, username: str) -> Tuple[bool, int]:
        return self.is_locked(f"login:{username.lower()}")

    def record_login(self, username: str) -> int:
        return self.record_attempt(f"login:{username.lower()}")

    def clear_login(self, username: str) -> None:
        self._attempts.pop(f"login:{username.lower()}", None)
