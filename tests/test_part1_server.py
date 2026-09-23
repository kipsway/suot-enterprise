"""Часть 1: тесты каркаса — аутентификация и изоляция данных."""

import os, sys, tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

TMP_DB = os.path.join(tempfile.gettempdir(), "suot_test_part1.db")
for suffix in ("", "-wal", "-shm"):
    try:
        if os.path.exists(TMP_DB + suffix):
            os.remove(TMP_DB + suffix)
    except PermissionError:
        pass

# Часть 21: сид admin/admin создаётся только в тестовой среде
os.environ["SUOT_E2E_DB"] = TMP_DB

from services.database import DatabaseManager  # noqa: E402

db = DatabaseManager(TMP_DB)

from server.app import app  # noqa: E402

client_ctx = TestClient(app)
client = client_ctx.__enter__()  # активирует lifespan → миграция изоляции
PASS = []
FAIL = []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK " if cond else "FAIL ") + name + (f" | {extra}" if extra else ""))


print("== Health ==")
r = client.get("/api/health")
check("health 200", r.status_code == 200, str(r.json()))

print("== Регистрация ==")
r1 = client.post(
    "/api/auth/register",
    json={"username": "boss", "password": "secret1", "full_name": "Босс Админов"},
)
check(
    "register #1 → user", r1.status_code == 201 and r1.json()["user"]["role"] == "user"
)
tok_a = r1.json()["token"]

r2 = client.post(
    "/api/auth/register",
    json={"username": "worker", "password": "secret2", "full_name": "Вася Работяга"},
)
check(
    "register #2 → user", r2.status_code == 201 and r2.json()["user"]["role"] == "user"
)
tok_b = r2.json()["token"]

rl_admin = client.post(
    "/api/auth/login", json={"username": "admin", "password": "admin"}
)
check(
    "сид-админ admin/admin → Administrator",
    rl_admin.status_code == 200 and rl_admin.json()["user"]["role"] == "Administrator",
)

rdup = client.post(
    "/api/auth/register", json={"username": "BOSS", "password": "secret3"}
)
check("duplicate username → 409", rdup.status_code == 409)
rshort = client.post(
    "/api/auth/register", json={"username": "ab", "password": "secret3"}
)
check("short username → 400", rshort.status_code == 400)

HA = {"Authorization": f"Bearer {tok_a}"}
HB = {"Authorization": f"Bearer {tok_b}"}

print("== Изоляция данных ==")
ra = client.post(
    "/api/data/employees",
    headers=HA,
    json={"data": {"ФИО": "Иванов А.А.", "Фирма": "ООО Альфа"}},
)
check("A создаёт сотрудника", ra.status_code == 201, str(ra.json()))
emp_id = ra.json()["id"]

rb_list = client.get("/api/data/employees", headers=HB)
ids_b = [i["id"] for i in rb_list.json()["items"]]
check("B НЕ видит запись A", emp_id not in ids_b, f"B sees {len(ids_b)} items")

ra_list = client.get("/api/data/employees", headers=HA)
ids_a = [i["id"] for i in ra_list.json()["items"]]
check("Админ видит запись A", emp_id in ids_a, f"admin sees {len(ids_a)}")

rb_get = client.get(f"/api/data/employees/{emp_id}", headers=HB)
check("B читает чужую запись → 403", rb_get.status_code == 403)
rb_del = client.delete(f"/api/data/employees/{emp_id}", headers=HB)
check("B удаляет чужую запись → 403", rb_del.status_code == 403)
rb_put = client.put(
    f"/api/data/employees/{emp_id}", headers=HB, json={"data": {"ФИО": "Взлом"}}
)
check("B правит чужую запись → 403", rb_put.status_code == 403)

rb_own = client.post(
    "/api/data/violations", headers=HB, json={"data": {"Описание": "Тест B"}}
)
check("B создаёт свою запись", rb_own.status_code == 201)
rb_own_id = rb_own.json()["id"]
rb_del_own = client.delete(f"/api/data/violations/{rb_own_id}", headers=HB)
check("B удаляет СВОЮ запись → ok", rb_del_own.status_code == 200)

runknown = client.get("/api/data/not_a_table", headers=HA)
check("чужая таблица → 404", runknown.status_code == 404)

print("== Часть 2: движок таблиц ==")
# создаём пачку записей для B
for i in range(7):
    client.post(
        "/api/data/employees",
        headers=HB,
        json={
            "data": {
                "ФИО": f"Тестов Тест №{i}",
                "Подразделение": "Цех №1" if i % 2 else "Склад",
            }
        },
    )
