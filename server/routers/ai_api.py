"""AI-модуль: чат (Ollama/OpenAI-совместимый), инсайты, агент с инструментами.

Все запросы проксируются через сервер → ключи не попадают в браузер.
Стриминг — Server-Sent Events.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from server.deps import get_db, get_current_user, is_admin
from services.database import DatabaseManager

router = APIRouter(prefix="/api/ai", tags=["ai"])


# ── Настройки ──


class AISettings(BaseModel):
    provider: str = "ollama"  # ollama | openai
    base_url: str = "http://localhost:11434"
    api_key: str = ""
    model: str = "llama3"


@router.get("/settings")
def get_settings(db=Depends(get_db), user=Depends(get_current_user)):
    s = {
        k: db.get_setting(f"ai_{k}", v)
        for k, v in {
            "provider": "ollama",
            "base_url": "http://localhost:11434",
            "api_key": "",
            "model": "llama3",
        }.items()
    }
    # Ключ — секрет администратора: обычным пользователям его не показываем.
    if not is_admin(user):
        s["api_key"] = ""
    s["api_key_set"] = bool(db.get_setting("ai_api_key", ""))
    return s


@router.post("/settings")
def save_settings(body: AISettings, db=Depends(get_db), user=Depends(get_current_user)):
    if not is_admin(user):
        raise HTTPException(403, "Только администратор")
    for k, v in body.dict().items():
        db.upsert_setting(f"ai_{k}", v)
    return {"ok": True}


def _get_ai_settings(db):
    return {
        "provider": db.get_setting("ai_provider", "ollama"),
        "base_url": db.get_setting("ai_base_url", "http://localhost:11434"),
        "api_key": db.get_setting("ai_api_key", ""),
        "model": db.get_setting("ai_model", "llama3"),
    }


async def _call_llm(messages: List[Dict], settings: Dict, stream: bool = False):
    """Единый вызов LLM (Ollama или OpenAI-совместимый)."""
    import httpx

    provider = settings["provider"]
    if provider == "ollama":
        url = settings["base_url"].rstrip("/") + "/api/chat"
        payload = {"model": settings["model"], "messages": messages, "stream": stream}
        headers = {}
    else:
        url = settings["base_url"].rstrip("/") + "/v1/chat/completions"
        payload = {"model": settings["model"], "messages": messages, "stream": stream}
        headers = {}
        if settings["api_key"]:
            headers["Authorization"] = f"Bearer {settings['api_key']}"
    async with httpx.AsyncClient(timeout=120, trust_env=False) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        if stream:
            return response.aiter_lines()
        data = response.json()
        if provider == "ollama":
            return data.get("message", {}).get("content", "")
        return data["choices"][0]["message"]["content"]


# ── Контекст данных ──


def _build_context(db, user, table: str = "") -> str:
    uid = None if is_admin(user) else int(user["id"])
    admin = is_admin(user)
    lines = ["Данные СУОТ Enterprise:"]
    for t in sorted(DatabaseManager.JSON_TABLES):
        if table and t != table:
            continue
        try:
            rows, total = db.query_json_records(
                t, owner_id=uid, is_admin=admin, page_size=20
            )
            lines.append(f"\n{t} ({total} записей):")
            for r in rows[:10]:
                dj = r.get("data_json") or {}
                summary = ", ".join(
                    f"{k}={v}" for k, v in list(dj.items())[:4] if v and str(v).strip()
                )
                lines.append(f"  #{r['id']}: {summary}")
        except Exception:
            continue
    return "\n".join(lines)


# ── Чат со стримингом ──


class ChatIn(BaseModel):
    messages: List[Dict[str, str]] = []
    table: str = ""
    thread_id: int = 0


def _save_chat(db, user, thread_id: int, messages: List[Dict[str, str]]) -> int:
    """Сохранить переписку в тред. Создаёт тред, если thread_id=0.
    Возвращает thread_id."""
    uid = int(user["id"])
    if thread_id:
        rows = db.chat_messages_list(thread_id, uid)
        if not rows and not db.fetch_one(
            "SELECT id FROM chat_threads WHERE id=? AND user_id=?",
            (thread_id, uid),
        ):
            return 0
    else:
        thread_id = db.chat_thread_create(uid)
    if not db.fetch_one(
        "SELECT id FROM chat_threads WHERE id=? AND user_id=?",
        (thread_id, uid),
    ):
        return 0
    for m in messages[-20:]:
        db.chat_message_add(thread_id, m.get("role", "user"), m.get("content", ""))
    return thread_id


@router.post("/chat")
async def chat(body: ChatIn, db=Depends(get_db), user=Depends(get_current_user)):
    settings = _get_ai_settings(db)
    context = _build_context(db, user, body.table)
    system_msg = (
        "Ты — ассистент по охране труда в приложении СУОТ Enterprise. "
        "Отвечай на русском языке, кратко и по делу. "
        "Используй данные ниже для ответов на вопросы.\n\n" + context
    )
    messages = [{"role": "system", "content": system_msg}]
    messages += body.messages[-20:]

    async def generate():
        full = ""
        try:
            result = await _call_llm(messages, settings, stream=True)
            async for line in result:
                if line.startswith("data: "):
                    chunk = line[6:]
                    if chunk == "[DONE]":
                        block = json.loads(full) if full else None
                        break
                    try:
                        j = json.loads(chunk)
                        provider = settings["provider"]
                        if provider == "ollama":
                            content = j.get("message", {}).get("content", "")
                        else:
                            delta = j["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                        if content:
                            full += content
                            yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"
                    except json.JSONDecodeError:
                        continue
                elif line.strip():
                    try:
                        j = json.loads(line)
                        content = j.get("message", {}).get("content", "")
                        if content:
                            full += content
                            yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"
                    except json.JSONDecodeError:
                        continue
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            persisted = list(body.messages[-20:])
            if full:
                persisted.append({"role": "assistant", "content": full})
            _save_chat(db, user, body.thread_id, persisted)

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── Инсайты ──


class InsightsIn(BaseModel):
    table: str = ""


@router.post("/insights")
async def insights(
    body: InsightsIn, db=Depends(get_db), user=Depends(get_current_user)
):
    settings = _get_ai_settings(db)
    context = _build_context(db, user, body.table)
    prompt = (
        "Проанализируй данные охраны труда ниже и дай 3-5 коротких инсайтов "
        "в формате списка. Каждый инсайт — одно предложение. "
        "Отмечай тревожные тенденции.\n\n" + context
    )
    messages = [{"role": "user", "content": prompt}]
    try:
        result = await _call_llm(messages, settings)
        return {"insights": result}
    except Exception as e:
        return {
            "insights": f"⚠ AI недоступен: {e}",
            "warning": True,
        }


# ── Агент с инструментами ──


class AgentIn(BaseModel):
    message: str
    table: str = ""


TOOLS = [
    {
        "name": "create_record",
        "description": "Создать запись в указанной таблице",
        "params": {"table": "string", "data": "object"},
    },
    {
        "name": "update_record",
        "description": "Обновить запись по ID",
        "params": {"table": "string", "record_id": "integer", "data": "object"},
    },
    {
        "name": "search_records",
        "description": "Найти записи по тексту",
        "params": {"table": "string", "query": "string"},
    },
    {
        "name": "batch_update",
        "description": "Массово обновить записи, подходящие под фильтр",
        "params": {
            "table": "string",
            "query": "string (текст поиска)",
            "filter": "object (напр. {'Оценка': 'Высокая'})",
            "data": "object (новые значения полей)",
        },
    },
    {
        "name": "batch_delete",
        "description": "Массово удалить записи, подходящие под фильтр",
        "params": {
            "table": "string",
            "query": "string",
            "filter": "object",
        },
    },
]


def _resolve_records(
    db, user, table: str, query: str, filter: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Выборка кандидатов для пакетной операции (дифф-предпросмотр)."""
    uid = None if is_admin(user) else int(user["id"])
    rows, _ = db.query_json_records(
        table,
        owner_id=uid,
        is_admin=is_admin(user),
        q=query,
        page_size=200,
    )
    out = []
    for r in rows:
        d = r.get("data_json") or {}
        if filter:
            ok = True
            for k, v in filter.items():
                if str(d.get(k, "")).strip().lower() != str(v).strip().lower():
                    ok = False
                    break
            if not ok:
                continue
        out.append({"id": r["id"], **d})
    return out


