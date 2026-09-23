import json, traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

from services.database import DatabaseManager


WEBHOOK_EVENTS = [
    "violation.created",
    "violation.updated",
    "violation.overdue",
    "incident.created",
    "ppe.expiring",
    "ppe.issued",
    "training.expiring",
    "permit.expiring",
    "reminder.due",
]


def _match_events(configured_events: str, event: str) -> bool:
    if configured_events == "*":
        return True
    for e in configured_events.split(","):
        e = e.strip()
        if e == event:
            return True
        if e.endswith(".*") and event.startswith(e[:-1]):
            return True
    return False


def _send_webhook(url: str, payload: Dict[str, Any]) -> str:
    try:
        import requests

        r = requests.post(
            url,
            json=payload,
            timeout=10,
            headers={
                "User-Agent": "SUOT-Enterprise/1.0",
                "Content-Type": "application/json",
            },
        )
        if r.ok:
            return ""
        return f"HTTP {r.status_code}: {r.text[:200]}"
    except ImportError:
        return "requests library not available"
    except Exception as e:
        return str(e)


def fire_event(event: str, data: Optional[Dict[str, Any]] = None) -> List[str]:
    results = []
    try:
        db = DatabaseManager()
        rows = db.fetch_all("SELECT * FROM webhooks WHERE enabled=1 ORDER BY id")
        payload = {
            "event": event,
            "timestamp": datetime.now().isoformat(),
            "data": data or {},
        }
        for row in rows:
            if _match_events(str(row["events"]), event):
                err = _send_webhook(str(row["url"]), payload)
                status = "ok" if not err else f"error: {err[:100]}"
                db.execute(
                    "UPDATE webhooks SET last_status=?, last_error=? WHERE id=?",
                    (status, err[:500] if err else "", row["id"]),
                )
                db.conn.commit()
                if err:
                    results.append(f"[{row['id']}] {row['name']}: {err}")
    except Exception:
        results.append(f"fire_event error: {traceback.format_exc()}")
    return results


def test_webhook(url: str) -> str:
    payload = {
        "event": "test",
        "timestamp": datetime.now().isoformat(),
        "data": {"message": "SUOT Enterprise webhook test"},
    }
    return _send_webhook(url, payload)


def get_all_targets() -> List[Dict[str, Any]]:
    db = DatabaseManager()
    rows = db.fetch_all("SELECT * FROM webhooks ORDER BY id")
    return [dict(r) for r in rows] if rows else []


def save_target(target_id: int, name: str, url: str, events: str, enabled: bool) -> int:
    db = DatabaseManager()
    if target_id:
        db.execute(
            "UPDATE webhooks SET name=?, url=?, events=?, enabled=? WHERE id=?",
            (name, url, events, 1 if enabled else 0, target_id),
        )
        db.conn.commit()
        return target_id
    db.execute(
        "INSERT INTO webhooks (name, url, events, enabled) VALUES (?, ?, ?, ?)",
        (name, url, events, 1 if enabled else 0),
    )
    db.conn.commit()
    return db.fetch_one("SELECT last_insert_rowid() as id")["id"]


def delete_target(target_id: int) -> None:
    db = DatabaseManager()
    db.execute("DELETE FROM webhooks WHERE id=?", (target_id,))
    db.conn.commit()