rb_page = client.get(
    "/api/data/employees", headers=HB, params={"page": 1, "page_size": 3}
)
jb = rb_page.json()
check(
    "пагинация page_size=3",
    len(jb["items"]) == 3 and jb["total"] >= 7,
    str(jb["total"]),
)
rb_p2 = client.get(
    "/api/data/employees", headers=HB, params={"page": 2, "page_size": 3}
)
check("страница 2 отличается", rb_p2.json()["items"][0]["id"] != jb["items"][0]["id"])

rb_sort = client.get(
    "/api/data/employees",
    headers=HB,
    params={"sort_by": "ФИО", "order": "desc", "page_size": 100},
)
names = [i["data"].get("ФИО", "") for i in rb_sort.json()["items"]]
check("сортировка desc по ФИО", names == sorted(names, reverse=True), str(names[:3]))

rb_q = client.get("/api/data/employees", headers=HB, params={"q": "Тест №3"})
check(
    "поиск q находит",
    any("Тест №3" in i["data"].get("ФИО", "") for i in rb_q.json()["items"]),
    str(rb_q.json()["total"]),
)

rv = client.get(
    "/api/data/employees/values", headers=HB, params={"col": "Подразделение"}
)
vset = set(rv.json()["values"])
check("значения колонки для фильтра", vset >= {"Цех №1", "Склад"}, str(sorted(vset)))

rf = client.get("/api/data/employees", headers=HB, params={"page_size": 100})
rf.url  # noqa
import urllib.parse

url = (
    "/api/data/employees?page_size=100&f_"
    + urllib.parse.quote("Подразделение")
    + "="
    + urllib.parse.quote("Склад")
)
rf2 = client.get(url, headers=HB)
all_c = all(i["data"].get("Подразделение") == "Склад" for i in rf2.json()["items"])
check(
    "фильтр колонки работает",
    all_c and len(rf2.json()["items"]) > 0,
    str(rf2.json()["total"]),
)

# массовое удаление: B не может удалить чужую запись A
rbd = client.post("/api/data/employees/bulk_delete", headers=HB, json={"ids": [emp_id]})
check(
    "bulk_delete чужой записи блокирован",
    rbd.status_code == 200 and rbd.json()["deleted"] == 0,
)
own_ids = [
    i["id"] for i in client.get("/api/data/violations", headers=HB).json()["items"]
]
client.post(
    "/api/data/violations", headers=HB, json={"data": {"Описание": "для удаления"}}
)
vids = [i["id"] for i in client.get("/api/data/violations", headers=HB).json()["items"]]
rbd2 = client.post("/api/data/violations/bulk_delete", headers=HB, json={"ids": vids})
check("bulk_delete своих записей", rbd2.json()["deleted"] == len(vids))

print("== Демо-данные ==")
rd = client.post("/api/demo/seed", headers=HB, json={})
jd = rd.json()["created"]
check(
    "демо сид создал записи",
    jd.get("violations", 0) > 0 and jd.get("ppe", 0) > 0 and jd.get("training", 0) > 0,
    str(jd),
)
rd2 = client.post("/api/demo/seed", headers=HB, json={})
check(
    "повторный сид пропускает непустые",
    rd2.json()["created"].get("employees", 0) == 0,
    str(rd2.json()),
)
rc = client.get("/api/me/counts", headers=HB)
check("me/counts считает", rc.json()["counts"].get("employees", 0) >= 7)

print("== Remember-me ==")
rr = client.post(
    "/api/auth/login",
    json={"username": "worker", "password": "secret2", "remember": False},
)
check("вход без запоминания", rr.status_code == 200)

print("== Часть 3: компании, фото, сортировка ==")
rc1 = client.post(
    "/api/data/companies",
    headers=HB,
    json={
        "data": {
            "Наименование": "ООО ТестКомпани",
            "Адрес": "ул. Ленина, 1",
            "Телефон": "+7 999 000-00-00",
            "ИНН": "1234567890",
        }
    },
)
check("создание компании", rc1.status_code == 201, str(rc1.json()))
comp_id = rc1.json()["id"]

rc_dup = client.post(
    "/api/data/companies",
    headers=HB,
    json={"data": {"Наименование": "ООО ТестКомпани"}},
)
check("дубль имени → 409", rc_dup.status_code == 409)

rc_noname = client.post(
    "/api/data/companies", headers=HB, json={"data": {"Адрес": "без имени"}}
)
check("компания без имени → 400", rc_noname.status_code == 400)