@router.post("/agent/plan")
async def agent_plan(body: AgentIn, db=Depends(get_db), user=Depends(get_current_user)):
    """Агент: пакетная операция → вернуть diff-предпросмотр без применения."""
    settings = _get_ai_settings(db)
    context = _build_context(db, user, body.table)
    tools_desc = json.dumps(TOOLS, ensure_ascii=False, indent=2)
    system = (
        "Ты — AI-агент СУОТ Enterprise. Проанализируй запрос пользователя и, "
        "если нужна массовая операция с данными, верни ТОЛЬКО JSON с полями "
        "'action' (batch_update или batch_delete) и 'params'.\n"
        f"Инструменты:\n{tools_desc}\n\n"
        f"Данные (контекст):\n{context}\n\n"
        "Если массовая операция невозможна или уточнение необходимо — ответь "
        "коротким текстом на русском."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": body.message},
    ]
    try:
        raw = await _call_llm(messages, settings)
    except Exception as e:
        raise HTTPException(500, f"AI недоступен: {e}")
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        parsed = json.loads(raw[start:end])
        action = parsed.get("action", "")
        params = parsed.get("params", {})
        if action not in ("batch_update", "batch_delete"):
            return {"type": "text", "content": raw}
        table = params.get("table", body.table or "")
        if table not in DatabaseManager.JSON_TABLES:
            raise HTTPException(400, f"Неизвестная таблица: {table}")
        recs = _resolve_records(
            db, user, table, params.get("query", ""), params.get("filter", {})
        )
        diff = []
        for rec in recs:
            if action == "batch_delete":
                diff.append(
                    {
                        "id": rec["id"],
                        "op": "delete",
                        "summary": json.dumps(rec, ensure_ascii=False)[:160],
                    }
                )
            else:
                changes = {
                    k: v
                    for k, v in (params.get("data", {}) or {}).items()
                    if str(rec.get(k, "")).strip() != str(v).strip()
                }
                diff.append(
                    {
                        "id": rec["id"],
                        "op": "update",
                        "changes": changes,
                        "summary": json.dumps(rec, ensure_ascii=False)[:160],
                    }
                )
        return {
            "type": "preview",
            "action": action,
            "params": params,
            "table": table,
            "count": len(diff),
            "diff": diff,
        }
    except (ValueError, KeyError) as e:
        return {"type": "text", "content": raw}


