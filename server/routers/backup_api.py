"""Часть 19: резервное копирование и восстановление.

ZIP = база данных (sqlite backup API) + media/ + manifest.json.
Бэкапы лежат в <рядом с БД>/backups/. Операции — только админ.
"""

import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from server.deps import get_db, get_current_user, is_admin
from services.database import DatabaseManager
from app_core.version import APP_VERSION

router = APIRouter(prefix="/api/backup", tags=["backup"])


def _backups_dir(db) -> str:
    root = os.path.dirname(str(db.database_path)) or "."
    d = os.path.join(root, "backups")
    os.makedirs(d, exist_ok=True)
    return d


def _safe_name(name: str) -> str:
    if (
        not name
        or "/" in name
        or "\\" in name
        or ".." in name
        or not name.endswith(".zip")
    ):
        raise HTTPException(400, "Некорректное имя файла")
    return name


def _manifest_stats(db) -> dict:
    users = db.fetch_one("SELECT COUNT(*) AS n FROM users")["n"]
    tables = {}
    for t in sorted(DatabaseManager.JSON_TABLES):
        try:
            tables[t] = db.fetch_one(f"SELECT COUNT(*) AS n FROM {t}")["n"]
        except Exception:
            tables[t] = 0
    try:
        custom = db.fetch_one("SELECT COUNT(*) AS n FROM custom_tables")["n"]
        custom_records = db.fetch_one("SELECT COUNT(*) AS n FROM custom_records")["n"]
    except Exception:
        custom = custom_records = 0
    return {
        "users": users,
        "tables": tables,
        "custom_tables": custom,
        "custom_records": custom_records,
    }


def create_backup_file(db, tag: str = "manual") -> str:
    """Создаёт ZIP-бэкап, возвращает путь."""
    bdir = _backups_dir(db)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{tag}_{stamp}.zip"
    path = os.path.join(bdir, name)
    i = 1
    while os.path.exists(path):
        name = f"{tag}_{stamp}_{i}.zip"
        path = os.path.join(bdir, name)
        i += 1

    conn: sqlite3.Connection = db._backend._conn
    tmp_db = tempfile.mktemp(suffix=".db")
    dst = sqlite3.connect(tmp_db)
    conn.backup(dst)
    dst.close()

    media_dir = None
    try:
        from app_core.config import RUNTIME_PATHS

        media_dir = getattr(RUNTIME_PATHS, "media_path", None)
    except Exception:
        media_dir = None
    if not media_dir or not os.path.isdir(media_dir):
        cand = os.path.join(os.path.dirname(str(db.database_path)), "media")
        media_dir = cand if os.path.isdir(cand) else None

    manifest = {
        "_format": "suot-backup",
        "_version": 1,
        "app_version": APP_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "tag": tag,
        "stats": _manifest_stats(db),
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(tmp_db, "database.db")
        if media_dir:
            for root, _, files in os.walk(media_dir):
                for f in files:
                    fp = os.path.join(root, f)
                    arc = os.path.join("media", os.path.relpath(fp, media_dir))
                    z.write(fp, arc)
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    os.remove(tmp_db)
    return path


# ── Настройки авто-бэкапа ──


class BackupSettings(BaseModel):
    enabled: bool
    keep: int = 5


@router.get("/settings")
def get_settings(db=Depends(get_db), user=Depends(get_current_user)):
    return {
        "enabled": db.get_setting("auto_backup_enabled", "1") == "1",
        "keep": int(db.get_setting("auto_backup_keep", "5")),
    }


@router.post("/settings")
def save_settings(
    body: BackupSettings, db=Depends(get_db), user=Depends(get_current_user)
):
    if not is_admin(user):
        raise HTTPException(403, "Только администратор")
    keep = max(1, min(body.keep, 50))
    db.upsert_setting("auto_backup_enabled", "1" if body.enabled else "0")
    db.upsert_setting("auto_backup_keep", str(keep))
    return {"ok": True}


def run_auto_backup(db) -> Optional[str]:
    """Авто-бэкап при старте: раз в сутки + ротация до keep."""
    if db.get_setting("auto_backup_enabled", "1") != "1":
        return None
    bdir = _backups_dir(db)
    today = datetime.now().strftime("%Y%m%d")
    for f in os.listdir(bdir):
        if f.startswith("auto_") and today in f:
            return None  # сегодняшний уже есть
    path = create_backup_file(db, tag="auto")
    prune_backups(db)
    return path


def prune_backups(db) -> int:
    """Оставить последние N бэкапов (настройка auto_backup_keep)."""
    keep = int(db.get_setting("auto_backup_keep", "5"))
    bdir = _backups_dir(db)
    files = sorted(f for f in os.listdir(bdir) if f.endswith(".zip"))
    removed = 0
    for f in files[:-keep] if len(files) > keep else []:
        try:
            os.remove(os.path.join(bdir, f))
            removed += 1
        except OSError:
            pass
    return removed


# ── Системные удобства ──


@router.post("/open-folder")
def open_data_folder(db=Depends(get_db), user=Depends(get_current_user)):
    """Открыть папку данных (БД/медиа/бэкапы) в проводнике. Админ."""
    if not is_admin(user):
        raise HTTPException(403, "Только администратор")
    folder = os.path.dirname(str(db.database_path)) or "."
    if not os.path.isdir(folder):
        raise HTTPException(404, "Папка не найдена")
    try:
        os.startfile(folder)  # Windows
        return {"ok": True}
    except AttributeError:
        import subprocess

        subprocess.Popen(["xdg-open", folder])
        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, f"Не удалось открыть: {e}")