rc_upd = client.put(
    f"/api/data/companies/{comp_id}",
    headers=HB,
    json={"data": {"Наименование": "ООО Переименованная", "Адрес": "новый адрес"}},
)
check("переименование компании", rc_upd.status_code == 200)
legacy = db.fetch_one("SELECT name, address FROM companies WHERE id=?", (comp_id,))
check(
    "легаси-колонки синхронизированы",
    legacy
    and legacy["name"] == "ООО Переименованная"
    and legacy["address"] == "новый адрес",
    str(dict(legacy) if legacy else None),
)

# Фото: загрузка + привязка
png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
rup = client.post(
    "/api/media/upload", headers=HA, files={"file": ("photo.png", png, "image/png")}
)
check(
    "загрузка фото",
    rup.status_code == 200 and rup.json()["url"].startswith("/media/"),
    str(rup.json()),
)
photo_url = rup.json()["url"]
rimg = client.get(photo_url)
check(
    "фото отдается статикой", rimg.status_code == 200 and len(rimg.content) == len(png)
)
rbad = client.post(
    "/api/media/upload",
    headers=HA,
    files={"file": ("evil.exe", b"MZ...", "application/x-exe")},
)
check("не-изображение → 400", rbad.status_code == 400)

rem = client.get(f"/api/data/employees/{emp_id}", headers=HA)
emp_data = rem.json()["data"]
emp_data["Фото"] = photo_url
rupd = client.put(f"/api/data/employees/{emp_id}", headers=HA, json={"data": emp_data})
rchk = client.get(f"/api/data/employees/{emp_id}", headers=HA)
check("фото привязано к записи", rchk.json()["data"].get("Фото") == photo_url)

# order_cast: текстовая колонка с числами
for val in ("10", "2", "10"):
    client.post(
        "/api/data/custom_ledger",
        headers=HB,
        json={"data": {"Категория": val, "Описание": "cast-тест"}},
    )
rt = client.get(
    "/api/data/custom_ledger",
    headers=HB,
    params={"sort_by": "Категория", "order": "asc", "page_size": 200},
)
cats_text = [
    i["data"].get("Категория", "")
    for i in rt.json()["items"]
    if i["data"].get("Описание") == "cast-тест"
]
rn = client.get(
    "/api/data/custom_ledger",
    headers=HB,
    params={
        "sort_by": "Категория",
        "order": "asc",
        "order_cast": "num",
        "page_size": 200,
    },
)
cats_num = [
    i["data"].get("Категория", "")
    for i in rn.json()["items"]
    if i["data"].get("Описание") == "cast-тест"
]
check(
    "текстовая сортировка: '10' перед '2'",
    cats_text == sorted(cats_text),
    str(cats_text),
)
check(
    "числовая сортировка: '2' перед '10'",
    cats_num == sorted(cats_num, key=lambda x: int(x)),
    str(cats_num),
)

rcc = client.get("/api/meta/companies", headers=HB)
check(
    "конфиг колонок компаний появился",
    rcc.status_code == 200
    and any(c["name"] == "Наименование" for c in rcc.json()["columns"]),
)

print("== Часть 4: справочники, заметки, история ==")
r_adm = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
HAdm = {"Authorization": "Bearer " + r_adm.json()["token"]}
rnt = client.post(
    "/api/dicts/violation_types",
    headers=HB,
    json={"name": "Тип Е2Е", "risk_category": "Высокая"},
)
check("не-админ не меняет справочник", rnt.status_code == 403)
rnt = client.post(
    "/api/dicts/violation_types",
    headers=HAdm,
    json={"name": "Тип Е2Е", "risk_category": "Высокая", "description": "тест"},
)
check("админ создаёт тип", rnt.status_code == 201, str(rnt.json()))
tid = rnt.json()["id"]
rnt2 = client.post("/api/dicts/violation_types", headers=HAdm, json={"name": "Тип Е2Е"})
check("дубль типа → 409", rnt2.status_code == 409)
rntu = client.put(
    f"/api/dicts/violation_types/{tid}",
    headers=HAdm,
    json={"name": "Тип Е2Е v2", "risk_category": "Низкая"},
)
check("правка типа", rntu.status_code == 200)
rtpl = client.get("/api/dicts/violation_templates", headers=HB)
check(
    "шаблоны нарушений есть",
    rtpl.status_code == 200 and len(rtpl.json()["items"]) >= 3,
    str(len(rtpl.json().get("items", []))),
)

