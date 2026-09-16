"""ОхранаТруда Про — FastAPI-сервер + статика веб-интерфейса."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from server.routers import (
    auth,
    data,
    demo,
    media,
    dicts,
    records,
    structured,
    custom,
    ucols,
    import_api,
    export_api,
    dashboard,
    print_api,
    print_pdf,
    search_reports,
    reminders_api,
    ai_api,
    settings_api,
    help_api,
    backup_api,
    plugins_api,
    setup_api,
    union_api,
    exporter_api,
    dash3_api,
    calendar_api,
    npa_api,
    tools_api,
    diag,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import os
    from services.database import DatabaseManager

    db_path = os.environ.get("SUOT_E2E_DB")
    db = DatabaseManager(db_path) if db_path else DatabaseManager()
    report = db.migrate_user_isolation()
    if report.get("tables_patched") or report.get("records_assigned"):
        print(f"[migration] isolation: {report}")
    # Часть 30: миграция старой Qt suot_platform.db (колонки users, sessions)
    legacy = db.migrate_legacy_qt()
    if legacy.get("patched"):
        print(f"[migration] legacy Qt: {legacy}")
    purged = db.purge_old_custom_tables(30)
    if purged:
        print(f"[trash] purged {purged} custom tables (30 days)")
    # Часть 18: флаг блокировки пользователей
    try:
        db.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        db.commit()
    except Exception:
        pass
    # Часть 21: секретный вопрос для восстановления пароля
    for col, decl in (
        ("sec_question", "TEXT DEFAULT ''"),
        ("sec_answer_hash", "TEXT DEFAULT ''"),
        ("sec_salt", "TEXT DEFAULT ''"),
    ):
        try:
            db.execute(f"ALTER TABLE users ADD COLUMN {col} {decl}")
            db.commit()
        except Exception:
            pass
    # Часть 19: авто-бэкап при старте
    if not db_path:
        try:
            from server.routers.backup_api import run_auto_backup

            p = run_auto_backup(db)
            if p:
                print(f"[backup] auto: {os.path.basename(p)}")
        except Exception as e:
            print(f"[backup] auto skipped: {e}")
    # Проверка ресурсов при запуске (first-launch / после обновления)
    if not db_path:  # в тестах не нужно
        try:
            from scripts.ensure_assets import check_and_fix

            rep = check_and_fix()
            if rep["missing"]:
                print(f"[assets] missing: {rep['missing']}")
            if rep["downloaded"]:
                print(f"[assets] downloaded: {rep['downloaded']}")
        except Exception as e:
            print(f"[assets] check skipped: {e}")
    # Часть 24: планировщик еженедельного автоэкспорта
    if not db_path:
        try:
            from server.routers.exporter_api import start_exporter_thread

            start_exporter_thread(db)
        except Exception as e:
            print(f"[exporter] start skipped: {e}")
    yield


app = FastAPI(title="ОхранаТруда Про", version="2.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8899", "http://localhost:8899"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(data.router)
app.include_router(demo.router)
app.include_router(media.router)
app.include_router(dicts.router)
app.include_router(records.router)
app.include_router(structured.router)
app.include_router(custom.router)
app.include_router(ucols.router)
app.include_router(import_api.router)
app.include_router(export_api.router)
app.include_router(dashboard.router)
app.include_router(print_api.router)
app.include_router(print_pdf.router)
app.include_router(search_reports.router)
app.include_router(reminders_api.router)
app.include_router(ai_api.router)
app.include_router(settings_api.router)
app.include_router(help_api.router)
app.include_router(backup_api.router)
app.include_router(plugins_api.router)
app.include_router(setup_api.router)
app.include_router(union_api.router)
app.include_router(exporter_api.router)
app.include_router(dash3_api.router)
app.include_router(calendar_api.router)
app.include_router(npa_api.router)
app.include_router(tools_api.router)
app.include_router(diag.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "suot-neo"}


# Медиа-файлы (фото) — монтируются ДО "/", иначе перехватываются им
from app_core.config import RUNTIME_PATHS  # noqa: E402

os.makedirs(str(RUNTIME_PATHS.media_dir), exist_ok=True)
app.mount("/media", StaticFiles(directory=str(RUNTIME_PATHS.media_dir)), name="media")


def _asset_root() -> str:
    import sys

    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(__file__))


WEB_DIR = os.path.join(_asset_root(), "web")
if os.path.isdir(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
