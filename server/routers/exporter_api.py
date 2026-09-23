"""Планировщик еженедельного автоэкспорта вида (Часть 24).

Конфигурация хранится в settings (summary: exporter_plan). Выполняется
фоновым потоком (запускается в lifespan), раз в минуту проверяет наступивший
день недели и время и сохраняет вид (колонки+фильтры) в exports/.
"""

import json
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from server.deps import get_db, get_current_user, is_admin
from services.database import DatabaseManager

router = APIRouter(prefix="/api/exporter", tags=["exporter"])

SETTING_KEY = "exporter_plan"
DEFAULT_PLAN = {
    "enabled": False,
    "weekday": 0,  # 0=Пн .. 6=Вс
    "time": "09:00",
    "table": "",  # '' → сводный реестр «Всё»
    "columns": [],  # пусто → все
    "format": "xlsx",  # xlsx | csv | json
    "title": "Реестр Всё",
}

WEEKDAYS_RU = [
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
]


def _load_plan(db: DatabaseManager) -> Dict[str, Any]:
    try:
        raw = db.get_setting(SETTING_KEY, "")
        if raw:
            return {**DEFAULT_PLAN, **json.loads(raw)}
    except (json.JSONDecodeError, TypeError):
        pass
    return dict(DEFAULT_PLAN)


def _save_plan(db: DatabaseManager, plan: Dict[str, Any]) -> None:
    db.upsert_setting(SETTING_KEY, json.dumps(plan, ensure_ascii=False))


class PlanIn(BaseModel):
    enabled: bool = False
    weekday: int = 0
    time: str = "09:00"
    table: str = ""
    columns: List[str] = []
    format: str = "xlsx"
    title: str = "Реестр Всё"


@router.get("/plan")
def get_plan(db=Depends(get_db), user=Depends(get_current_user)):
    plan = _load_plan(db)
    plan["weekday_ru"] = WEEKDAYS_RU[int(plan.get("weekday", 0)) % 7]
    return plan


@router.post("/plan")
def set_plan(body: PlanIn, db=Depends(get_db), user=Depends(get_current_user)):
    plan = dict(DEFAULT_PLAN)
    plan["enabled"] = bool(body.enabled)
    plan["weekday"] = int(body.weekday) % 7
    plan["time"] = (str(body.time) or "09:00")[:5]
    plan["table"] = str(body.table or "")
    plan["columns"] = list(body.columns or [])
    plan["format"] = str(body.format or "xlsx").lower()
    plan["title"] = str(body.title or "Реестр Всё")
    _save_plan(db, plan)
    db.log_event(f"Exporter plan saved: {plan}", "INFO")
    return plan


@router.post("/run_now")
def run_now(db=Depends(get_db), user=Depends(get_current_user)):
    # IDOR-фикс (аудит 7.2 п.7): экспорт идёт с owner=None (все данные) —
    # запуск вручную только для администратора.
    if not is_admin(user):
        raise HTTPException(403, "Только для администратора")
    plan = _load_plan(db)
    out = do_export(db, plan)
    return {"ok": True, "file": out}