# Заметки на записи сотрудника A
rn1 = client.post(
    f"/api/record/employees/{emp_id}/notes",
    headers=HA,
    json={"title": "Позвонить", "content": "уточнить медосмотр"},
)
check("заметка добавлена", rn1.status_code == 201)
rnl = client.get(f"/api/record/employees/{emp_id}/notes", headers=HA)
check("заметка в списке", len(rnl.json()["items"]) >= 1)
nid = rnl.json()["items"][0]["id"]
rnb = client.get(f"/api/record/employees/{emp_id}/notes", headers=HB)
check("чужие заметки недоступны", rnb.status_code == 403)
rnd = client.delete(f"/api/record/notes/{nid}", headers=HA)
check("заметка удалена", rnd.status_code == 200)

# Связи
# IDOR-фикс (аудит 7.2 п.5): цель связи тоже должна быть доступна.
# comp_id создан пользователем B — A не может связать с ним; создаём свою.
rca = client.post(
    "/api/data/companies",
    headers=HA,
    json={"data": {"Наименование": "ООО КомпанияА"}},
)
rc_id = rca.json()["id"]
rln = (
    client.post(
        f"/api/record/violations/{rb_own_id if False else 1}/links",
        headers=HA,
        json={"target_table": "companies", "target_id": rc_id},
    )
    if False
    else None
)
# создаём нарушение от A и связываем с компанией A
rvl = client.post(
    "/api/data/violations",
    headers=HA,
    json={"data": {"Описание": "связь-тест", "Дата": "01.08.2026"}},
)
viol_id = rvl.json()["id"]
rln_x = client.post(
    f"/api/record/violations/{viol_id}/links",
    headers=HA,
    json={"target_table": "companies", "target_id": comp_id},
)
check("связь к чужой компании → 403", rln_x.status_code == 403, str(rln_x.json()))
rln = client.post(
    f"/api/record/violations/{viol_id}/links",
    headers=HA,
    json={"target_table": "companies", "target_id": rc_id},
)
check("связь создана", rln.status_code == 201, str(rln.json()))
rln2 = client.post(
    f"/api/record/violations/{viol_id}/links",
    headers=HA,
    json={"target_table": "companies", "target_id": rc_id},
)
check("дубль связи → 409", rln2.status_code == 409)
rll = client.get(f"/api/record/violations/{viol_id}/links", headers=HA)
check(
    "имя связанной записи резолвится",
    any("КомпанияА" in (i.get("target_name") or "") for i in rll.json()["items"]),
    str(rll.json()["items"][:1]),
)

# История: правим нарушение → запись в истории → откат
rv_get = client.get(f"/api/data/violations/{viol_id}", headers=HA)
vd = rv_get.json()["data"]
vd["Описание"] = "связь-тест ИЗМЕНЕНО"
client.put(f"/api/data/violations/{viol_id}", headers=HA, json={"data": vd})
rh = client.get(f"/api/record/violations/{viol_id}/history", headers=HA)
hitems = rh.json()["items"]
check(
    "история фиксирует изменение",
    any(
        i["field"] == "Описание" and "ИЗМЕНЕНО" in (i["new_value"] or "")
        for i in hitems
    ),
    str(len(hitems)),
)
hid = next(i["id"] for i in hitems if i["field"] == "Описание")
rrb = client.post(
    f"/api/record/violations/{viol_id}/history/{hid}/rollback", headers=HA
)
check("откат изменения", rrb.status_code == 200)
rv_after = client.get(f"/api/data/violations/{viol_id}", headers=HA)
check("значение восстановлено", rv_after.json()["data"]["Описание"] == "связь-тест")

# Дубликат нарушений
rdup2 = client.post(
    "/api/data/violations",
    headers=HA,
    json={
        "data": {
            "Дата": "02.08.2026",
            "Фирма": "ДубФирма",
            "Подразделение": "Цех",
            "Описание": "уникальное дубль-описание",
        }
    },
)
dup_id = rdup2.json()["id"]
rdchk = client.get(
    "/api/data/violations/duplicate_check",
    headers=HA,
    params={
        "Дата": "02.08.2026",
        "Фирма": "дубфирма",
        "Подразделение": "цех",
        "Описание": "Уникальное Дубль-Описание",
    },
)
check(
    "дубликат найден (регистронезависимо)",
    rdchk.json().get("found") is True,
    str(rdchk.json()),
)
rdno = client.get(
    "/api/data/violations/duplicate_check",
    headers=HA,
    params={"Дата": "09.09.2030", "Описание": "нет такого"},
)
check("не-дубликат → found:false", rdno.json().get("found") is False)

