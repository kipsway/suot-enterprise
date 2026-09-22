"""Глобальный поиск + конструктор отчётов (Часть 14)."""

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from server.deps import get_db, get_current_user, is_admin
from services.database import DatabaseManager
from app_core.utils import JsonUtils

router = APIRouter(prefix="/api", tags=["search+reports"])


def _scope(user):
    uid = None if is_admin(user) else int(user["id"])
    return uid, is_admin(user)


# ═══ Глобальный поиск ═══


@router.get("/search")
def global_search(q: str, db=Depends(get_db), user=Depends(get_current_user)):
    if not q.strip() or len(q.strip()) < 2:
        return {"results": []}
    uid, admin = _scope(user)
    q_lower = q.strip().lower()
    results: List[Dict[str, Any]] = []
    for table in sorted(DatabaseManager.JSON_TABLES):
        try:
            rows, _ = db.query_json_records(
                table, owner_id=uid, is_admin=admin, q=q.strip(), page_size=10
            )
        except Exception:
            continue
        for r in rows[:5]:
            dj = r.get("data_json") or {}
            title = str(
                dj.get(
                    "ФИО",
                    dj.get(
                        "Описание",
                        dj.get(
                            "Наименование",
                            dj.get(
                                "title",
                                dj.get(
                                    "Название",
                                    dj.get("Тема", dj.get("Номер наряда", "")),
                                ),
                            ),
                        ),
                    ),
                )
            ).strip()[:80]
            if not title:
                title = f"#{r['id']}"
            # найти совпавшее поле для подсветки
            matched_field = ""
            for k, v in dj.items():
                if q_lower in str(v or "").lower():
                    matched_field = k
                    break
            results.append(
                {
                    "table": table,
                    "id": r["id"],
                    "title": title,
                    "matched_field": matched_field,
                    "snippet": _snippet(dj, q_lower),
                }
            )
    # Правовая база (Часть 26): поиск по НПА
    from services.npa_seed import npa_hay_match

    try:
        npa_rows = db.fetch_all(
            "SELECT * FROM npa_documents ORDER BY date DESC, id LIMIT 600"
        )
        for r in npa_rows:
            hay = (
                f"{r['kind']} {r['number']} {r['title']} {r['category']} "
                f"{r['audience']} {r['notes']}"
            ).lower()
            if npa_hay_match(q, hay):
                results.append(
                    {
                        "table": "npa",
                        "id": r["id"],
                        "title": f"[{r['kind']}] {r['number']} {r['title']}".strip()[
                            :100
                        ],
                        "matched_field": "НПА",
                        "snippet": _snippet(
                            {
                                "Номер": r["number"],
                                "Название": r["title"],
                                "Категория": r["category"],
                                "Статус": r["status"],
                                "Примечание": r["notes"],
                            },
                            q_lower,
                        ),
                    }
                )
                if sum(1 for x in results if x.get("table") == "npa") >= 8:
                    break
    except Exception:
        pass
    results.sort(key=lambda x: x["title"])
    return {"results": results[:40], "query": q}


def _snippet(dj: dict, q: str) -> str:
    for v in dj.values():
        s = str(v or "")
        idx = s.lower().find(q)
        if idx >= 0:
            start = max(0, idx - 20)
            return ("…" if start > 0 else "") + s[start : idx + len(q) + 30] + "…"
    return ""


# ═══ Конструктор отчётов ═══


class ReportIn(BaseModel):
    table: str
    columns: List[str] = []
    filters: Dict[str, List[str]] = {}
    group_by: str = ""
    aggregate: str = "count"  # count | sum | avg | min | max
    aggregate_field: str = ""
    q: str = ""