def do_export(
    db: DatabaseManager, plan: Dict[str, Any], export_dir: Optional[str] = None
) -> str:
    """Выполнить экспорт по плану — вернуть имя файла в exports/."""
    from app_core.config import RUNTIME_PATHS

    directory = export_dir or str(RUNTIME_PATHS.export_dir)
    os.makedirs(directory, exist_ok=True)
    fmt = (plan.get("format") or "xlsx").lower()
    table = plan.get("table") or ""

    if table:
        rows = _collect_table_rows(db, table, plan.get("columns") or [])
        header = [c["name"] for c in db.get_columns_config(table) if c["name"] != "ID"]
        if plan.get("columns"):
            header = [c for c in header if c in plan["columns"]]
        sheet_rows = [
            {h: (r.get("data_json") or {}).get(h, "") for h in header} for r in rows
        ]
        # сортировка как в таблице
        sheet_rows.sort(key=lambda x: str(x.get(header[0], "")) if header else "")
        fname = f"{table}_{datetime.now():%Y%m%d_%H%M}.{fmt}"
    else:
        # сводный реестр «Всё»
        rows = _collect_union_rows(db, plan.get("columns") or [])
        header = ["Раздел"] + [c for c in rows["columns"] if c != "Раздел"]
        sheet_rows = rows["rows"]
        fname = f"union_{datetime.now():%Y%m%d_%H%M}.{fmt}"

    path = os.path.join(directory, fname)
    if fmt == "csv":
        import csv as _csv
        import io

        buf = io.StringIO()
        w = _csv.writer(buf, delimiter=";", quoting=_csv.QUOTE_MINIMAL)
        w.writerow(header)
        for row in sheet_rows:
            w.writerow([str(row.get(c, "") or "") for c in header])
        with open(path, "w", encoding="utf-8-sig") as f:
            f.write(buf.getvalue())
    elif fmt == "json":
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "title": plan.get("title", "Реестр Всё"),
                    "columns": header,
                    "rows": sheet_rows,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
    else:
        import io
        from openpyxl.styles import Font, PatternFill
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = (plan.get("title") or "Реестр")[:31]
        hd = PatternFill("solid", fgColor="6366F1")
        hf = Font(color="FFFFFF", bold=True, size=11)
        for i, c in enumerate(header, 1):
            cell = ws.cell(row=1, column=i, value=c)
            cell.font = hf
            cell.fill = hd
        for ri, row in enumerate(sheet_rows, 2):
            for ci, c in enumerate(header, 1):
                v = row.get(c, "")
                if isinstance(v, (dict, list)):
                    import json as _j

                    v = _j.dumps(v, ensure_ascii=False)
                ws.cell(row=ri, column=ci, value=str(v) if v is not None else "")
        ws.freeze_panes = "A2"
        wb.save(path)
    db.log_event(f"Автоэкспорт готов: {fname}", "INFO", {"file": fname, "format": fmt})
    return fname


def _collect_table_rows(db: DatabaseManager, table: str, columns: List[str]):
    if table.startswith("u_"):
        t = db.get_custom_table(table)
        if not t:
            return []
        rows = db.query_custom_records(
            table, owner_id=None, is_admin=True, page_size=20000
        )[0]
    elif table in DatabaseManager.JSON_TABLES:
        rows = db.query_json_records(
            table, owner_id=None, is_admin=True, page_size=20000
        )[0]
    else:
        rows = []
    return rows


def _collect_union_rows(db: DatabaseManager, columns: List[str]):
    from server.routers.union_api import _gather, _union_columns

    gathered = _gather(db, {"id": 0, "role": "Administrator"}, q="", only_sections=None)
    want_cols = [c for c in (columns or [])]
    section_map = _union_columns(db, {"id": 0, "role": "Administrator"})
    header = ["Раздел"] + (want_cols or section_map)
    out_rows = []
    for it in gathered:
        row = {"Раздел": it["section_label"]}
        for name in header[1:]:
            row[name] = it["data"].get(name, "")
        out_rows.append(row)
    return {"columns": header, "rows": out_rows}


# ═══ Фоновый поток ═══


class WeeklyExporterThread:
    def __init__(self, db: DatabaseManager):
        self._db = db
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        last_fired: Dict[str, str] = {}
        while self._running:
            try:
                plan = _load_plan(self._db)
                now = datetime.now()
                key = now.strftime("%Y-%m-%d")
                if plan.get("enabled") and int(plan.get("weekday", 0)) == now.weekday():
                    hh, _, mm = (plan.get("time") or "00:00").partition(":")
                    target = int(hh or 0) * 60 + int(mm or 0)
                    cur = now.hour * 60 + now.minute
                    if cur >= target and last_fired.get("day") != key:
                        try:
                            do_export(self._db, plan)
                            last_fired["day"] = key
                        except Exception:
                            pass
            except Exception:
                pass
            time.sleep(60)


_exporter_thread: Optional[WeeklyExporterThread] = None


def start_exporter_thread(db: DatabaseManager) -> WeeklyExporterThread:
    global _exporter_thread
    if _exporter_thread is None:
        _exporter_thread = WeeklyExporterThread(db)
        _exporter_thread.start()
    return _exporter_thread