print("== Часть 5: дубликат, batch edit, метки ==")
rdup3 = client.post(f"/api/data/violations/{viol_id}/duplicate", headers=HA)
check("дублирование записи", rdup3.status_code == 201)
dup2_id = rdup3.json()["id"]
rdup_get = client.get(f"/api/data/violations/{dup2_id}", headers=HA)
check(
    "копия помечена '(копия)'",
    "копия" in rdup_get.json()["data"].get("Описание", ""),
    rdup_get.json()["data"].get("Описание"),
)

rbe = client.post(
    "/api/data/violations/bulk_edit",
    headers=HA,
    json={"ids": [viol_id, dup2_id, dup_id], "field": "Статус", "value": "Устранено"},
)
check("batch edit обновил 3", rbe.json().get("updated") == 3, str(rbe.json()))
rbe_bad = client.post(
    "/api/data/violations/bulk_edit",
    headers=HA,
    json={"ids": [viol_id], "field": "НетТакой", "value": "x"},
)
check("batch edit чужая колонка → 400", rbe_bad.status_code == 400)
rbe_b = client.post(
    "/api/data/violations/bulk_edit",
    headers=HB,
    json={"ids": [viol_id], "field": "Статус", "value": "Взлом"},
)
check("B не редактирует чужие batch'ем", rbe_b.json().get("updated") == 0)

rlbl = client.post(
    f"/api/data/violations/{viol_id}/label", headers=HA, json={"color": "red"}
)
check("метка установлена", rlbl.status_code == 200 and rlbl.json()["color"] == "red")
rv_l = client.get(f"/api/data/violations/{viol_id}", headers=HA)
check("метка в данных записи", rv_l.json()["data"].get("_label") == "red")
rlbl_bad = client.post(
    f"/api/data/violations/{viol_id}/label", headers=HA, json={"color": "gold"}
)
check("недопустимый цвет → 400", rlbl_bad.status_code == 400)
rlbl_b = client.post(
    f"/api/data/violations/{dup_id}/label", headers=HB, json={"color": "red"}
)
check("B не ставит метку чужой записи", rlbl_b.status_code == 403)
rlbl0 = client.post(
    f"/api/data/violations/{viol_id}/label", headers=HA, json={"color": ""}
)
check("метка снята", rlbl0.status_code == 200)

print("== Часть 6: чек-листы, CAPA, протоколы, риски, справочник ==")
# Чек-лист
rcl = client.post(
    "/api/s/checklists",
    headers=HA,
    json={
        "title": "Е2Е Осмотр",
        "description": "тест",
        "items": ["Пункт 1", "Пункт 2", ""],
    },
)
check("чек-лист создан", rcl.status_code == 201)
clid = rcl.json()["id"]
rclg = client.get(f"/api/s/checklists/{clid}", headers=HA)
check("пункты сохранились (2)", len(rclg.json()["items"]) == 2)
# Результат с провалом
rid_res = client.post(
    f"/api/s/checklists/{clid}/results",
    headers=HA,
    json={
        "conducted_by": "Е2Е",
        "answers": [
            {"item_id": rclg.json()["items"][0]["id"], "value": "ok"},
            {
                "item_id": rclg.json()["items"][1]["id"],
                "value": "fail",
                "comment": "дефект",
            },
        ],
    },
)
check(
    "результат: статус fail",
    rid_res.json().get("status") == "fail",
    str(rid_res.json()),
)
# Шаблон (предложение 2)
rtpl2 = client.post(f"/api/s/checklists/{clid}/save_as_template", headers=HA)
tpl_id = rtpl2.json()["id"]
rtpls = client.get("/api/s/checklists?mode=templates", headers=HA)
check("шаблон в списке шаблонов", any(i["id"] == tpl_id for i in rtpls.json()["items"]))
rfrom = client.post(f"/api/s/checklists/from_template/{tpl_id}", headers=HA)
new_cl = rfrom.json()["id"]
rnew = client.get(f"/api/s/checklists/{new_cl}", headers=HA)
check(
    "из шаблона: пункты перенесены",
    len(rnew.json()["items"]) == 2 and rnew.json()["checklist"]["is_template"] == 0,
)
# Изоляция чек-листов
rcl_b = client.get(f"/api/s/checklists/{clid}", headers=HB)
check("B не видит чужой чек-лист", rcl_b.status_code == 403)

