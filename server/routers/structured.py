"""Структурированные разделы: чек-листы (+шаблоны, результаты),
CAPA (с цепочкой), протоколы, риски, справочник сокращений."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from server.deps import get_db, get_current_user, is_admin
from services.database import DatabaseManager

router = APIRouter(prefix="/api/s", tags=["structured"])

# таблицы с изоляцией по владельцу
OWNED = {
    "ot_protocols",
    "inspection_checklists",
    "inspection_results",
    "capa_records",
    "risk_assessments",
}


def _own_sql(user: dict):
    if is_admin(user):
        return "1=1", []
    return "(user_id=? OR user_id=0)", [int(user["id"])]


def _assert_owned(db: DatabaseManager, table: str, rid: int, user: dict) -> None:
    row = db.fetch_one(f"SELECT user_id FROM {table} WHERE id=?", (rid,))
    if not row:
        raise HTTPException(404, "Запись не найдена")
    owner = int(row["user_id"] or 0)
    if owner != 0 and owner != int(user["id"]) and not is_admin(user):
        raise HTTPException(403, "Нет доступа")


def _ins(db: DatabaseManager, table: str, values: Dict[str, Any], user: dict) -> int:
    cols = ", ".join(values.keys())
    ph = ", ".join("?" for _ in values)
    cur = db.execute(
        f"INSERT INTO {table} ({cols}, user_id) VALUES ({ph}, ?)",
        tuple(values.values()) + (int(user["id"]),),
    )
    db.commit()
    return int(cur.lastrowid)


# ═══ Справочник сокращений (общий) ═══


@router.get("/textbook")
def tb_list(db=Depends(get_db), user=Depends(get_current_user)):
    data = db.get_textbook()
    return {
        "items": [{"short_code": k, "full_text": v} for k, v in sorted(data.items())]
    }


class TbIn(BaseModel):
    short_code: str
    full_text: str = ""


@router.post("/textbook", status_code=201)
def tb_add(body: TbIn, db=Depends(get_db), user=Depends(get_current_user)):
    code = body.short_code.strip()
    if not code:
        raise HTTPException(400, "Пустой код")
    if db.fetch_one("SELECT id FROM textbook WHERE short_code=?", (code,)):
        raise HTTPException(409, "Такой код уже есть")
    db.save_textbook_entry(code, body.full_text)
    return {"ok": True}


@router.put("/textbook/{code}")
def tb_update(
    code: str, body: TbIn, db=Depends(get_db), user=Depends(get_current_user)
):
    if not db.fetch_one("SELECT id FROM textbook WHERE short_code=?", (code,)):
        raise HTTPException(404, "Не найдено")
    db.save_textbook_entry(code, body.full_text)
    return {"ok": True}


@router.delete("/textbook/{code}")
def tb_del(code: str, db=Depends(get_db), user=Depends(get_current_user)):
    db.delete_textbook_entry(code)
    return {"ok": True}


# ═══ Чек-листы ═══


class ChecklistIn(BaseModel):
    title: str
    description: str = ""
    is_template: bool = False
    items: List[str] = []


@router.get("/checklists")
def cl_list(mode: str = "all", db=Depends(get_db), user=Depends(get_current_user)):
    where, params = _own_sql(user)
    if mode == "templates":
        where += " AND is_template=1"
    elif mode == "checklists":
        where += " AND is_template=0"
    rows = db.fetch_all(
        f"SELECT c.id, c.title, c.description, c.is_template, "
        f"(SELECT COUNT(*) FROM checklist_items i "
        f" WHERE i.checklist_id=c.id) AS items_count "
        f"FROM inspection_checklists c WHERE {where} ORDER BY c.id DESC",
        tuple(params),
    )
    return {"items": [dict(r) for r in rows]}


@router.get("/checklists/{clid}")
def cl_get(clid: int, db=Depends(get_db), user=Depends(get_current_user)):
    _assert_owned(db, "inspection_checklists", clid, user)
    c = db.fetch_one(
        "SELECT id, title, description, is_template "
        "FROM inspection_checklists WHERE id=?",
        (clid,),
    )
    items = db.fetch_all(
        "SELECT id, item_text, position FROM checklist_items "
        "WHERE checklist_id=? ORDER BY position",
        (clid,),
    )
    results = db.fetch_all(
        "SELECT id, conducted_date, conducted_by, notes, status "
        "FROM inspection_results WHERE checklist_id=? ORDER BY id DESC",
        (clid,),
    )
    return {
        "checklist": dict(c),
        "items": [dict(i) for i in items],
        "results": [dict(r) for r in results],
    }


@router.post("/checklists", status_code=201)
def cl_create(body: ChecklistIn, db=Depends(get_db), user=Depends(get_current_user)):
    if not body.title.strip():
        raise HTTPException(400, "Укажите название")
    clid = _ins(
        db,
        "inspection_checklists",
        {
            "title": body.title.strip(),
            "description": body.description,
            "is_template": 1 if body.is_template else 0,
        },
        user,
    )
    for pos, text in enumerate(body.items):
        if text.strip():
            db.execute(
                "INSERT INTO checklist_items (checklist_id, item_text, "
                "position) VALUES (?, ?, ?)",
                (clid, text.strip(), pos),
            )
    db.commit()
    return {"id": clid}


@router.put("/checklists/{clid}")
def cl_update(
    clid: int, body: ChecklistIn, db=Depends(get_db), user=Depends(get_current_user)
):
    _assert_owned(db, "inspection_checklists", clid, user)
    db.execute(
        "UPDATE inspection_checklists SET title=?, description=? WHERE id=?",
        (body.title.strip(), body.description, clid),
    )
    db.execute("DELETE FROM checklist_items WHERE checklist_id=?", (clid,))
    for pos, text in enumerate(body.items):
        if text.strip():
            db.execute(
                "INSERT INTO checklist_items (checklist_id, item_text, "
                "position) VALUES (?, ?, ?)",
                (clid, text.strip(), pos),
            )
    db.commit()
    return {"ok": True}


@router.delete("/checklists/{clid}")
def cl_delete(clid: int, db=Depends(get_db), user=Depends(get_current_user)):
    _assert_owned(db, "inspection_checklists", clid, user)
    db.execute("DELETE FROM checklist_items WHERE checklist_id=?", (clid,))
    db.execute(
        "DELETE FROM inspection_result_items WHERE result_id IN "
        "(SELECT id FROM inspection_results WHERE checklist_id=?)",
        (clid,),
    )
    db.execute("DELETE FROM inspection_results WHERE checklist_id=?", (clid,))
    db.execute("DELETE FROM inspection_checklists WHERE id=?", (clid,))
    db.commit()
    return {"ok": True}


@router.post("/checklists/{clid}/save_as_template", status_code=201)
def cl_save_as_template(clid: int, db=Depends(get_db), user=Depends(get_current_user)):
    _assert_owned(db, "inspection_checklists", clid, user)
    src = db.fetch_one(
        "SELECT title, description FROM inspection_checklists WHERE id=?", (clid,)
    )
    new_id = _ins(
        db,
        "inspection_checklists",
        {
            "title": src["title"] + " (шаблон)",
            "description": src["description"],
            "is_template": 1,
        },
        user,
    )
    db.execute(
        "INSERT INTO checklist_items (checklist_id, item_text, position) "
        "SELECT ?, item_text, position FROM checklist_items "
        "WHERE checklist_id=?",
        (new_id, clid),
    )
    db.commit()
    return {"id": new_id}


@router.post("/checklists/from_template/{tpl_id}", status_code=201)
def cl_from_template(tpl_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    _assert_owned(db, "inspection_checklists", tpl_id, user)
    src = db.fetch_one(
        "SELECT title, description FROM inspection_checklists WHERE id=?", (tpl_id,)
    )
    new_id = _ins(
        db,
        "inspection_checklists",
        {"title": src["title"], "description": src["description"], "is_template": 0},
        user,
    )
    db.execute(
        "INSERT INTO checklist_items (checklist_id, item_text, position) "
        "SELECT ?, item_text, position FROM checklist_items "
        "WHERE checklist_id=?",
        (new_id, tpl_id),
    )
    db.commit()
    return {"id": new_id}


class ResultIn(BaseModel):
    conducted_by: str = ""
    notes: str = ""
    answers: List[Dict[str, Any]] = []


@router.post("/checklists/{clid}/results", status_code=201)
def cl_add_result(
    clid: int, body: ResultIn, db=Depends(get_db), user=Depends(get_current_user)
):
    _assert_owned(db, "inspection_checklists", clid, user)
    has_fail = any(a.get("value") == "fail" for a in body.answers)
    status = "fail" if has_fail else "pass"
    rid = _ins(
        db,
        "inspection_results",
        {
            "checklist_id": clid,
            "conducted_by": body.conducted_by,
            "notes": body.notes,
            "status": status,
        },
        user,
    )
    for a in body.answers:
        db.execute(
            "INSERT INTO inspection_result_items (result_id, item_id, "
            "value, comment) VALUES (?, ?, ?, ?)",
            (rid, a.get("item_id"), a.get("value", "na"), a.get("comment", "")),
        )
    db.commit()
    return {"id": rid, "status": status}


@router.get("/results/{rid}")
def result_get(rid: int, db=Depends(get_db), user=Depends(get_current_user)):
    _assert_owned(db, "inspection_results", rid, user)
    r = db.fetch_one("SELECT * FROM inspection_results WHERE id=?", (rid,))
    items = db.fetch_all(
        "SELECT ri.item_id, ri.value, ri.comment, i.item_text "
        "FROM inspection_result_items ri "
        "LEFT JOIN checklist_items i ON i.id = ri.item_id "
        "WHERE ri.result_id=?",
        (rid,),
    )
    return {"result": dict(r), "answers": [dict(i) for i in items]}


@router.delete("/results/{rid}")
def result_del(rid: int, db=Depends(get_db), user=Depends(get_current_user)):
    _assert_owned(db, "inspection_results", rid, user)
    db.execute("DELETE FROM inspection_result_items WHERE result_id=?", (rid,))
    db.execute("DELETE FROM inspection_results WHERE id=?", (rid,))
    db.commit()
    return {"ok": True}


# ═══ CAPA ═══


class CapaIn(BaseModel):
    title: str
    description: str = ""
    root_cause: str = ""
    action_plan: str = ""
    effectiveness: str = ""
    severity: str = "medium"
    status: str = "open"
    assigned_to: str = ""
    deadline: str = ""


CAPA_FIELDS = (
    "title",
    "description",
    "root_cause",
    "action_plan",
    "effectiveness",
    "severity",
    "status",
    "assigned_to",
    "deadline",
)


@router.get("/capa")
def capa_list(status: str = "", db=Depends(get_db), user=Depends(get_current_user)):
    where, params = _own_sql(user)
    if status:
        where += " AND status=?"
        params.append(status)
    rows = db.fetch_all(
        f"SELECT * FROM capa_records WHERE {where} ORDER BY id DESC", tuple(params)
    )
    return {"items": [dict(r) for r in rows]}


@router.get("/capa/{cid}")
def capa_get(cid: int, db=Depends(get_db), user=Depends(get_current_user)):
    _assert_owned(db, "capa_records", cid, user)
    r = db.fetch_one("SELECT * FROM capa_records WHERE id=?", (cid,))
    links = db.get_record_links("capa_records", cid)
    return {"record": dict(r), "links": [dict(l) for l in links]}


@router.post("/capa", status_code=201)
def capa_create(body: CapaIn, db=Depends(get_db), user=Depends(get_current_user)):
    if not body.title.strip():
        raise HTTPException(400, "Укажите название")
    values = {f: getattr(body, f) for f in CAPA_FIELDS}
    return {"id": _ins(db, "capa_records", values, user)}


@router.put("/capa/{cid}")
def capa_update(
    cid: int, body: CapaIn, db=Depends(get_db), user=Depends(get_current_user)
):
    _assert_owned(db, "capa_records", cid, user)
    sets = ", ".join(f"{f}=?" for f in CAPA_FIELDS)
    db.execute(
        f"UPDATE capa_records SET {sets} WHERE id=?",
        tuple(getattr(body, f) for f in CAPA_FIELDS) + (cid,),
    )
    db.commit()
    return {"ok": True}


@router.delete("/capa/{cid}")
def capa_delete(cid: int, db=Depends(get_db), user=Depends(get_current_user)):
    _assert_owned(db, "capa_records", cid, user)
    db.execute("DELETE FROM capa_records WHERE id=?", (cid,))
    db.commit()
    return {"ok": True}


# ═══ Протоколы ═══


class ProtocolIn(BaseModel):
    date: str = ""
    topic: str
    participants: str = ""
    agenda: str = ""
    decisions: str = ""
    status: str = "active"


PROTOCOL_FIELDS = ("date", "topic", "participants", "agenda", "decisions", "status")


@router.get("/protocols")
def prot_list(db=Depends(get_db), user=Depends(get_current_user)):
    where, params = _own_sql(user)
    rows = db.fetch_all(
        f"SELECT * FROM ot_protocols WHERE {where} ORDER BY id DESC", tuple(params)
    )
    return {"items": [dict(r) for r in rows]}


@router.post("/protocols", status_code=201)
def prot_create(body: ProtocolIn, db=Depends(get_db), user=Depends(get_current_user)):
    if not body.topic.strip():
        raise HTTPException(400, "Укажите тему")
    values = {f: getattr(body, f) for f in PROTOCOL_FIELDS}
    return {"id": _ins(db, "ot_protocols", values, user)}


@router.put("/protocols/{pid}")
def prot_update(
    pid: int, body: ProtocolIn, db=Depends(get_db), user=Depends(get_current_user)
):
    _assert_owned(db, "ot_protocols", pid, user)
    sets = ", ".join(f"{f}=?" for f in PROTOCOL_FIELDS)
    db.execute(
        f"UPDATE ot_protocols SET {sets} WHERE id=?",
        tuple(getattr(body, f) for f in PROTOCOL_FIELDS) + (pid,),
    )
    db.commit()
    return {"ok": True}


@router.delete("/protocols/{pid}")
def prot_delete(pid: int, db=Depends(get_db), user=Depends(get_current_user)):
    _assert_owned(db, "ot_protocols", pid, user)
    db.execute("DELETE FROM ot_protocols WHERE id=?", (pid,))
    db.commit()
    return {"ok": True}


# ═══ Риски ═══


class RiskIn(BaseModel):
    title: str
    description: str = ""
    category: str = ""
    probability: int = 1
    consequence: int = 1
    mitigation: str = ""
    status: str = "active"


RISK_FIELDS = (
    "title",
    "description",
    "category",
    "probability",
    "consequence",
    "risk_level",
    "mitigation",
    "status",
)


def risk_level(p: int, c: int) -> int:
    return max(1, min(5, p)) * max(1, min(5, c))


@router.get("/risks")
def risk_list(db=Depends(get_db), user=Depends(get_current_user)):
    where, params = _own_sql(user)
    rows = db.fetch_all(
        f"SELECT * FROM risk_assessments WHERE {where} ORDER BY id DESC", tuple(params)
    )
    return {"items": [dict(r) for r in rows]}


@router.post("/risks", status_code=201)
def risk_create(body: RiskIn, db=Depends(get_db), user=Depends(get_current_user)):
    if not body.title.strip():
        raise HTTPException(400, "Укажите название")
    values = {f: getattr(body, f) for f in RISK_FIELDS if f != "risk_level"}
    values["risk_level"] = risk_level(body.probability, body.consequence)
    return {"id": _ins(db, "risk_assessments", values, user)}


@router.put("/risks/{rid}")
def risk_update(
    rid: int, body: RiskIn, db=Depends(get_db), user=Depends(get_current_user)
):
    _assert_owned(db, "risk_assessments", rid, user)
    values = {f: getattr(body, f) for f in RISK_FIELDS if f != "risk_level"}
    values["risk_level"] = risk_level(body.probability, body.consequence)
    sets = ", ".join(f"{f}=?" for f in values)
    db.execute(
        f"UPDATE risk_assessments SET {sets} WHERE id=?",
        tuple(values.values()) + (rid,),
    )
    db.commit()
    return {"ok": True}


@router.delete("/risks/{rid}")
def risk_delete(rid: int, db=Depends(get_db), user=Depends(get_current_user)):
    _assert_owned(db, "risk_assessments", rid, user)
    db.execute("DELETE FROM risk_assessments WHERE id=?", (rid,))
    db.commit()
    return {"ok": True}
