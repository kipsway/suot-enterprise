"""Periodic task scheduler."""

import json
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from services.database import DatabaseManager


class ScheduleService:
    def __init__(self):
        self._db = DatabaseManager()
        self._jobs: Dict[str, Callable] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def add_job(
        self,
        name: str,
        callback: Callable,
        interval_minutes: int = 0,
        interval_hours: int = 0,
        interval_days: int = 0,
        enabled: bool = True,
    ) -> None:
        self._jobs[name] = callback
        config = json.dumps(
            {
                "interval_minutes": interval_minutes,
                "interval_hours": interval_hours,
                "interval_days": interval_days,
                "enabled": enabled,
            }
        )
        self._db.upsert_setting(f"sched_{name}", config)

    def remove_job(self, name: str) -> None:
        self._jobs.pop(name, None)
        self._db.upsert_setting(f"sched_{name}", "")

    def get_jobs(self) -> List[Dict[str, Any]]:
        result = []
        for key in self._db.get_settings_like("sched_"):
            name = key[len("sched_") :]
            try:
                config = json.loads(self._db.get_setting(key, "{}"))
            except (json.JSONDecodeError, TypeError):
                config = {}
            result.append({"name": name, **config})
        return result

    def _get_interval_seconds(self, config: dict) -> int:
        return (
            config.get("interval_minutes", 0) * 60
            + config.get("interval_hours", 0) * 3600
            + config.get("interval_days", 0) * 86400
        )

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        last_run: Dict[str, float] = {}
        while self._running:
            for name, callback in list(self._jobs.items()):
                config_key = f"sched_{name}"
                raw = self._db.get_setting(config_key, "")
                if not raw:
                    continue
                try:
                    config = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                if not config.get("enabled", True):
                    continue
                interval = self._get_interval_seconds(config)
                if interval <= 0:
                    continue
                now = time.time()
                if name not in last_run:
                    last_run[name] = now
                    continue
                if now - last_run[name] >= interval:
                    try:
                        callback()
                    except Exception:
                        pass
                    last_run[name] = now
            time.sleep(10)
