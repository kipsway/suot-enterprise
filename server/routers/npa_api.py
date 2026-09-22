"""Правовая база (Часть 26): каталог НПА по охране труда, фасетный поиск,
избранное, конспекты и импорт списком."""

import re
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from server.deps import get_db, get_current_user, is_admin
from services.database import DatabaseManager
from services.npa_seed import NPA_KINDS, NPA_STATUSES

router = APIRouter(prefix="/api/npa", tags=["legal-base"])

KIND_LABELS = {
    "кодекс": "Кодексы",
    "ФЗ": "Федеральные законы",
    "приказ": "Приказы",
    "постановление": "Постановления",
    "СП": "СП / СанПиН",
}
DEFAULT_CATEGORY = "Общее"


class NpaIn(BaseModel):
    parent_id: int = 0
    kind: str = "приказ"
    number: str = ""
    title: str = ""
    date: str = ""
    status: str = "действует"
    category: str = ""
    audience: str = ""
    url: str = ""
    notes: str = ""


class NpaImportIn(BaseModel):
    items: List[NpaIn] = []
    csv: str = ""


def _norm_kind(k: str) -> str:
    k = (k or "").strip()
    if not k:
        return "приказ"
    if k in NPA_KINDS:
        return k
    low = k.lower()
    for cand in NPA_KINDS:
        if low in cand.lower():
            return cand
    return "приказ"


def _norm_status(s: str) -> str:
    s = (s or "").strip()
    if not s or s not in NPA_STATUSES:
        return "действует"
    return s


def _validate_year(date_str: str) -> str:
    """Строго: принять YYYY или DD.MM.YYYY; вернуть YYYY или ''."""
    if not date_str:
        return ""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", date_str)
    if m:
        return m.group(1)
    m2 = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", date_str)
    if m2:
        return m2.group(3)
    m3 = re.fullmatch(r"(\d{4})", date_str)
    if m3:
        return m3.group(1)
    return ""


def _parse_csv(text: str) -> List[Dict[str, Any]]:
    """Разбор CSV-списка НПА. Формат строки:
    kind;number;title;date;status;category
    Первая строка может быть заголовком (колонки kind,number,...)."""
    rows: List[Dict[str, Any]] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) == 1:
            parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        if parts[0].lower() in ("kind", "вид"):
            continue
        kind, number, title = parts[0], parts[1], parts[2]
        date = parts[3] if len(parts) > 3 else ""
        status = parts[4] if len(parts) > 4 else ""
        category = parts[5] if len(parts) > 5 else ""
        rows.append(
            {
                "kind": kind,
                "number": number,
                "title": title,
                "date": date,
                "status": status,
                "category": category,
            }
        )
    return rows


def _year_part(date_str: str) -> str:
    """Извлечь год из DD.MM.YYYY / YYYY-MM-DD / YYYY."""
    d = (date_str or "").strip()
    if len(d) == 10:
        if d[2] == ".":
            return d[6:10]
        if d[4] == "-":
            return d[0:4]
    if len(d) == 4 and d.isdigit():
        return d
    return ""


def _row_out(db: DatabaseManager, rec: Dict[str, Any], user_id: int) -> Dict[str, Any]:
    """Привести строку к JSON с флагом избранного для текущего пользователя."""
    out = dict(rec)
    favs = db.fetch_all("SELECT npa_id FROM npa_favs WHERE user_id=?", (user_id,))
    fav_ids = {r["npa_id"] for r in favs}
    out["is_fav"] = out["id"] in fav_ids
    out["kind_label"] = KIND_LABELS.get(out.get("kind"), out.get("kind"))
    return out