# ── Статус провайдера (ping) ──


@router.post("/ping")
async def ai_ping(db=Depends(get_db), user=Depends(get_current_user)):
    """Проверка доступности провайдера LLM."""
    import time

    settings = _get_ai_settings(db)
    t0 = time.time()
    try:
        if settings["provider"] == "ollama":
            url = settings["base_url"].rstrip("/") + "/api/tags"
        else:
            url = settings["base_url"].rstrip("/") + "/v1/models"
        headers = {}
        if settings["provider"] != "ollama" and settings.get("api_key"):
            headers["Authorization"] = f"Bearer {settings['api_key']}"
        import httpx

        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(url, headers=headers)
            ok = resp.status_code == 200
        ms = int((time.time() - t0) * 1000)
        return {
            "ok": ok,
            "ms": ms,
            "provider": settings["provider"],
            "url": settings["base_url"],
            "error": "" if ok else f"HTTP {resp.status_code}",
        }
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        return {
            "ok": False,
            "ms": ms,
            "provider": settings["provider"],
            "url": settings["base_url"],
            "error": str(e)[:200],
        }


@router.post("/agent")
async def agent(body: AgentIn, db=Depends(get_db), user=Depends(get_current_user)):
    settings = _get_ai_settings(db)
    context = _build_context(db, user, body.table)
    tools_desc = json.dumps(TOOLS, ensure_ascii=False, indent=2)
    system = (
        "Ты — AI-агент СУОТ Enterprise. Ты можешь управлять данными.\n"
        f"Доступные инструменты:\n{tools_desc}\n\n"
        f"Данные:\n{context}\n\n"
        "Если пользователь просит создать/изменить/найти запись — "
        "верни JSON с полем 'action' (create_record/update_record/"
        "search_records) и полем 'params'. "
        "Если просто вопрос — ответь текстом без JSON."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": body.message},
    ]
    try:
        raw = await _call_llm(messages, settings)
    except Exception as e:
        raise HTTPException(500, f"AI недоступен: {e}")
    # Пытаемся распарсить JSON-действие
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        action = json.loads(raw[start:end])
        if "action" in action and "params" in action:
            return {
                "type": "action",
                "action": action["action"],
                "params": action["params"],
                "raw": raw,
            }
    except (ValueError, KeyError):
        pass
    return {"type": "text", "content": raw}


