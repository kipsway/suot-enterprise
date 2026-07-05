import traceback
from typing import Optional, Dict, Any
from datetime import datetime


class SessionManager:
    def __init__(self, db) -> None:
        self.db = db

    def save_remember_me(self, username: str, token: str, expiry: datetime) -> None:
        try:
            self.db.execute("UPDATE users SET session_token=?, token_expiry=? WHERE username=?",
                            (token, expiry.isoformat(), username))
            self.db.upsert_setting("remember_me_token", token)
            self.db.upsert_setting("remember_me_expiry", expiry.isoformat())
            self.db.log_event("Remember Me session activated", "INFO")
            self.db.commit()
        except Exception:
            self.db.rollback()
            self.db.log_event(f"Remember Me failed: {traceback.format_exc()}", "CRITICAL")

    def clear_remember_me(self) -> None:
        try:
            self.db.execute("UPDATE users SET session_token=NULL, token_expiry=NULL")
            self.db.upsert_setting("remember_me_token", "")
            self.db.upsert_setting("remember_me_expiry", "")
            self.db.log_event("Remember Me session cleared", "INFO")
            self.db.commit()
        except Exception:
            self.db.rollback()
            self.db.log_event(f"Clear session failed: {traceback.format_exc()}", "CRITICAL")

    def validate_remember_me(self) -> Optional[Dict[str, Any]]:
        try:
            token = self.db.get_setting("remember_me_token", "")
            if not token:
                return None
            row = self.db.fetch_one(
                "SELECT id,username,password_hash,salt,role,session_token,token_expiry "
                "FROM users WHERE session_token=?", (token,))
            if not row:
                self.clear_remember_me()
                return None
            expiry_str = row.get("token_expiry", "")
            if expiry_str:
                try:
                    expiry = datetime.fromisoformat(expiry_str)
                    if datetime.now() > expiry:
                        self.clear_remember_me()
                        return None
                except Exception:
                    self.clear_remember_me()
                    return None
            return dict(row)
        except Exception:
            self.clear_remember_me()
            return None
