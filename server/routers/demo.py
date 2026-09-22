"""Генерация демонстрационных данных для нового пользователя.

Заполняет только те таблицы, где у пользователя ещё нет записей.
"""

import random
from datetime import date, timedelta
from typing import Any, Dict, List

random.seed(42)  # детерминированные демо-данные (стабильные тесты)

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from server.deps import get_db, get_current_user, is_admin
from services.database import DatabaseManager
from app_core.utils import JsonUtils

router = APIRouter(prefix="/api/demo", tags=["demo"])

_FIOS = [
    "Иванов Иван Иванович",
    "Петрова Мария Сергеевна",
    "Сидоров Алексей Петрович",
    "Кузнецова Ольга Дмитриевна",
    "Смирнов Дмитрий Андреевич",
    "Попов Сергей Викторович",
    "Васильева Анна Николаевна",
    "Морозов Павел Олегович",
    "Новикова Елена Владимировна",
    "Фёдоров Андрей Игоревич",
    "Козлова Татьяна Витальевна",
    "Лебедев Максим Романович",
]
_POSITIONS = [
    "Электрогазосварщик",
    "Монтажник",
    "Слесарь-ремонтник",
    "Оператор котельной",
    "Стропальщик",
    "Электромонтёр",
    "Мастер участка",
    "Инженер по ОТ",
    "Кладовщик",
    "Водитель погрузчика",
]
_DEPARTMENTS = [
    "Цех №1",
    "Цех №2",
    "Ремонтная служба",
    "Склад",
    "Транспортный участок",
    "Администрация",
]
_COMPANIES = [
    ("ООО ТехСтрой", "г. Москва, ул. Строителей, 15", "+7 (495) 123-45-67"),
    (
        "АО ПромБезопасность",
        "г. Санкт-Петербург, пр. Промышленный, 42",
        "+7 (812) 765-43-21",
    ),
    ("ИП Иванов", "г. Новосибирск, ул. Рабочая, 8", "+7 (383) 987-65-43"),
    ("ООО СевМеталл", "г. Челябинск, ш. Копейское, 22", "+7 (351) 111-22-33"),
]
_VIOLATION_DESCS = [
    "Работа без применения СИЗ органов дыхания в запылённой зоне",
    "Отсутствие ограждения зоны проведения работ на высоте",
    "Нарушение схемы строповки груза при перемещении краном",
    "Использование неисправного электроинструмента",
    "Нахождение в опасной зоне без разрешения ответственного",
    "Работа на высоте без страховочной привязи",
    "Загромождение эвакуационного выхода тарой",
    "Проведение огневых работ без наряда-допуска",
]
_STATUSES = ["Активно", "Устранено", "Просрочено"]
_INCIDENT_KINDS = [
    "Микротравма",
    "Несчастный случай (лёгкий)",
    "Аварийная ситуация",
    "Инцидент без травмы",
]
_ROOT_CAUSES = [
    "Нарушение технологии работ",
    "Неисправность оборудования",
    "Недостатки в обучении",
    "Усталость / невнимательность",
]
_PPE_NAMES = [
    ("Каска защитная СОМЗ-55", "шт"),
    ("Перчатки х/б с ПВХ", "пар"),
    ("Очки защитные ЗН", "шт"),
    ("Респиратор FFP2", "шт"),
    ("Ботинки с металлическим подноском", "пар"),
    ("Страховочная привязь", "шт"),
    ("Наушники SNR 27", "шт"),
]
_TRAINING_TOPICS = [
    "Охрана труда для рабочих",
    "Работы на высоте",
    "Пожарная безопасность",
    "Первая помощь пострадавшим",
    "Электробезопасность II группа",
    "Оказание первой помощи",
    "Промышленная безопасность",
]
_PERMIT_TYPES = [
    "Огневые работы",
    "Работы на высоте",
    "Газоопасные работы",
    "Работы в замкнутом пространстве",
]
_WORK_ORDER_TITLES = [
    "Плановый осмотр вентиляции",
    "Замена освещения в цеху",
    "Ремонт конвейера №3",
    "Проверка заземления",
    "Обслуживание огнетушителей",
]
_STATUS_DONE = ["Выполнено", "В работе", "Просрочено"]


def _rnd_date(back_days: int = 365) -> str:
    d = date.today() - timedelta(days=random.randint(0, back_days))
    return d.strftime("%d.%m.%Y")


def _future_date(days_ahead: int = 180) -> str:
    d = date.today() + timedelta(days=random.randint(10, days_ahead))
    return d.strftime("%d.%m.%Y")