@router.get("/list")
def npa_list(
    q: str = "",
    kind: str = "",
    category: str = "",
    status: str = "",
    year: str = "",
    fav: str = "",
    limit: int = 500,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    uid = int(user["id"])
    rows = db.fetch_all("SELECT * FROM npa_documents ORDER BY date DESC, id")
    favs = {
        r["npa_id"]
        for r in db.fetch_all("SELECT npa_id FROM npa_favs WHERE user_id=?", (uid,))
    }
    q_l = (q or "").strip().lower()
    kind = _norm_kind(kind) if kind else ""
    status = _norm_status(status) if status else ""
    year = _validate_year(year) if year else ""
    fav_only = fav in ("1", "true")
    out: List[Dict[str, Any]] = []
    for r in rows:
        rec = _row_out(db, r, uid)
        if kind and rec["kind"] != kind:
            continue
        if category and rec.get("category") != category:
            continue
        if status and rec["status"] != status:
            continue
        if year and _year_part(rec.get("date", "")) != year:
            continue
        if fav_only and not rec["is_fav"]:
            continue
        if q_l:
            from services.npa_seed import npa_hay_match

            hay = (
                str(rec.get("number", ""))
                + " "
                + str(rec.get("title", ""))
                + " "
                + str(rec.get("kind", ""))
                + " "
                + str(rec.get("category", ""))
                + " "
                + str(rec.get("audience", ""))
                + " "
                + str(rec.get("notes", ""))
            )
            if not npa_hay_match(q, hay):
                continue
        out.append(rec)
    return {"items": out[:limit], "total": len(out)}


@router.get("/facets")
def npa_facets(db=Depends(get_db), user=Depends(get_current_user)):
    rows = db.fetch_all("SELECT * FROM npa_documents ORDER BY id")
    km: Dict[str, int] = {}
    cm: Dict[str, int] = {}
    sm: Dict[str, int] = {}
    ym: Dict[str, int] = {}
    for r in rows:
        k = str(r["kind"])
        km[k] = km.get(k, 0) + 1
        c = str(r["category"] or DEFAULT_CATEGORY)
        cm[c] = cm.get(c, 0) + 1
        s = str(r["status"])
        sm[s] = sm.get(s, 0) + 1
        y = _year_part(str(r["date"] or ""))
        if y:
            ym[y] = ym.get(y, 0) + 1
    cats_sorted = sorted(cm.items(), key=lambda x: (-x[1], x[0]))
    res_cats = [{"value": c, "count": n} for c, n in cats_sorted]
    years_sorted = sorted(ym.items(), key=lambda x: -int(x[0] or 0))
    return {
        "kinds": [
            {"value": k, "count": n, "label": KIND_LABELS.get(k, k)}
            for k, n in sorted(km.items())
        ],
        "categories": res_cats,
        "statuses": [{"value": k, "count": n} for k, n in sorted(sm.items())],
        "years": [{"value": y, "count": n} for y, n in years_sorted],
    }


@router.get("/{doc_id}")
def npa_detail(doc_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    rec = db.npa_get(doc_id)
    if not rec:
        raise HTTPException(404, "Документ не найден")
    return {"item": _row_out(db, rec, int(user["id"]))}


@router.post("")
def npa_create(body: NpaIn, db=Depends(get_db), user=Depends(get_current_user)):
    if not is_admin(user):
        raise HTTPException(403, "Добавлять документы может администратор")
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(400, "Укажите название документа")
    data: Dict[str, Any] = {
        "parent_id": int(body.parent_id or 0),
        "kind": _norm_kind(body.kind),
        "number": (body.number or "").strip()[:60],
        "title": title[:300],
        "date": (body.date or "").strip()[:10],
        "status": _norm_status(body.status),
        "category": (body.category or "").strip()[:60] or DEFAULT_CATEGORY,
        "audience": (body.audience or "").strip()[:120],
        "url": (body.url or "").strip()[:300],
        "notes": (body.notes or "").strip(),
    }
    new_id = db.npa_save(data, 0)
    db.log_event("NPA document created", "INFO", {"id": new_id, "title": title})
    return {"id": new_id}


@router.put("/{doc_id}")
def npa_update(
    doc_id: int, body: NpaIn, db=Depends(get_db), user=Depends(get_current_user)
):
    if not is_admin(user):
        raise HTTPException(403, "Редактировать документы может администратор")
    cur = db.npa_get(doc_id)
    if not cur:
        raise HTTPException(404, "Документ не найден")
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(400, "Укажите название документа")
    data: Dict[str, Any] = {
        "parent_id": int(body.parent_id or cur.get("parent_id") or 0),
        "kind": _norm_kind(body.kind),
        "number": (body.number or "").strip()[:60],
        "title": title[:300],
        "date": (body.date or "").strip()[:10],
        "status": _norm_status(body.status),
        "category": (body.category or "").strip()[:60] or DEFAULT_CATEGORY,
        "audience": (body.audience or "").strip()[:120],
        "url": (body.url or "").strip()[:300],
        "notes": (body.notes or "").strip(),
    }
    db.npa_save(data, doc_id)
    db.log_event("NPA document updated", "INFO", {"id": doc_id})
    return {"ok": True}


@router.delete("/{doc_id}")
def npa_delete(doc_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    if not is_admin(user):
        raise HTTPException(403, "Удалять документы может администратор")
    if not db.npa_delete(doc_id):
        raise HTTPException(404, "Документ не найден")
    return {"ok": True}


@router.post("/{doc_id}/fav")
def npa_toggle_fav(doc_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    cur = db.npa_get(doc_id)
    if not cur:
        raise HTTPException(404, "Документ не найден")
    fav = db.npa_toggle_fav(int(user["id"]), doc_id)
    db.log_event("NPA fav" if fav else "NPA unfav", "INFO", {"id": doc_id})
    return {"is_fav": fav, "id": doc_id}


@router.post("/import")
def npa_import(body: NpaImportIn, db=Depends(get_db), user=Depends(get_current_user)):
    """Импорт списком: JSON {"items": [...]} или CSV-текст {csv: "...",
    строки: kind;number;title;date;status;category. Только для администратора."""
    if not is_admin(user):
        raise HTTPException(403, "Импортировать документы может администратор")
    items: List[Dict[str, Any]] = []
    if body.items:
        items = [item.model_dump() for item in body.items]
    elif body.csv.strip():
        items = _parse_csv(body.csv)
    else:
        raise HTTPException(400, "Пустой список")
    if not items:
        raise HTTPException(400, "Пустой список")
    count = 0
    for item in items:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        data: Dict[str, Any] = {
            "parent_id": int(item.get("parent_id") or 0),
            "kind": _norm_kind(item.get("kind")),
            "number": (item.get("number") or "").strip()[:60],
            "title": title[:300],
            "date": (item.get("date") or "").strip()[:10],
            "status": _norm_status(item.get("status")),
            "category": (item.get("category") or "").strip()[:60] or DEFAULT_CATEGORY,
            "audience": (item.get("audience") or "").strip()[:120],
            "url": (item.get("url") or "").strip()[:300],
            "notes": (item.get("notes") or "").strip(),
        }
        db.npa_save(data, 0)
        count += 1
    db.log_event("NPA bulk import", "INFO", {"count": count})
    return {"imported": count}