# ── Операции ──


@router.post("/create")
def create_backup(db=Depends(get_db), user=Depends(get_current_user)):
    if not is_admin(user):
        raise HTTPException(403, "Только администратор")
    path = create_backup_file(db, tag="manual")
    db.log_event(
        f"Backup created: {os.path.basename(path)}", "INFO", {"by": user["username"]}
    )
    return {"ok": True, "file": os.path.basename(path), "size": os.path.getsize(path)}


@router.get("/list")
def list_backups(db=Depends(get_db), user=Depends(get_current_user)):
    if not is_admin(user):
        raise HTTPException(403, "Только администратор")
    bdir = _backups_dir(db)
    items = []
    for f in sorted(os.listdir(bdir), reverse=True):
        if not f.endswith(".zip"):
            continue
        p = os.path.join(bdir, f)
        items.append(
            {
                "name": f,
                "size": os.path.getsize(p),
                "mtime": datetime.fromtimestamp(os.path.getmtime(p)).isoformat(
                    timespec="seconds"
                ),
                "tag": "auto" if f.startswith("auto_") else "manual",
            }
        )
    return {"items": items}


@router.get("/download")
def download(name: str, db=Depends(get_db), user=Depends(get_current_user)):
    if not is_admin(user):
        raise HTTPException(403, "Только администратор")
    _safe_name(name)
    p = os.path.join(_backups_dir(db), name)
    if not os.path.isfile(p):
        raise HTTPException(404, "Файл не найден")
    return FileResponse(p, filename=name, media_type="application/zip")


@router.get("/stats")
def backup_stats(name: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Предпросмотр содержимого бэкапа без восстановления."""
    if not is_admin(user):
        raise HTTPException(403, "Только администратор")
    _safe_name(name)
    p = os.path.join(_backups_dir(db), name)
    if not os.path.isfile(p):
        raise HTTPException(404, "Файл не найден")
    try:
        with zipfile.ZipFile(p) as z:
            raw = z.read("manifest.json").decode("utf-8")
        m = json.loads(raw)
    except Exception as e:
        raise HTTPException(400, f"Повреждённый архив: {e}")
    return {
        "name": name,
        "created_at": m.get("created_at"),
        "app_version": m.get("app_version"),
        "tag": m.get("tag"),
        "stats": m.get("stats", {}),
    }


@router.post("/restore")
def restore(name: str, db=Depends(get_db), user=Depends(get_current_user)):
    if not is_admin(user):
        raise HTTPException(403, "Только администратор")
    _safe_name(name)
    p = os.path.join(_backups_dir(db), name)
    if not os.path.isfile(p):
        raise HTTPException(404, "Файл не найден")

    db_path = str(db.database_path)
    tmp_dir = tempfile.mkdtemp(prefix="suot_restore_")
    try:
        with zipfile.ZipFile(p) as z:
            names = z.namelist()
            if "database.db" not in names:
                raise HTTPException(400, "В архиве нет database.db")
            z.extract("database.db", tmp_dir)
            restored_media = 0
            for n in names:
                if n.startswith("media/") and not n.endswith("/"):
                    rel = n[len("media/") :]
                    dest_root = os.path.join(os.path.dirname(db_path), "media")
                    os.makedirs(dest_root, exist_ok=True)
                    dest = os.path.normpath(os.path.join(dest_root, rel))
                    if not dest.startswith(dest_root):
                        continue  # защита от zip-slip
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with z.open(n) as srcf, open(dest, "wb") as out:
                        shutil.copyfileobj(srcf, out)
                    restored_media += 1
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Не удалось распаковать: {e}")

    new_db = os.path.join(tmp_dir, "database.db")

    # Целостность копии
    chk = sqlite3.connect(new_db)
    ok = chk.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    chk.close()
    if not ok:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(400, "База в архиве повреждена")

    # Подменяем живую базу
    db._backend.close()
    try:
        for suf in ("-wal", "-shm"):
            try:
                os.remove(db_path + suf)
            except OSError:
                pass
        shutil.copyfile(new_db, db_path)
    finally:
        db._backend.connect()
    shutil.rmtree(tmp_dir, ignore_errors=True)

    # Повторные миграции (идемпотентны)
    try:
        db.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        db.commit()
    except Exception:
        pass
    try:
        db.migrate_user_isolation()
    except Exception:
        pass

    db.log_event(
        f"Backup restored: {name}",
        "WARN",
        {"by": user["username"], "media_files": restored_media},
    )
    return {"ok": True, "media_files": restored_media}
