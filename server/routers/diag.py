"""Часть 30: страница диагностики — версии, WebView2, порт, размер БД,
integrity, журнал сервера, статус сессий."""

import os
import platform
import shutil
import sys
import time

from fastapi import APIRouter, Depends
from server.deps import get_db, get_current_user, is_admin
from server import tokens
from app_core.version import APP_VERSION

router = APIRouter(prefix="/api/diag", tags=["diag"])

_START_TIME = time.time()


def _db_size(db) -> int:
    try:
        path = db._backend._conn.execute("PRAGMA database_list").fetchone()
        db_file = path[2] if path else ""
        return os.path.getsize(db_file) if db_file and os.path.exists(db_file) else 0
    except Exception:
        return 0


def _integrity(db) -> dict:
    try:
        rows = db.fetch_all("PRAGMA integrity_check")
        ok = rows and rows[0].get("integrity_check") == "ok"
        tables = db.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        return {
            "ok": bool(ok),
            "tables": len(tables),
        }
    except Exception as ex:
        return {"ok": False, "error": str(ex)[:200], "tables": 0}


def _db_meta(db) -> dict:
    counts = {}
    for tbl in ("users", "records", "employees", "audit_log"):
        try:
            counts[tbl] = db.fetch_one(f"SELECT COUNT(*) AS n FROM {tbl}")["n"]
        except Exception:
            counts[tbl] = -1
    return counts


def _webview2_info() -> dict:
    """Статус WebView2 runtime (используется desktop-оболочкой)."""
    hints = []
    if getattr(sys, "frozen", False):
        hints.append("bundled-app")
    try:
        import webview  # noqa: F401

        hints.append("pywebview-available")
    except Exception:
        hints.append("pywebview-missing")
    try:
        from PyQt5.QtCore import QLibraryInfo  # noqa: F401

        hints.append("qt-runtime")
    except Exception:
        pass
    return {
        "status": "ok" if "pywebview-available" in hints else "warn",
        "hints": hints,
    }


@router.get("")
@router.get("/summary")
def diag_summary(db=Depends(get_db), user=Depends(get_current_user)):
    """Общая диагностика для любого авторизованного пользователя."""

    def _port() -> int:
        try:
            return int(os.environ.get("SUOT_PORT", "8899"))
        except Exception:
            return 8899

    try:
        import fastapi

        fastapi_version = fastapi.__version__
    except Exception:
        fastapi_version = "?"
    try:
        import uvicorn

        uvicorn_version = uvicorn.__version__
    except Exception:
        uvicorn_version = "?"
    try:
        import httpx

        httpx_version = httpx.__version__
    except Exception:
        httpx_version = "?"

    size = _db_size(db)
    integrity = _integrity(db)

    return {
        "app": {
            "name": "ОхранаТруда Про",
            "version": APP_VERSION,
            "mode": "exe" if getattr(sys, "frozen", False) else "source",
            "uptime_sec": int(time.time() - _START_TIME),
        },
        "runtime": {
            "python": platform.python_version(),
            "python_exec": sys.executable,
            "os": platform.platform(),
            "fastapi": fastapi_version,
            "uvicorn": uvicorn_version,
            "httpx": httpx_version,
        },
        "server": {
            "host": os.environ.get("SUOT_HOST", "127.0.0.1"),
            "port": _port(),
            "webview2": _webview2_info(),
        },
        "database": {
            "size_bytes": size,
            "size_mb": round(size / 1048576, 2),
            "integrity": integrity,
            "counts": _db_meta(db),
        },
        "user": {
            "id": int(user["id"]),
            "username": user["username"],
            "role": user.get("role", "user"),
            "is_admin": is_admin(user),
        },
    }


@router.get("/log")
def diag_log(limit: int = 40, db=Depends(get_db), user=Depends(get_current_user)):
    """Последние записи журнала аудита."""
    limit = max(1, min(limit, 200))
    rows = db.fetch_all(
        "SELECT id, timestamp, event, severity, username, details "
        "FROM audit_log ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    return {
        "items": [
            {
                "id": r["id"],
                "timestamp": r["timestamp"],
                "event": r["event"],
                "severity": r["severity"],
                "username": r["username"] or "",
            }
            for r in rows
        ]
    }


@router.get("/disk")
def diag_disk(db=Depends(get_db), user=Depends(get_current_user)):
    """Размеры директорий данных (БД, бэкапы, медиа, экспорт)."""
    from app_core.config import RUNTIME_PATHS

    def _size_of(d: str) -> int:
        if not os.path.isdir(d):
            return 0
        total = 0
        for root, _dirs, files in os.walk(d):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        return total

    dirs = {
        "database": os.path.getsize(str(RUNTIME_PATHS.database_path))
        if os.path.exists(str(RUNTIME_PATHS.database_path))
        else 0,
        "backups": _size_of(str(RUNTIME_PATHS.backup_dir)),
        "media": _size_of(str(RUNTIME_PATHS.media_dir)),
        "exports": _size_of(str(RUNTIME_PATHS.export_dir)),
    }
    free_bytes = shutil.disk_usage(str(RUNTIME_PATHS.app_dir)).free
    return {
        "dirs": dirs,
        "free_bytes": free_bytes,
        "free_gb": round(free_bytes / 1073741824, 2),
    }