@router.post("/agent/execute")
async def agent_execute(
    body: Dict[str, Any], db=Depends(get_db), user=Depends(get_current_user)
):
    """Выполнение подтверждённого действия агента."""
    action = body.get("action", "")
    params = body.get("params", {})
    uid = int(user["id"])
    table = params.get("table", "")
    if table not in DatabaseManager.JSON_TABLES:
        raise HTTPException(400, f"Неизвестная таблица: {table}")
    if action == "create_record":
        nid = db.save_json_record(table, 0, params.get("data", {}), user_id=uid)
        return {"ok": True, "id": nid}
    if action == "update_record":
        rid = int(params.get("record_id", 0))
        rec = db.get_json_record(table, rid)
        if not rec:
            raise HTTPException(404, "Запись не найдена")
        data = {**(rec.get("data_json") or {}), **params.get("data", {})}
        db.save_json_record(table, rid, data, user_id=uid)
        return {"ok": True, "id": rid}
    if action == "search_records":
        rows, total = db.query_json_records(
            table,
            owner_id=uid,
            is_admin=is_admin(user),
            q=params.get("query", ""),
            page_size=20,
        )
        return {
            "ok": True,
            "results": [{"id": r["id"], **(r.get("data_json") or {})} for r in rows],
        }
    if action in ("batch_update", "batch_delete"):
        recs = _resolve_records(
            db, user, table, params.get("query", ""), params.get("filter", {})
        )
        if not recs:
            raise HTTPException(404, "Нет записей, подходящих под фильтр")
        if action == "batch_delete":
            for rec in recs:
                db.delete_json_record(table, rec["id"])
            return {"ok": True, "count": len(recs), "action": action}
        data = params.get("data", {}) or {}
        for rec in recs:
            cur = db.get_json_record(table, rec["id"])
            if not cur:
                continue
            merged = {**(cur.get("data_json") or {}), **data}
            db.save_json_record(table, rec["id"], merged, user_id=uid)
        return {"ok": True, "count": len(recs), "action": action}
    raise HTTPException(400, f"Неизвестное действие: {action}")


# ── История диалогов (Часть 27) ──


class ThreadCreateIn(BaseModel):
    title: str = ""


class ThreadRenameIn(BaseModel):
    title: str


@router.get("/threads")
def threads_list(db=Depends(get_db), user=Depends(get_current_user)):
    uid = int(user["id"])
    threads = db.chat_threads_list(uid)
    for t in threads:
        last = db.chat_messages_list(t["id"], uid)
        t["message_count"] = len(last)
        t["preview"] = last[-1]["content"][:140] if last else ""
    return {"items": threads}


@router.post("/threads")
def thread_create(
    body: ThreadCreateIn, db=Depends(get_db), user=Depends(get_current_user)
):
    tid = db.chat_thread_create(int(user["id"]), body.title)
    return {"ok": True, "id": tid}


@router.patch("/threads/{thread_id}")
def thread_rename(
    thread_id: int,
    body: ThreadRenameIn,
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    ok = db.chat_thread_rename(thread_id, int(user["id"]), body.title)
    if not ok:
        raise HTTPException(404, "Диалог не найден")
    return {"ok": True}


@router.delete("/threads/{thread_id}")
def thread_delete(thread_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    ok = db.chat_thread_delete(thread_id, int(user["id"]))
    if not ok:
        raise HTTPException(404, "Диалог не найден")
    return {"ok": True}


@router.get("/threads/{thread_id}/messages")
def thread_messages(thread_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    items = db.chat_messages_list(thread_id, int(user["id"]))
    return {"thread_id": thread_id, "items": items}
