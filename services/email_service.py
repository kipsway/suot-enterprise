import smtplib
import ssl
import traceback
from datetime import datetime
from email.message import EmailMessage
from typing import Any, Dict, Optional

from PyQt5.QtCore import QObject
from services.database import DatabaseManager
from services.workerpool import AsyncPool, Worker


def _send_sync(
    cfg: Dict[str, str], to_addr: str, subject: str, html_body: str, text_body: str
) -> str:
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = cfg.get("from_addr", "")
        msg["To"] = to_addr
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")

        host = cfg.get("host", "")
        port = int(cfg.get("port", "587"))
        use_tls = cfg.get("use_tls", "true") == "true"
        username = cfg.get("username", "")
        password = cfg.get("password", "")

        ctx = ssl.create_default_context()
        if use_tls:
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.starttls(context=ctx)
                if username:
                    server.login(username, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP_SSL(host, port, timeout=15, context=ctx) as server:
                if username:
                    server.login(username, password)
                server.send_message(msg)
        return ""
    except Exception as e:
        return str(e)


NOTIFICATION_HTML = """\
<!DOCTYPE html>
<html><body style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f5f5f5;">
<div style="background: white; border-radius: 12px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
<div style="text-align: center; font-size: 36px; margin-bottom: 8px;">{icon}</div>
<h2 style="color: #333; margin: 0 0 8px 0; text-align: center;">{title}</h2>
<p style="color: #666; font-size: 14px; line-height: 1.5;">{message}</p>
<hr style="border: none; border-top: 1px solid #eee; margin: 16px 0;">
<p style="color: #999; font-size: 11px; text-align: center;">
SUOT Enterprise &mdash; {time}</p>
</div></body></html>"""


class EmailService(QObject):
    _instance: Optional["EmailService"] = None

    def __new__(cls, *args: Any, **kwargs: Any) -> "EmailService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, parent: Optional[QObject] = None) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        super().__init__(parent)
        self._db = DatabaseManager()

    def _get_config(self) -> Dict[str, str]:
        return {
            "host": self._db.get_setting("email_smtp_host", ""),
            "port": self._db.get_setting("email_smtp_port", "587"),
            "use_tls": self._db.get_setting("email_smtp_tls", "true"),
            "username": self._db.get_setting("email_username", ""),
            "password": self._db.get_setting("email_password", ""),
            "from_addr": self._db.get_setting("email_from", ""),
        }

    def is_enabled(self) -> bool:
        cfg = self._get_config()
        return bool(
            cfg["host"] and self._db.get_setting("email_enabled", "false") == "true"
        )

    def send(
        self, to_addr: str, subject: str, html_body: str, text_body: str = ""
    ) -> None:
        if not to_addr:
            return
        cfg = self._get_config()
        if not cfg["host"]:
            return
        if not text_body:
            text_body = subject
        worker = Worker(_send_sync, cfg, to_addr, subject, html_body, text_body)
        worker.signals.error.connect(
            lambda err: self._db.log_event(f"Email error: {err}", "WARNING")
        )
        AsyncPool.start(worker)

    def send_notification(
        self, title: str, message: str, severity: str = "info"
    ) -> int:
        if not self.is_enabled():
            return 0
        icon_map = {"info": "ℹ️", "warning": "⚠️", "error": "🚨", "success": "✅"}
        icon = icon_map.get(severity, "ℹ️")
        html = NOTIFICATION_HTML.format(
            icon=icon,
            title=title,
            message=message.replace("\n", "<br>"),
            time=datetime.now().strftime("%d.%m.%Y %H:%M"),
        )
        to_addr = self._db.get_setting("email_default_to", "")
        if to_addr:
            self.send(to_addr, f"[SUOT] {title}", html)
            return 1
        return 0

    def send_test(self, to_addr: str) -> Optional[str]:
        cfg = self._get_config()
        if not cfg["host"] or not to_addr:
            return "Check SMTP settings and recipient address"
        err = _send_sync(
            cfg,
            to_addr,
            "SUOT Enterprise — Test Email",
            "<h2>Test message</h2><p>Email configuration works.</p>",
            "Test message: Email configuration works.",
        )
        return err or None