# CAPA
rcapa = client.post(
    "/api/s/capa",
    headers=HA,
    json={
        "title": "Е2Е CAPA",
        "description": "Несоответствие Е2Е",
        "root_cause": "Причина Е2Е",
        "action_plan": "План Е2Е",
        "severity": "high",
        "deadline": "01.12.2026",
    },
)
capa_id = rcapa.json()["id"]
rcapa_g = client.get(f"/api/s/capa/{capa_id}", headers=HA)
check("CAPA создана и читается", rcapa_g.json()["record"]["title"] == "Е2Е CAPA")
rcapa_u = client.put(
    f"/api/s/capa/{capa_id}",
    headers=HA,
    json={
        "title": "Е2Е CAPA",
        "description": "Несоответствие Е2Е",
        "root_cause": "Причина",
        "action_plan": "План",
        "effectiveness": "Эффективно, повторов нет",
        "severity": "high",
        "status": "verified",
        "assigned_to": "",
        "deadline": "01.12.2026",
    },
)
check("CAPA обновлена (эффективность)", rcapa_u.status_code == 200)
rcapa_b = client.get(f"/api/s/capa/{capa_id}", headers=HB)
check("B не видит чужую CAPA", rcapa_b.status_code == 403)

# Протоколы
rpr = client.post(
    "/api/s/protocols",
    headers=HA,
    json={"topic": "Е2Е Протокол", "participants": "Иванов", "decisions": "решение"},
)
check("протокол создан", rpr.status_code == 201)
rpr_l = client.get("/api/s/protocols", headers=HA)
check(
    "протокол в списке",
    any(i["topic"] == "Е2Е Протокол" for i in rpr_l.json()["items"]),
)

# Риски: уровень = P×C
rrisk = client.post(
    "/api/s/risks",
    headers=HA,
    json={"title": "Е2Е Риск", "probability": 4, "consequence": 4},
)
risk_id = rrisk.json()["id"]
rrisk_g = client.get("/api/s/risks", headers=HA)
r_rec = next(i for i in rrisk_g.json()["items"] if i["id"] == risk_id)
check("уровень риска 4×4=16", r_rec["risk_level"] == 16)
rrisk2 = client.post(
    "/api/s/risks",
    headers=HA,
    json={"title": "Низкий риск", "probability": 1, "consequence": 2},
)
r2 = next(
    i
    for i in client.get("/api/s/risks", headers=HA).json()["items"]
    if i["id"] == rrisk2.json()["id"]
)
check("уровень риска 1×2=2", r2["risk_level"] == 2)

# Справочник сокращений
rtb = client.post(
    "/api/s/textbook",
    headers=HA,
    json={"short_code": "е2е_код", "full_text": "расшифровка"},
)
check("справочник: добавление", rtb.status_code == 201)
rtb2 = client.post("/api/s/textbook", headers=HA, json={"short_code": "е2е_код"})
check("дубль кода → 409", rtb2.status_code == 409)
rtb_l = client.get("/api/s/textbook", headers=HB)
check(
    "справочник общий (видит B)",
    any(i["short_code"] == "е2е_код" for i in rtb_l.json()["items"]),
)
rtb_d = client.delete("/api/s/textbook/е2е_код", headers=HA)
check("справочник: удаление", rtb_d.status_code == 200)

print("== Часть 7: пользовательские таблицы ==")
rct = client.post(
    "/api/custom/tables",
    headers=HB,
    json={
        "label": "Е2Е Склад",
        "icon": "database",
        "color": "#10B981",
        "columns": [
            {"name": "Название", "type": "Текст"},
            {"name": "Количество", "type": "Число"},
        ],
    },
)
check("своя таблица создана", rct.status_code == 201)
ct_key = rct.json()["key"]

rct_b = client.get("/api/custom/meta/" + ct_key, headers=HAdm)
check("A (админ) видит таблицу B", rct_b.status_code == 200)
rct_meta = client.get("/api/custom/meta/" + ct_key, headers=HB)
check(
    "мета: колонки и label",
    rct_meta.json()["label"] == "Е2Е Склад" and len(rct_meta.json()["columns"]) == 2,
)

rcr = client.post(
    f"/api/custom/records/{ct_key}",
    headers=HB,
    json={"data": {"Название": "Болт М8", "Количество": 100}},
)
check("запись создана", rcr.status_code == 201)
crec_id = rcr.json()["id"]
rcr2 = client.post(
    f"/api/custom/records/{ct_key}",
    headers=HB,
    json={"data": {"Название": "Гайка М8", "Количество": 50}},
)
rl = client.get(
    f"/api/custom/records/{ct_key}?sort_by=Количество&order=desc", headers=HB
)
check(
    "сортировка по числу desc", rl.json()["items"][0]["data"]["Название"] == "Болт М8"
)
rq = client.get(f"/api/custom/records/{ct_key}?q=гайка", headers=HB)
check("поиск по своей таблице", rq.json()["total"] == 1)

