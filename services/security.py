import os, hmac, hashlib, secrets, traceback
from typing import Optional, Tuple
from datetime import datetime
from app_core.config import AppConfig


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