def _fill_by_columns(
    columns: List[Dict[str, Any]], ctx: Dict[str, Any]
) -> Dict[str, Any]:
    """Заполняет поля по именам колонок из columns_config."""
    data: Dict[str, Any] = {}
    for c in columns:
        name = c["name"]
        if name == "ID":
            continue
        ctype = c.get("type", "Текст")
        low = name.lower()
        if "фио" in low or "сотрудник" in low:
            data[name] = random.choice(ctx["fios"])
        elif "фирм" in low or "компани" in low:
            data[name] = random.choice(ctx["company_names"])
        elif "подраздел" in low:
            data[name] = random.choice(_DEPARTMENTS)
        elif "должност" in low:
            data[name] = random.choice(_POSITIONS)
        elif "статус" in low:
            data[name] = random.choice(ctx.get("statuses", _STATUSES))
        elif "описан" in low or "причин" in low or "мероприя" in low:
            pool = ctx.get("desc_pool") or _ROOT_CAUSES
            data[name] = random.choice(pool)
        elif ctype == "Число":
            data[name] = random.randint(1, 200)
        elif ctype in ("Дата", "Дата проведения", "Годен до"):
            data[name] = (
                _future_date() if "годн" in low or "оконч" in low else _rnd_date()
            )
        elif ctype in ("Медиа", "Фото"):
            continue
        elif "наименован" in low or "тема" in low or "вид" in low:
            data[name] = random.choice(ctx.get("name_pool", _TRAINING_TOPICS))
        elif "номер" in low:
            data[name] = f"№{random.randint(100, 999)}"
        else:
            data[name] = ""
    return data


_DEMO_SPEC: Dict[str, Dict[str, Any]] = {
    "companies": {"count": len(_COMPANIES)},
    "employees": {"count": 10},
    "violations": {"count": 16, "extra": {"desc_pool": _VIOLATION_DESCS}},
    "incidents": {
        "count": 6,
        "extra": {"desc_pool": _ROOT_CAUSES, "name_pool": _INCIDENT_KINDS},
    },
    "ppe": {"count": 7},
    "ppe_inspections": {"count": 5},
    "training": {"count": 8},
    "permits": {"count": 5},
    "work_orders": {"count": 6},
    "custom_ledger": {"count": 6},
}


class SeedIn(BaseModel):
    tables: List[str] = []


@router.post("/seed")
def seed(body: SeedIn, db=Depends(get_db), user=Depends(get_current_user)):
    uid = int(user["id"])
    wanted = body.tables or list(_DEMO_SPEC.keys())
    created: Dict[str, int] = {}

    existing_companies = [
        r["data_json"].get("Наименование", "")
        for r in db.query_json_records(
            "companies", owner_id=uid, is_admin=is_admin(user), page_size=50
        )[0]
    ]
    try:
        legacy = db.fetch_all("SELECT DISTINCT name FROM companies WHERE name != ''")
        existing_companies += [r["name"] for r in legacy]
    except Exception:
        pass
    company_names = sorted({c for c in existing_companies if c}) or [
        n for n, _, _ in _COMPANIES
    ]

    for table in wanted:
        spec = _DEMO_SPEC.get(table)
        if not spec or table not in DatabaseManager.JSON_TABLES:
            continue
        rows, total = db.query_json_records(
            table, owner_id=uid, is_admin=is_admin(user), page_size=1
        )
        if total > 0:
            continue
        columns = [
            {"name": c["name"], "type": c["type"]} for c in db.get_columns_config(table)
        ]
        ctx = {"fios": _FIOS, "company_names": company_names, "statuses": _STATUSES}
        ctx.update(spec.get("extra", {}))
        n = 0
        for _ in range(spec["count"]):
            if table == "companies":
                # companies: легаси-колонка name NOT NULL + UNIQUE.
                # Добавляем только те компании, которых ещё нет в базе.
                nm, addr, ph = _COMPANIES[n % len(_COMPANIES)]
                exists = db.fetch_one("SELECT id FROM companies WHERE name=?", (nm,))
                if exists:
                    continue
                db.execute(
                    "INSERT INTO companies (name, address, contact, "
                    "data_json, user_id) VALUES (?, ?, ?, ?, ?)",
                    (
                        nm,
                        addr,
                        ph,
                        JsonUtils.dumps(
                            {"Наименование": nm, "Адрес": addr, "Телефон": ph}
                        ),
                        uid,
                    ),
                )
                db.commit()
                n += 1
                continue
            data = _fill_by_columns(columns, ctx)
            db.save_json_record(table, 0, data, user_id=uid)
            n += 1
        created[table] = n

    db.log_event(f"Demo data seeded for user {uid}", "INFO", {"created": created})
    return {"created": created}