# чужому пользователю недоступна
rct_a_denied = client.get(f"/api/custom/records/{ct_key}", headers={})
check("без токена → 401", rct_a_denied.status_code == 401)

# дубликат/метка/batch на своей таблице
rd_c = client.post(f"/api/custom/duplicate/{ct_key}/{crec_id}", headers=HB)
check("дубликат в своей таблице", rd_c.status_code == 201)
rlb_c = client.post(
    f"/api/custom/label/{ct_key}/{crec_id}", headers=HB, json={"color": "blue"}
)
check("метка в своей таблице", rlb_c.status_code == 200)

# вторая таблица + перенос (переместить)
rct2 = client.post(
    "/api/custom/tables",
    headers=HB,
    json={
        "label": "Е2Е Полка",
        "columns": [
            {"name": "Название", "type": "Текст"},
            {"name": "Количество", "type": "Число"},
        ],
    },
)
ct2_key = rct2.json()["key"]
rtr = client.post(
    "/api/custom/transfer",
    headers=HB,
    json={
        "from_key": ct_key,
        "to_key": ct2_key,
        "ids": [rl.json()["items"][0]["id"]],
        "move": True,
    },
)
check("перенос с удалением", rtr.json().get("moved") == 1)
rl2 = client.get(f"/api/custom/records/{ct2_key}", headers=HB)
check("запись в целевой таблице", rl2.json()["total"] == 1)

# перенос в JSON-таблицу: совпадающих колонок нет → 0 (корректно)
rtr2 = client.post(
    "/api/custom/transfer",
    headers=HB,
    json={
        "from_key": ct2_key,
        "to_key": "companies",
        "ids": [rl2.json()["items"][0]["id"]],
        "move": False,
    },
)
check(
    "перенос в JSON без совпадающих колонок → 0",
    rtr2.json().get("moved") == 0,
    str(rtr2.json()),
)

# корзина: удалить → в корзине → восстановить
rtr_del = client.delete(f"/api/custom/tables/{ct2_key}", headers=HB)
rtrash = client.get("/api/custom/trash", headers=HB)
check("таблица в корзине", any(i["key"] == ct2_key for i in rtrash.json()["items"]))
rrest = client.post(f"/api/custom/tables/{ct2_key}/restore", headers=HB)
rtrash2 = client.get("/api/custom/trash", headers=HB)
check(
    "восстановлена из корзины",
    all(i["key"] != ct2_key for i in rtrash2.json()["items"]),
)

# counts включает свои таблицы
rcc2 = client.get("/api/me/counts", headers=HB)
check(
    "counts содержит u_ ключи", any(k.startswith("u_") for k in rcc2.json()["counts"])
)

# purge (безвозвратно)
client.delete(f"/api/custom/tables/{ct2_key}", headers=HB)
rpurge = client.delete(f"/api/custom/tables/{ct2_key}/purge", headers=HB)
check("purge таблицы", rpurge.status_code == 200)
rmeta_gone = client.get(f"/api/custom/meta/{ct2_key}", headers=HB)
check("после purge → 404", rmeta_gone.status_code == 404)

# миграция: purge_old не трогает свежие
check("purge_old(30) не удаляет свежие", db.purge_old_custom_tables(30) == 0)

print("== Часть 8: пользовательские колонки ==")
# добавление
ruc = client.post(
    "/api/ucols/employees", headers=HB, json={"name": "Отдел Е2Е", "type": "Текст"}
)
check("своя колонка добавлена", ruc.status_code == 201)
uc_id = ruc.json()["id"]
ruc_dup = client.post("/api/ucols/employees", headers=HB, json={"name": "Отдел Е2Е"})
check("дубль своей → 409", ruc_dup.status_code == 409)
ruc_sys = client.post("/api/ucols/employees", headers=HB, json={"name": "ФИО"})
check("имя системной → 409", ruc_sys.status_code == 409)
ruc_bad = client.post(
    "/api/ucols/employees", headers=HB, json={"name": "Х", "type": "Магия"}
)
check("неизвестный тип → 400", ruc_bad.status_code == 400)

# изоляция: A не видит колонку B
ruc_a = client.get("/api/ucols/employees", headers=HA)
check(
    "колонки B не видны A", all(i["name"] != "Отдел Е2Е" for i in ruc_a.json()["items"])
)