@router.post("/reports/run")
def run_report(body: ReportIn, db=Depends(get_db), user=Depends(get_current_user)):
    if body.table not in DatabaseManager.JSON_TABLES:
        raise HTTPException(404, "Неизвестная таблица")
    uid, admin = _scope(user)
    rows, total = db.query_json_records(
        body.table,
        owner_id=uid,
        is_admin=admin,
        q=body.q,
        filters=body.filters,
        page_size=5000,
    )
    # фильтрация по колонкам
    if body.columns:
        rows = [
            {
                **r,
                "data_json": {
                    k: v
                    for k, v in (r.get("data_json") or {}).items()
                    if k in body.columns
                },
            }
            for r in rows
        ]

    # группировка
    if body.group_by:
        groups: Dict[str, List[Dict]] = {}
        for r in rows:
            gv = str(r.get(body.group_by, "") or "(пусто)")
            groups.setdefault(gv, []).append(r)
        agg_results = []
        for gv, grp in sorted(groups.items()):
            agg_val = _aggregate(grp, body.aggregate, body.aggregate_field)
            agg_results.append(
                {
                    "group": gv,
                    "count": len(grp),
                    "aggregate": agg_val,
                    "aggregate_label": f"{body.aggregate}({body.aggregate_field})"
                    if body.aggregate_field
                    else body.aggregate,
                }
            )
        return {
            "mode": "grouped",
            "total": len(rows),
            "groups": agg_results,
            "columns": body.columns or _default_cols(db, body.table),
        }

    # без группировки — просто данные
    items = []
    for r in rows[:200]:
        data = r.get("data_json") or {}
        if body.columns:
            data = {k: v for k, v in data.items() if k in body.columns}
        items.append({"id": r["id"], **data})
    return {
        "mode": "flat",
        "total": len(rows),
        "items": items,
        "columns": body.columns or _default_cols(db, body.table),
    }


def _aggregate(rows: List[Dict], func: str, field: str) -> Any:
    if func == "count" or not field:
        return len(rows)
    vals = []
    for r in rows:
        try:
            v = float(r.get(field, 0) or 0)
            vals.append(v)
        except (ValueError, TypeError):
            continue
    if not vals:
        return 0
    if func == "sum":
        return round(sum(vals), 2)
    if func == "avg":
        return round(sum(vals) / len(vals), 2)
    if func == "min":
        return min(vals)
    if func == "max":
        return max(vals)
    return len(rows)


def _default_cols(db, table):
    return [c["name"] for c in db.get_columns_config(table) if c["name"] != "ID"][:8]


# ═══ Быстрые фильтры ═══


@router.get("/quick_filters/{table}")
def quick_filters(table: str, db=Depends(get_db), user=Depends(get_current_user)):
    """Предопределённые быстрые фильтры для таблицы."""
    uid, admin = _scope(user)
    filters = []
    if table in DatabaseManager.JSON_TABLES:
        rows, _ = db.query_json_records(
            table, owner_id=uid, is_admin=admin, page_size=5000
        )
        has_status = any("Статус" in (r.get("data_json") or {}) for r in rows)
        has_dates = any(
            any(
                f in (r.get("data_json") or {})
                for f in (
                    "Срок устранения",
                    "Дата медосмотра",
                    "Срок замены",
                    "Срок действия",
                    "Дата окончания",
                )
            )
            for r in rows
        )
        if has_status:
            filters.append(
                {
                    "key": "active",
                    "label": "Активные",
                    "field": "Статус",
                    "values": ["Активно", "Активен", "Active", "В работе", "open"],
                }
            )
            filters.append(
                {
                    "key": "done",
                    "label": "Устранённые",
                    "field": "Статус",
                    "values": [
                        "Устранено",
                        "Исполнено",
                        "Resolved",
                        "Выполнено",
                        "closed",
                    ],
                }
            )
        if has_dates:
            filters.append(
                {
                    "key": "overdue",
                    "label": "Просроченные",
                    "field": "_overdue",
                    "values": [],
                }
            )
        filters.append(
            {"key": "mine", "label": "Только мои", "field": "_mine", "values": []}
        )
    return {"filters": filters}