# запись значения в свою колонку через обычный PUT (своя запись B)
rown = client.post(
    "/api/data/employees", headers=HB, json={"data": {"ФИО": "Колонкин Тест"}}
)
own_id = rown.json()["id"]
rget = client.get(f"/api/data/employees/{own_id}", headers=HB)
edata = rget.json()["data"]
edata["Отдел Е2Е"] = "Цех Е2Е"
client.put(f"/api/data/employees/{own_id}", headers=HB, json={"data": edata})
rchk2 = client.get(f"/api/data/employees/{own_id}", headers=HB)
check(
    "значение в своей колонке сохранено",
    rchk2.json()["data"].get("Отдел Е2Е") == "Цех Е2Е",
)

# вычисляемая колонка
rcomp = client.post(
    "/api/ucols/employees",
    headers=HB,
    json={
        "name": "Метка Е2Е",
        "type": "Вычисляемая",
        "template": "{ФИО} / {Отдел Е2Е}",
    },
)
check("вычисляемая колонка создана", rcomp.status_code == 201)
rcomp_bad = client.post(
    "/api/ucols/employees",
    headers=HB,
    json={"name": "Без шаблона", "type": "Вычисляемая"},
)
check("вычисляемая без шаблона → 400", rcomp_bad.status_code == 400)

# дублирование с данными (предложение 2) — из колонки со значениями
rdu = client.post(
    f"/api/ucols/employees/{uc_id}/duplicate", headers=HB, json={"name": "Отдел копия"}
)
check("дублирование колонки", rdu.status_code == 201)
rchk3 = client.get(f"/api/data/employees/{own_id}", headers=HB)
check(
    "данные скопированы в копию", rchk3.json()["data"].get("Отдел копия") == "Цех Е2Е"
)

# скрытие (мягкое удаление)
rhid = client.put(f"/api/ucols/employees/{uc_id}", headers=HB, json={"visible": False})
rhid_l = client.get("/api/ucols/employees", headers=HB)
hid_item = next(i for i in rhid_l.json()["items"] if i["id"] == uc_id)
check(
    "скрытие: visible=0, данные на месте",
    hid_item["visible"] == 0 and rchk3.json()["data"].get("Отдел Е2Е") == "Цех Е2Е",
)
rrest2 = client.put(f"/api/ucols/employees/{uc_id}", headers=HB, json={"visible": True})
check("возврат колонки", rrest2.status_code == 200)

# удаление определения
rdel = client.delete(f"/api/ucols/employees/{rdu.json()['id']}", headers=HB)
check("удаление определения колонки", rdel.status_code == 200)

# чужая таблица u_ → 404
ru_bad = client.get("/api/ucols/u_something", headers=HB)
check("ucols для u_ таблиц → 404", ru_bad.status_code == 404)

print("== Вход ==")
rl_bad = client.post("/api/auth/login", json={"username": "boss", "password": "WRONG"})
check("неверный пароль → 401", rl_bad.status_code == 401)
rl_ok = client.post("/api/auth/login", json={"username": "BOSS", "password": "secret1"})
check("вход (регистронезависимо)", rl_ok.status_code == 200 and rl_ok.json()["token"])
rme = client.get(
    "/api/auth/me", headers={"Authorization": "Bearer " + rl_ok.json()["token"]}
)
check(
    "me → full_name",
    rme.status_code == 200 and rme.json()["user"]["full_name"] == "Босс Админов",
)

for _ in range(5):
    client.post("/api/auth/login", json={"username": "worker", "password": "x"})
rl_locked = client.post("/api/auth/login", json={"username": "worker", "password": "x"})
check("rate limit → 429 после 5 попыток", rl_locked.status_code == 429)

print("== Прочее ==")
rlang = client.post("/api/auth/language", json={"language": "en"})
check(
    "язык сохраняется",
    rlang.status_code == 200 and db.get_setting("app_language") == "en",
)
rmeta = client.get("/api/meta/employees", headers=HA)
check("meta таблицы", rmeta.status_code == 200 and "columns" in rmeta.json())
rnoauth = client.get("/api/data/employees")
check("без токена → 401", rnoauth.status_code == 401)
rbad = client.get(
    "/api/data/employees", headers={"Authorization": "Bearer garbage.token"}
)
check("битый токен → 401", rbad.status_code == 401)

mig = db.migrate_user_isolation()
check(
    "миграция идемпотентна (0 патчей повторно)",
    mig["records_assigned"] >= 0 and not mig["tables_patched"],
)

for suffix in ("", "-wal", "-shm"):
    try:
        os.remove(TMP_DB + suffix)
    except OSError:
        pass
print(f"\nИТОГО: {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print("Провалены:", FAIL)
    sys.exit(1)
