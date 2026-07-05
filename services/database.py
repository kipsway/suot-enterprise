import os, csv, json, sqlite3, hashlib, shutil, zipfile, tempfile, traceback
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime
from app_core.config import AppConfig, RUNTIME_PATHS
from app_core.utils import JsonUtils
from services.security import SecurityEngine
from services.session import SessionManager


class DatabaseManager:
    _instance: Optional["DatabaseManager"] = None
    _lock: Any = None
    _cache: Dict[str, tuple] = {}
    JSON_TABLES = {"employees", "violations", "custom_ledger", "incidents", "ppe", "training", "permits"}

    def invalidate_cache(self, category: str = "") -> None:
        if category:
            self._cache = {k: v for k, v in self._cache.items() if category not in k}
        else:
            self._cache.clear()

    def __new__(cls, *args: Any, **kwargs: Any) -> "DatabaseManager":
        if cls._instance is None:
            from threading import Lock
            cls._lock = Lock()
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DatabaseManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, database_path: Optional[str] = None) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.database_path = database_path or RUNTIME_PATHS.database_path
        self._lock = __import__('threading').Lock()
        self.conn = sqlite3.connect(self.database_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.execute("PRAGMA foreign_keys=ON;")
        self.conn.execute("PRAGMA busy_timeout=5000;")
        self.conn.execute("PRAGMA cache_size=-8000;")
        self._session_manager: Optional[SessionManager] = None
        self._init_schema()
        self._seed_defaults()
        self._fix_column_types()

    @property
    def session_manager(self) -> SessionManager:
        if self._session_manager is None:
            self._session_manager = SessionManager(self)
        return self._session_manager

    def _init_schema(self) -> None:
        try:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'Inspector',
                    session_token TEXT,
                    token_expiry TEXT,
                    totp_secret TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS columns_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL DEFAULT 'Текст',
                    position INTEGER NOT NULL DEFAULT 0,
                    visible INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(category, name)
                );
                CREATE TABLE IF NOT EXISTS employees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS custom_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS companies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    address TEXT DEFAULT '',
                    contact TEXT DEFAULT '',
                    data_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL DEFAULT 'global',
                    entity_id INTEGER,
                    title TEXT DEFAULT '',
                    content TEXT DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    due_date TEXT NOT NULL,
                    check_interval INTEGER NOT NULL DEFAULT 60,
                    is_done INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS custom_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    data_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS textbook (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    short_code TEXT UNIQUE NOT NULL,
                    full_text TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                    event TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'INFO',
                    details TEXT NOT NULL DEFAULT '{}',
                    username TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS backups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    file_path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    sha256 TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS print_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    template_type TEXT NOT NULL DEFAULT 'order',
                    html_content TEXT NOT NULL DEFAULT '',
                    css_content TEXT DEFAULT '',
                    is_default INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS ai_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL DEFAULT ''
                );
                CREATE TRIGGER IF NOT EXISTS trg_audit_insert_only
                BEFORE UPDATE ON audit_log
                BEGIN
                    SELECT RAISE(ABORT, 'Audit log is immutable');
                END;
                CREATE TRIGGER IF NOT EXISTS trg_audit_no_delete
                BEFORE DELETE ON audit_log
                BEGIN
                    SELECT RAISE(ABORT, 'Audit log is immutable');
                END;
                CREATE TABLE IF NOT EXISTS incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS ppe (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS training (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS permits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS violation_types (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    risk_category TEXT NOT NULL DEFAULT 'Средняя',
                    description TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS import_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                    table_name TEXT NOT NULL,
                    source_file TEXT,
                    imported INTEGER NOT NULL DEFAULT 0,
                    updated INTEGER NOT NULL DEFAULT 0,
                    errors INTEGER NOT NULL DEFAULT 0,
                    details TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_audit_severity ON audit_log(severity);
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
                CREATE INDEX IF NOT EXISTS idx_employees_json ON employees(data_json);
                CREATE INDEX IF NOT EXISTS idx_violations_json ON violations(data_json);
                CREATE INDEX IF NOT EXISTS idx_notes_entity ON notes(entity_type, entity_id);
                CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(due_date);
            """)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

        for tbl in ("employees", "violations", "custom_ledger", "incidents", "ppe", "training", "permits"):
            try:
                self.conn.execute(f"ALTER TABLE {tbl} ADD COLUMN user_id INTEGER DEFAULT 0")
            except Exception:
                pass
        self.conn.commit()

    def _insert_or_ignore(self, table: str, values: Dict[str, Any]) -> None:
        if table not in {"settings", "users", "ai_settings", "columns_config",
                          "violation_types", "reminders", "notes", "audit_log",
                          "employees", "violations", "custom_ledger", "companies",
                          "incidents", "ppe", "training", "permits"}:
            raise ValueError(f"Invalid table: {table}")
        try:
            cols = ", ".join(values.keys())
            plc = ", ".join(["?" for _ in values])
            self.conn.execute(f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({plc})",
                              tuple(values.values()))
        except Exception:
            self.conn.rollback()

    def _fix_column_types(self) -> None:
        try:
            fixes = {
                "employees": {
                    "Дата медосмотра": "Годен до",
                    "Дата проведения": "Дата проведения",
                    "Статус": "Статус",
                },
                "violations": {
                    "Дата": "Годен до",
                    "Срок устранения": "Годен до",
                    "Статус": "Статус",
                },
                "custom_ledger": {
                    "Дата": "Годен до",
                    "Статус": "Статус",
                },
            }
            for cat, col_fixes in fixes.items():
                for col_name, expected_type in col_fixes.items():
                    cur = self.conn.execute(
                        "SELECT type FROM columns_config WHERE category=? AND name=?",
                        (cat, col_name))
                    row = cur.fetchone()
                    if row and row["type"] != expected_type:
                        self.conn.execute(
                            "UPDATE columns_config SET type=? WHERE category=? AND name=?",
                            (expected_type, cat, col_name))
            self.conn.commit()
        except Exception:
            self.conn.rollback()

    def _seed_defaults(self) -> None:
        try:
            self._seed_settings()
            self._seed_column_configs()
            self._seed_textbook()
            self._seed_templates()
            self._seed_admin_user()
            self._seed_companies()
            self._seed_employees()
            self._seed_violations()
            self._seed_print_templates()
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            self.log_event(f"Seed failed: {traceback.format_exc()}", "CRITICAL")

    def _seed_settings(self) -> None:
        from app_core.i18n import I18n
        defaults = {
            "app_language": AppConfig.DEFAULT_LANG,
            "theme": AppConfig.DEFAULT_THEME,
            "accent_color": AppConfig.DEFAULT_ACCENT,
            "tab_dashboard": I18n._("tab.dashboard"),
            "tab_employees": I18n._("tab.employees"),
            "tab_violations": I18n._("tab.violations"),
            "tab_companies": I18n._("tab.companies"),
            "tab_custom_ledger": I18n._("tab.custom_ledger"),
            "tab_statistics": I18n._("tab.statistics"),
            "tab_audit": I18n._("tab.audit"),
            "tab_ai": I18n._("tab.ai"),
            "tab_reminders": I18n._("tab.reminders"),
            "auto_save_interval": str(AppConfig.AUTO_SAVE_INTERVAL),
            "reminder_check_interval": str(AppConfig.REMINDER_CHECK_INTERVAL),
            "media_path": RUNTIME_PATHS.media_dir,
            "remember_me_token": "",
            "remember_me_expiry": "",
        }
        for k, v in defaults.items():
            self._insert_or_ignore("settings", {"key": k, "value": str(v)})

    def _seed_column_configs(self) -> None:
        configs: Dict[str, List[Tuple[str, str, int]]] = {
            "employees": [
                ("ID", "Число", 0), ("ФИО", "Текст", 1),
                ("Должность", "Текст", 2), ("Подразделение", "Текст", 3),
                ("Фирма", "Текст", 4), ("Телефон", "Текст", 5),
                ("Дата медосмотра", "Годен до", 6), ("Квалификация", "Текст", 7),
                ("Дата проведения", "Дата проведения", 8),
                ("Фото", "Медиа", 9), ("Статус", "Статус", 10),
            ],
            "violations": [
                ("ID", "Число", 0), ("Дата", "Годен до", 1),
                ("Фирма", "Текст", 2), ("Подразделение", "Текст", 3),
                ("Категория риска", "Текст", 4), ("Описание", "Текст", 5),
                ("Ответственный", "Текст", 6), ("Срок устранения", "Годен до", 7),
                ("Штраф", "Число", 8), ("Статус", "Статус", 9),
                ("Фото", "Медиа", 10),
            ],
            "custom_ledger": [
                ("ID", "Число", 0), ("Дата", "Годен до", 1),
                ("Категория", "Текст", 2), ("Описание", "Текст", 3),
                ("Ответственный", "Текст", 4), ("Статус", "Статус", 5),
                ("Фото", "Медиа", 6), ("Примечание", "Текст", 7),
            ],
            "incidents": [
                ("ID", "Число", 0), ("Дата происшествия", "Годен до", 1),
                ("Время", "Текст", 2), ("Тип", "Текст", 3),
                ("Тяжесть", "Статус", 4), ("Место", "Текст", 5),
                ("Описание", "Текст", 6), ("Пострадавшие", "Текст", 7),
                ("Причина", "Текст", 8), ("Корректирующие меры", "Текст", 9),
                ("Срок устранения", "Годен до", 10), ("Статус", "Статус", 11),
                ("Фото", "Медиа", 12),
            ],
            "ppe": [
                ("ID", "Число", 0), ("Сотрудник", "Текст", 1),
                ("Наименование СИЗ", "Текст", 2), ("Тип", "Текст", 3),
                ("ГОСТ/ТР", "Текст", 4), ("Ед.изм.", "Текст", 5),
                ("Количество", "Число", 6), ("Норма на год", "Число", 7),
                ("Дата выдачи", "Годен до", 8), ("Срок замены", "Годен до", 9),
                ("Статус", "Статус", 10), ("Примечание", "Текст", 11),
            ],
            "training": [
                ("ID", "Число", 0), ("Сотрудник", "Текст", 1),
                ("Наименование", "Текст", 2), ("Тип обучения", "Текст", 3),
                ("Обучающая организация", "Текст", 4),
                ("Дата проведения", "Годен до", 5),
                ("Срок действия", "Годен до", 6),
                ("Номер удостоверения", "Текст", 7),
                ("Статус", "Статус", 8), ("Примечание", "Текст", 9),
            ],
            "permits": [
                ("ID", "Число", 0), ("Номер наряда", "Текст", 1),
                ("Тип работ", "Текст", 2), ("Описание работ", "Текст", 3),
                ("Место проведения", "Текст", 4),
                ("Ответственный", "Текст", 5), ("Состав бригады", "Текст", 6),
                ("Дата начала", "Годен до", 7),
                ("Дата окончания", "Годен до", 8),
                ("Меры безопасности", "Текст", 9),
                ("Статус", "Статус", 10), ("Примечание", "Текст", 11),
            ],
        }
        for cat, cols in configs.items():
            for name, typ, pos in cols:
                self._insert_or_ignore("columns_config", {
                    "category": cat, "name": name, "type": typ, "position": pos,
                })

    def _seed_textbook(self) -> None:
        items = {
            "сиз": "Средства индивидуальной защиты должны применяться в соответствии "
                   "с требованиями охраны труда, утверждёнными работодателем. Работник "
                   "обязан использовать выданные средства по назначению, хранить их в "
                   "установленном месте и своевременно сообщать о повреждении или утрате.",
            "ограждение": "Ограждение опасных зон должно быть выполнено таким образом, "
                          "чтобы исключать несанкционированный доступ работников. Ограждения "
                          "должны быть устойчивыми, видимыми и сопровождаться "
                          "предупредительными знаками безопасности.",
            "инструктаж": "Инструктаж по охране труда проводится в установленном порядке "
                          "до допуска работника к самостоятельной работе. Факт проведения "
                          "инструктажа фиксируется в журнале с подписями инструктируемого "
                          "и инструктирующего лица.",
            "лоут": "Лист оценки условий труда используется для фиксации выявленных опасных "
                    "и вредных производственных факторов, а также для планирования "
                    "корректирующих мероприятий.",
            "журнал": "Журнал регистрации инструктажей является документом внутреннего "
                      "контроля и должен храниться в соответствии с установленными сроками "
                      "документооборота организации.",
            "пожар": "Пожарная безопасность: все работники должны знать пути эвакуации, "
                     "места расположения огнетушителей и планы действий при пожаре.",
            "электро": "Электробезопасность: работы с электрооборудованием должны "
                       "проводиться только обученным персоналом с соответствующей "
                       "группой допуска.",
            "высота": "Работы на высоте: обязательное применение страховочных систем, "
                      "предохранительных поясов и наличие наряда-допуска.",
        }
        for code, text in items.items():
            self._insert_or_ignore("textbook", {"short_code": code, "full_text": text})

    def _seed_templates(self) -> None:
        templates = [
            {"name": "Нарушение применения СИЗ", "data": {"category": "Средства индивидуальной защиты", "risk_level": "Средний", "regulation": "Требования охраны труда по применению СИЗ", "recommended_action": "Выдать средства защиты, провести повторный инструктаж, зафиксировать нарушение в журнале."}},
            {"name": "Отсутствие ограждения", "data": {"category": "Опасные зоны", "risk_level": "Высокий", "regulation": "Требования к ограждению опасных производственных зон", "recommended_action": "Установить временное или постоянное ограждение опасной зоны, разместить предупреждающие знаки."}},
            {"name": "Непроведение инструктажа", "data": {"category": "Обучение и инструктаж", "risk_level": "Высокий", "regulation": "Требования к проведению инструктажей по охране труда", "recommended_action": "Немедленно провести целевой инструктаж, внести запись в журнал, назначить ответственное лицо."}},
            {"name": "Нарушение электробезопасности", "data": {"category": "Электробезопасность", "risk_level": "Высокий", "regulation": "Правила устройства электроустановок (ПУЭ)", "recommended_action": "Отстранить работника, провести внеочередную проверку знаний, устранить нарушение."}},
            {"name": "Пожарная безопасность", "data": {"category": "Пожарная безопасность", "risk_level": "Критический", "regulation": "Правила противопожарного режима в РФ", "recommended_action": "Устранить нарушение, провести внеплановый противопожарный инструктаж."}},
        ]
        for t in templates:
            self._insert_or_ignore("custom_templates", {
                "name": t["name"], "data_json": JsonUtils.dumps(t["data"]),
            })

    def _seed_admin_user(self) -> None:
        if self.fetch_one("SELECT id FROM users"):
            return
        pw_hash, salt = SecurityEngine.generate_hash("admin")
        self.conn.execute(
            "INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)",
            ("admin", pw_hash, salt, "Administrator"),
        )
        self.log_event("Default admin user created (admin/admin)", "WARNING")

    def _seed_companies(self) -> None:
        if self.fetch_one("SELECT id FROM companies"):
            return
        companies = [
            ("ООО ТехСтрой", "г. Москва, ул. Строителей, 15", "+7 (495) 123-45-67"),
            ("АО ПромБезопасность", "г. Санкт-Петербург, пр. Промышленный, 42", "+7 (812) 765-43-21"),
            ("ИП Иванов", "г. Новосибирск, ул. Рабочая, 8", "+7 (383) 987-65-43"),
        ]
        for name, addr, contact in companies:
            self.conn.execute(
                "INSERT INTO companies (name, address, contact) VALUES (?, ?, ?)",
                (name, addr, contact),
            )
        self.log_event("Demo companies seeded", "INFO")

    def _seed_employees(self) -> None:
        if self.fetch_one("SELECT id FROM employees"):
            return
        now = datetime.now()
        employees = [
            ("Иванов Иван Иванович", "Инженер по охране труда", "ОТиПБ", "ООО ТехСтрой", "+7 (495) 111-11-11", (now - timedelta(days=30)).strftime("%d.%m.%Y"), "5-й уровень", (now - timedelta(days=180)).strftime("%d.%m.%Y"), "Активен"),
            ("Петров Пётр Петрович", "Начальник цеха", "Цех №1", "ООО ТехСтрой", "+7 (495) 111-11-12", (now - timedelta(days=45)).strftime("%d.%m.%Y"), "4-й уровень", (now - timedelta(days=90)).strftime("%d.%m.%Y"), "Активен"),
            ("Сидоров Сидор Сидорович", "Электромонтёр", "Электроцех", "ООО ТехСтрой", "+7 (495) 111-11-13", (now - timedelta(days=320)).strftime("%d.%m.%Y"), "3-й уровень", (now - timedelta(days=60)).strftime("%d.%m.%Y"), "Активен"),
            ("Кузнецов Алексей Сергеевич", "Сварщик", "Цех №2", "ООО ТехСтрой", "+7 (495) 111-11-14", (now - timedelta(days=15)).strftime("%d.%m.%Y"), "4-й уровень", (now - timedelta(days=30)).strftime("%d.%m.%Y"), "Активен"),
            ("Смирнова Ольга Владимировна", "Бухгалтер", "Бухгалтерия", "ООО ТехСтрой", "+7 (495) 111-11-15", (now - timedelta(days=180)).strftime("%d.%m.%Y"), "5-й уровень", "", "Активен"),
            ("Васильев Дмитрий Андреевич", "Инспектор по охране труда", "ОТиПБ", "АО ПромБезопасность", "+7 (812) 222-22-21", (now - timedelta(days=10)).strftime("%d.%m.%Y"), "5-й уровень", (now - timedelta(days=45)).strftime("%d.%m.%Y"), "Активен"),
            ("Николаев Артём Павлович", "Начальник смены", "Смена №1", "АО ПромБезопасность", "+7 (812) 222-22-22", (now - timedelta(days=365)).strftime("%d.%m.%Y"), "4-й уровень", (now - timedelta(days=365)).strftime("%d.%m.%Y"), "Архив"),
            ("Козлова Елена Михайловна", "Химик-лаборант", "Лаборатория", "АО ПромБезопасность", "+7 (812) 222-22-23", (now - timedelta(days=200)).strftime("%d.%m.%Y"), "4-й уровень", (now - timedelta(days=120)).strftime("%d.%m.%Y"), "Активен"),
            ("Морозов Сергей Викторович", "Грузчик", "Склад", "АО ПромБезопасность", "+7 (812) 222-22-24", (now - timedelta(days=5)).strftime("%d.%m.%Y"), "2-й уровень", (now - timedelta(days=15)).strftime("%d.%m.%Y"), "Активен"),
            ("Фёдорова Анна Павловна", "Секретарь", "Администрация", "АО ПромБезопасность", "+7 (812) 222-22-25", (now - timedelta(days=90)).strftime("%d.%m.%Y"), "3-й уровень", "", "Активен"),
            ("Григорьев Илья Алексеевич", "Разнорабочий", "Производство", "ИП Иванов", "+7 (383) 333-33-31", (now - timedelta(days=60)).strftime("%d.%m.%Y"), "2-й уровень", (now - timedelta(days=10)).strftime("%d.%m.%Y"), "Активен"),
            ("Тимофеев Максим Денисович", "Водитель", "Транспорт", "ИП Иванов", "+7 (383) 333-33-32", (now - timedelta(days=365 + 30)).strftime("%d.%m.%Y"), "3-й уровень", (now - timedelta(days=200)).strftime("%d.%m.%Y"), "Активен"),
            ("Архипов Виктор Николаевич", "Кладовщик", "Склад", "ИП Иванов", "+7 (383) 333-33-33", (now - timedelta(days=25)).strftime("%d.%m.%Y"), "3-й уровень", (now - timedelta(days=90)).strftime("%d.%m.%Y"), "Активен"),
            ("Белова Татьяна Олеговна", "Уборщица", "Хоз. часть", "ИП Иванов", "+7 (383) 333-33-34", (now - timedelta(days=150)).strftime("%d.%m.%Y"), "1-й уровень", "", "Активен"),
            ("Дмитриев Константин Борисович", "Менеджер", "Офис", "ИП Иванов", "+7 (383) 333-33-35", (now - timedelta(days=45)).strftime("%d.%m.%Y"), "4-й уровень", (now - timedelta(days=30)).strftime("%d.%m.%Y"), "Активен"),
        ]
        for emp in employees:
            data = {
                "ФИО": emp[0], "Должность": emp[1], "Подразделение": emp[2],
                "Фирма": emp[3], "Телефон": emp[4], "Дата медосмотра": emp[5],
                "Квалификация": emp[6], "Дата проведения": emp[7], "Статус": emp[8],
                "Фото": [],
            }
            self.conn.execute("INSERT INTO employees (data_json) VALUES (?)",
                              (JsonUtils.dumps(data),))
        self.log_event("Demo employees seeded (15 records)", "INFO")

    def _seed_violations(self) -> None:
        if self.fetch_one("SELECT id FROM violations"):
            return
        now = datetime.now()
        violations = [
            ("10.01.2024", "ООО ТехСтрой", "Цех №1", "Средства индивидуальной защиты", "Работник находился на рабочем месте без защитной каски", "Петров Пётр Петрович", (now - timedelta(days=10)).strftime("%d.%m.%Y"), "5000", "Активно"),
            ("15.02.2024", "ООО ТехСтрой", "Цех №2", "Электробезопасность", "Неисправность заземления электрооборудования", "Кузнецов Алексей Сергеевич", (now + timedelta(days=20)).strftime("%d.%m.%Y"), "15000", "Активно"),
            ("20.03.2024", "АО ПромБезопасность", "Лаборатория", "Пожарная безопасность", "Загромождение путей эвакуации", "Козлова Елена Михайловна", (now - timedelta(days=5)).strftime("%d.%m.%Y"), "10000", "Активно"),
            ("05.04.2024", "АО ПромБезопасность", "Склад", "Опасные зоны", "Отсутствует ограждение опасной зоны погрузки", "Морозов Сергей Викторович", (now - timedelta(days=60)).strftime("%d.%m.%Y"), "20000", "Просрочено"),
            ("12.05.2024", "ИП Иванов", "Производство", "Обучение и инструктаж", "Не проведён инструктаж новому работнику", "Григорьев Илья Алексеевич", (now + timedelta(days=5)).strftime("%d.%m.%Y"), "8000", "Активно"),
            ("01.06.2024", "ИП Иванов", "Транспорт", "Средства индивидуальной защиты", "Отсутствие сигнального жилета у водителя", "Тимофеев Максим Денисович", (now - timedelta(days=90)).strftime("%d.%m.%Y"), "3000", "Исполнено"),
            ("15.06.2024", "ООО ТехСтрой", "ОТиПБ", "Документация", "Отсутствует журнал регистрации инструктажей", "Иванов Иван Иванович", (now + timedelta(days=45)).strftime("%d.%m.%Y"), "5000", "Активно"),
            ("20.07.2024", "АО ПромБезопасность", "Администрация", "Пожарная безопасность", "Не проведена проверка огнетушителей", "Фёдорова Анна Павловна", (now - timedelta(days=365)).strftime("%d.%m.%Y"), "7000", "Исполнено"),
        ]
        for v in violations:
            data = {
                "Дата": v[0], "Фирма": v[1], "Подразделение": v[2],
                "Категория риска": v[3], "Описание": v[4],
                "Ответственный": v[5], "Срок устранения": v[6],
                "Штраф": v[7], "Статус": v[8], "Фото": [],
            }
            self.conn.execute("INSERT INTO violations (data_json) VALUES (?)",
                              (JsonUtils.dumps(data),))
        self.log_event("Demo violations seeded (8 records)", "INFO")

    def _seed_print_templates(self) -> None:
        if self.fetch_one("SELECT id FROM print_templates"):
            return
        default_order_html = """<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8">
<style>
body{font-family:'Segoe UI',Arial,sans-serif;margin:40px;color:#333;line-height:1.6}
h1{color:#1a237e;border-bottom:2px solid #1a237e;padding-bottom:10px;font-size:24px}
h2{color:#283593;font-size:18px;margin-top:30px}
.meta{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:20px 0;padding:15px;background:#f5f5f5;border-radius:6px}
.meta div{font-size:14px}
.label{color:#666;font-weight:600}
.content{margin:20px 0;padding:15px;border:1px solid #e0e0e0;border-radius:6px}
.photos{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:15px;margin-top:20px}
.photos img{width:100%;border-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,.15)}
.footer{margin-top:40px;padding-top:15px;border-top:1px solid #e0e0e0;font-size:12px;color:#999;text-align:center}
</style></head>
<body>
<h1>ПРЕДПИСАНИЕ №{id}</h1>
<div class="meta">
<div><span class="label">Дата:</span> {date}</div>
<div><span class="label">Фирма:</span> {company}</div>
<div><span class="label">Ответственный:</span> {responsible}</div>
<div><span class="label">Срок устранения:</span> {deadline}</div>
</div>
<div class="content">
<h2>Описание нарушения</h2>
<p>{description}</p>
<h2>Рекомендуемые меры</h2>
<p>{recommended_action}</p>
{h2}<p>Сумма штрафа: <strong>{fine} руб.</strong></p>
</div>
{photos_section}
<div class="footer">{app_name} — Документ сформирован {generated_at}</div>
</body></html>"""
        default_report_html = """<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8">
<style>
body{font-family:'Segoe UI',Arial,sans-serif;margin:40px;color:#333;line-height:1.6}
h1{color:#1a237e;border-bottom:2px solid #1a237e;padding-bottom:10px}
table{width:100%;border-collapse:collapse;margin:20px 0}
th{background:#1a237e;color:#fff;padding:10px;text-align:left;font-size:14px}
td{padding:8px 10px;border-bottom:1px solid #e0e0e0;font-size:13px}
tr:nth-child(even){background:#f5f5f5}
.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:15px;margin:20px 0}
.card{padding:15px;background:#f5f5f5;border-radius:8px;text-align:center}
.card .value{font-size:28px;font-weight:700;color:#1a237e}
.card .label{font-size:12px;color:#666;margin-top:5px}
.footer{margin-top:40px;padding-top:15px;border-top:1px solid #e0e0e0;font-size:12px;color:#999;text-align:center}
</style></head>
<body>
<h1>ОТЧЁТ ПО ОХРАНЕ ТРУДА</h1>
<p><strong>Фирма:</strong> {company_name} | <strong>Дата:</strong> {date}</p>
<div class="summary">
<div class="card"><div class="value">{emp_count}</div><div class="label">Сотрудников</div></div>
<div class="card"><div class="value">{viol_count}</div><div class="label">Нарушений</div></div>
<div class="card"><div class="value">{fines_total} ₽</div><div class="label">Штрафов</div></div>
<div class="card"><div class="value">{overdue_count}</div><div class="label">Просрочено</div></div>
</div>
{table_html}
<div class="footer">{app_name} — Отчёт сформирован {generated_at}</div>
</body></html>"""
        self.conn.execute("""INSERT INTO print_templates (name, template_type, html_content, is_default)
            VALUES (?, ?, ?, 1)""", ("Стандартное предписание", "order", default_order_html))
        self.conn.execute("""INSERT INTO print_templates (name, template_type, html_content, is_default)
            VALUES (?, ?, ?, 1)""", ("Стандартный отчёт", "report", default_report_html))
        self.log_event("Default print templates seeded", "INFO")

    def execute(self, sql: str, params: Tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock:
            try:
                return self.conn.execute(sql, params)
            except Exception:
                self.conn.rollback()
                self.log_event(f"SQL error: {traceback.format_exc()}", "CRITICAL")
                raise

    def commit(self) -> None:
        with self._lock:
            try:
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                self.log_event(f"Commit error: {traceback.format_exc()}", "CRITICAL")
                raise

    def rollback(self) -> None:
        with self._lock:
            try:
                self.conn.rollback()
            except Exception:
                self.log_event(f"Rollback error: {traceback.format_exc()}", "CRITICAL")

    def fetch_all(self, sql: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        with self._lock:
            try:
                return [dict(r) for r in self.conn.execute(sql, params).fetchall()]
            except Exception:
                self.conn.rollback()
                self.log_event(f"Fetch error: {traceback.format_exc()}", "CRITICAL")
                return []

    def fetch_one(self, sql: str, params: Tuple[Any, ...] = ()) -> Optional[Dict[str, Any]]:
        with self._lock:
            try:
                r = self.conn.execute(sql, params).fetchone()
                return dict(r) if r else None
            except Exception:
                self.conn.rollback()
                self.log_event(f"Fetch one error: {traceback.format_exc()}", "CRITICAL")
                return None

    def upsert_setting(self, key: str, value: Any) -> None:
        try:
            self.conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            self.log_event(f"Setting upsert error: {traceback.format_exc()}", "CRITICAL")

    def get_setting(self, key: str, default: Any = None) -> Any:
        r = self.fetch_one("SELECT value FROM settings WHERE key=?", (key,))
        return r["value"] if r else default

    def get_all_settings(self) -> Dict[str, str]:
        rows = self.fetch_all("SELECT key, value FROM settings")
        return {r["key"]: r["value"] for r in rows}

    def log_event(self, event: str, severity: str = "INFO",
                  details: Optional[Dict[str, Any]] = None,
                  username: str = "") -> None:
        try:
            self.conn.execute(
                "INSERT INTO audit_log (timestamp, event, severity, details, username) "
                "VALUES (?, ?, ?, ?, ?)",
                (datetime.now().isoformat(), event, severity,
                 JsonUtils.dumps(details or {}), username))
            self.conn.commit()
        except Exception:
            self.conn.rollback()

    def get_audit_events(self, limit: int = 500,
                         severity: Optional[str] = None) -> List[Dict[str, Any]]:
        if severity:
            return self.fetch_all(
                "SELECT * FROM audit_log WHERE severity=? ORDER BY id DESC LIMIT ?",
                (severity, limit))
        return self.fetch_all(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))

    def _validate_json_table(self, name: str) -> str:
        if name not in self.JSON_TABLES:
            raise ValueError(f"Unsupported JSON table: {name}")
        return name

    def find_violation_duplicate(self, data: Dict[str, Any], exclude_id: int = 0,
                                 user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        date = str(data.get("Дата", "")).strip()
        if not date:
            return None
        company = str(data.get("Фирма", "")).strip().lower()
        department = str(data.get("Подразделение", "")).strip().lower()
        description = str(data.get("Описание", "")).strip().lower()
        for rec in self.get_json_records("violations", user_id=user_id):
            if exclude_id and int(rec.get("id", 0)) == int(exclude_id):
                continue
            dj = rec.get("data_json", {})
            if str(dj.get("Дата", "")).strip() != date:
                continue
            rec_company = str(dj.get("Фирма", "")).strip().lower()
            rec_department = str(dj.get("Подразделение", "")).strip().lower()
            rec_description = str(dj.get("Описание", "")).strip().lower()
            if company and rec_company and company != rec_company:
                continue
            if department and rec_department and department != rec_department:
                continue
            if description and rec_description and description != rec_description:
                continue
            return rec
        return None

    def find_duplicate(self, table: str, data: Dict[str, Any],
                       exclude_id: int = 0,
                       user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        self._validate_json_table(table)
        cols = self.get_columns_config(table)
        text_cols = {c["name"] for c in cols if c["type"] == "Текст"}
        name_col = None
        for n in ("ФИО", "Наименование", "Наименование СИЗ", "Номер наряда",
                   "Описание", "Сотрудник"):
            if n in text_cols:
                name_col = n
                break
        if not name_col:
            return None
        val = str(data.get(name_col, "")).strip().lower()
        if not val:
            return None
        for rec in self.get_json_records(table, user_id=user_id):
            if exclude_id and int(rec.get("id", 0)) == int(exclude_id):
                continue
            rv = str(rec.get("data_json", {}).get(name_col, "")).strip().lower()
            if rv == val:
                return rec
            if len(val) > 5 and (rv.startswith(val) or val.startswith(rv)):
                return rec
        return None

    def get_import_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        rows = self.fetch_all(
            "SELECT * FROM import_history ORDER BY timestamp DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows] if rows else []

    def merge_duplicates(self, table: str, user_id: Optional[int] = None) -> int:
        merged = 0
        if table == "employees":
            merged = self._merge_employees(user_id)
        elif table == "violations":
            merged = self._merge_violations(user_id)
        elif table == "custom_ledger":
            merged = self._merge_ledger(user_id)
        return merged

    def _merge_employees(self, user_id: Optional[int] = None) -> int:
        records = self.get_json_records("employees", user_id=user_id)
        seen: Dict[str, Dict[str, Any]] = {}
        merged = 0
        for rec in records:
            dj = rec.get("data_json", {})
            key = (
                str(dj.get("ФИО", "")).strip().lower(),
                str(dj.get("Фирма", "")).strip().lower(),
                str(dj.get("Подразделение", "")).strip().lower(),
            )
            if key in seen:
                existing = seen[key]
                merged_data = dict(existing.get("data_json", {}))
                for k, v in dj.items():
                    if isinstance(v, list):
                        if v:
                            merged_data[k] = v
                    elif str(v).strip():
                        merged_data[k] = v
                self.save_json_record("employees", existing["id"], merged_data, user_id=user_id)
                self.delete_json_record("employees", rec["id"])
                merged += 1
            else:
                seen[key] = rec
        return merged

    def _merge_violations(self, user_id: Optional[int] = None) -> int:
        records = self.get_json_records("violations", user_id=user_id)
        seen: Dict[tuple, Dict[str, Any]] = {}
        merged = 0
        for rec in records:
            dj = rec.get("data_json", {})
            key = (
                str(dj.get("Дата", "")).strip(),
                str(dj.get("Фирма", "")).strip().lower(),
                str(dj.get("Подразделение", "")).strip().lower(),
                str(dj.get("Описание", "")).strip().lower(),
            )
            if key in seen:
                existing = seen[key]
                merged_data = dict(existing.get("data_json", {}))
                for k, v in dj.items():
                    if isinstance(v, list):
                        if v:
                            merged_data[k] = v
                    elif str(v).strip():
                        merged_data[k] = v
                self.save_json_record("violations", existing["id"], merged_data, user_id=user_id)
                self.delete_json_record("violations", rec["id"])
                merged += 1
            else:
                seen[key] = rec
        return merged

    def _merge_ledger(self, user_id: Optional[int] = None) -> int:
        records = self.get_json_records("custom_ledger", user_id=user_id)
        seen: Dict[str, Dict[str, Any]] = {}
        merged = 0
        for rec in records:
            dj = rec.get("data_json", {})
            key = (
                str(dj.get("Дата", "")).strip(),
                str(dj.get("Категория", "")).strip().lower(),
                str(dj.get("Описание", "")).strip().lower(),
            )
            if key in seen:
                existing = seen[key]
                merged_data = dict(existing.get("data_json", {}))
                for k, v in dj.items():
                    if isinstance(v, list):
                        if v:
                            merged_data[k] = v
                    elif str(v).strip():
                        merged_data[k] = v
                self.save_json_record("custom_ledger", existing["id"], merged_data, user_id=user_id)
                self.delete_json_record("custom_ledger", rec["id"])
                merged += 1
            else:
                seen[key] = rec
        return merged

    def save_json_record(self, table: str, record_id: int,
                         data: Dict[str, Any],
                         user_id: int = 0) -> int:
        self._validate_json_table(table)
        self.invalidate_cache(table)
        try:
            payload = JsonUtils.dumps(data)
            if record_id > 0:
                exists = self.fetch_one(f"SELECT id FROM {table} WHERE id=?", (record_id,))
                if exists:
                    self.conn.execute(
                        f"UPDATE {table} SET data_json=?, updated_at=datetime('now') "
                        f"WHERE id=?", (payload, record_id))
                    self.conn.commit()
                    self.log_event(f"Record updated in {table}", "INFO", {"id": record_id})
                    return record_id
            cur = self.conn.execute(
                f"INSERT INTO {table} (data_json, user_id) VALUES (?, ?)",
                (payload, user_id))
            self.conn.commit()
            new_id = int(cur.lastrowid)
            self.log_event(f"Record inserted in {table}", "INFO", {"id": new_id})
            return new_id
        except Exception:
            self.conn.rollback()
            self.log_event(f"Save record error: {traceback.format_exc()}", "CRITICAL")
            raise

    def get_json_records(self, table: str, limit: int = 2000,
                         user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        from time import time
        cache_key = f"records:{table}:{limit}:{user_id}"
        if cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if time() - ts < 1.0:
                return data
        self._validate_json_table(table)
        if user_id:
            rows = self.fetch_all(
                f"SELECT id, data_json, created_at, updated_at, user_id "
                f"FROM {table} WHERE user_id=? OR user_id=0 ORDER BY id DESC LIMIT ?",
                (user_id, limit))
        else:
            rows = self.fetch_all(
                f"SELECT id, data_json, created_at, updated_at, user_id "
                f"FROM {table} ORDER BY id DESC LIMIT ?",
                (limit,))
        result: List[Dict[str, Any]] = []
        for r in rows:
            dj = JsonUtils.loads(r["data_json"])
            rec: Dict[str, Any] = {"id": r["id"], "data_json": dj}
            rec.update(dj)
            result.append(rec)
        self._cache[cache_key] = (time(), result)
        return result

    def get_json_record(self, table: str, record_id: int) -> Optional[Dict[str, Any]]:
        self._validate_json_table(table)
        r = self.fetch_one(
            f"SELECT id, data_json, created_at, updated_at FROM {table} WHERE id=?",
            (record_id,))
        if not r:
            return None
        dj = JsonUtils.loads(r["data_json"])
        rec: Dict[str, Any] = {"id": r["id"], "data_json": dj}
        rec.update(dj)
        return rec

    def delete_json_record(self, table: str, record_id: int) -> bool:
        self._validate_json_table(table)
        self.invalidate_cache(table)
        try:
            self.create_backup()
            self.conn.execute(f"DELETE FROM {table} WHERE id=?", (record_id,))
            self.conn.commit()
            self.log_event("Record deleted", "WARNING", {"table": table, "id": record_id})
            return True
        except Exception:
            self.conn.rollback()
            self.log_event(f"Delete error: {traceback.format_exc()}", "CRITICAL")
            return False

    def get_columns_config(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        from time import time
        cache_key = f"columns:{category or 'all'}"
        if cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if time() - ts < 2.0:
                return data
        if category:
            result = self.fetch_all(
                "SELECT * FROM columns_config WHERE category=? ORDER BY position",
                (category,))
        else:
            result = self.fetch_all(
                "SELECT * FROM columns_config ORDER BY category, position")
        self._cache[cache_key] = (time(), result)
        return result

    def set_columns_config(self, category: str,
                           configs: List[Tuple[str, str, int]]) -> None:
        self.invalidate_cache(f"columns:{category}")
        try:
            self.create_backup()
            self.conn.execute("DELETE FROM columns_config WHERE category=?", (category,))
            for name, typ, pos in configs:
                self.conn.execute(
                    "INSERT INTO columns_config (category, name, type, position) "
                    "VALUES (?, ?, ?, ?)", (category, name, typ, pos))
            self.conn.commit()
            self.log_event(f"Columns config updated for {category}", "INFO")
        except Exception:
            self.conn.rollback()
            self.log_event(f"Columns config error: {traceback.format_exc()}", "CRITICAL")
            raise

    def rename_column(self, category: str, old_name: str,
                      new_name: str) -> bool:
        if not new_name or old_name == new_name:
            return False
        dup = self.fetch_one(
            "SELECT id FROM columns_config WHERE category=? AND name=?",
            (category, new_name))
        if dup:
            return False
        table_map = {"employees": "employees", "violations": "violations",
                     "custom_ledger": "custom_ledger"}
        table = table_map.get(category)
        if not table:
            return False
        try:
            self.create_backup()
            self.invalidate_cache(f"columns:{category}")
            self.conn.execute(
                "UPDATE columns_config SET name=? WHERE category=? AND name=?",
                (new_name, category, old_name))
            self._migrate_json_key(table, old_name, new_name)
            self.conn.commit()
            self.log_event("Column renamed", "INFO", {
                "category": category, "old": old_name, "new": new_name})
            return True
        except Exception:
            self.conn.rollback()
            self.log_event(f"Rename column error: {traceback.format_exc()}", "CRITICAL")
            return False

    def add_column(self, category: str, name: str, typ: str) -> bool:
        if not name:
            return False
        dup = self.fetch_one(
            "SELECT id FROM columns_config WHERE category=? AND name=?",
            (category, name))
        if dup:
            return False
        max_pos = self.fetch_one(
            "SELECT MAX(position) as mp FROM columns_config WHERE category=?",
            (category,))
        pos = (max_pos["mp"] + 1) if (max_pos is not None and max_pos["mp"] is not None) else 0
        try:
            self.invalidate_cache(f"columns:{category}")
            self.conn.execute(
                "INSERT INTO columns_config (category, name, type, position) "
                "VALUES (?, ?, ?, ?)", (category, name, typ, pos))
            self.conn.commit()
            self.log_event("Column added", "INFO", {"category": category, "name": name})
            return True
        except Exception:
            self.conn.rollback()
            self.log_event(f"Add column error: {traceback.format_exc()}", "CRITICAL")
            return False

    def delete_column(self, category: str, name: str) -> bool:
        try:
            self.create_backup()
            self.invalidate_cache(f"columns:{category}")
            self.conn.execute(
                "DELETE FROM columns_config WHERE category=? AND name=?",
                (category, name))
            table_map = {"employees": "employees", "violations": "violations",
                         "custom_ledger": "custom_ledger"}
            table = table_map.get(category)
            if table:
                rows = self.fetch_all(f"SELECT id, data_json FROM {table}")
                for r in rows:
                    dj = JsonUtils.loads(r["data_json"])
                    if name in dj:
                        del dj[name]
                        self.conn.execute(
                            f"UPDATE {table} SET data_json=? WHERE id=?",
                            (JsonUtils.dumps(dj), r["id"]))
            self.conn.commit()
            self.log_event("Column deleted with data migration", "WARNING",
                           {"category": category, "name": name})
            return True
        except Exception:
            self.conn.rollback()
            self.log_event(f"Delete column error: {traceback.format_exc()}", "CRITICAL")
            return False

    def _migrate_json_key(self, table: str, old_key: str, new_key: str) -> None:
        allowed = {"employees", "violations", "custom_ledger"}
        if table not in allowed:
            self.log_event(f"Invalid table name in _migrate_json_key: {table}", "CRITICAL")
            return
        rows = self.fetch_all(f"SELECT id, data_json FROM {table}")
        for r in rows:
            dj = JsonUtils.loads(r["data_json"])
            if old_key in dj:
                dj[new_key] = dj.pop(old_key)
                self.conn.execute(
                    f"UPDATE {table} SET data_json=? WHERE id=?",
                    (JsonUtils.dumps(dj), r["id"]))

    def get_companies(self) -> List[Dict[str, Any]]:
        return self.fetch_all("SELECT * FROM companies ORDER BY name")

    def get_company(self, company_id: int) -> Optional[Dict[str, Any]]:
        return self.fetch_one("SELECT * FROM companies WHERE id=?", (company_id,))

    def save_company(self, name: str, address: str = "",
                     contact: str = "", data_json: Optional[Dict[str, Any]] = None,
                     company_id: int = 0) -> int:
        try:
            dj = JsonUtils.dumps(data_json or {})
            if company_id > 0:
                self.conn.execute(
                    "UPDATE companies SET name=?, address=?, contact=?, data_json=? "
                    "WHERE id=?", (name, address, contact, dj, company_id))
                self.conn.commit()
                return company_id
            cur = self.conn.execute(
                "INSERT INTO companies (name, address, contact, data_json) "
                "VALUES (?, ?, ?, ?)", (name, address, contact, dj))
            self.conn.commit()
            return int(cur.lastrowid)
        except Exception:
            self.conn.rollback()
            self.log_event(f"Company save error: {traceback.format_exc()}", "CRITICAL")
            raise

    def delete_company(self, company_id: int) -> bool:
        try:
            self.create_backup()
            self.conn.execute("DELETE FROM companies WHERE id=?", (company_id,))
            self.conn.commit()
            self.log_event("Company deleted", "WARNING", {"id": company_id})
            return True
        except Exception:
            self.conn.rollback()
            self.log_event(f"Delete company error: {traceback.format_exc()}", "CRITICAL")
            return False

    def save_note(self, entity_type: str = "global", entity_id: int = 0,
                  title: str = "", content: str = "", note_id: int = 0) -> int:
        try:
            if note_id > 0:
                self.conn.execute(
                    "UPDATE notes SET title=?, content=?, updated_at=datetime('now') "
                    "WHERE id=?", (title, content, note_id))
                self.conn.commit()
                return note_id
            cur = self.conn.execute(
                "INSERT INTO notes (entity_type, entity_id, title, content) "
                "VALUES (?, ?, ?, ?)", (entity_type, entity_id, title, content))
            self.conn.commit()
            return int(cur.lastrowid)
        except Exception:
            self.conn.rollback()
            self.log_event(f"Note save error: {traceback.format_exc()}", "CRITICAL")
            raise

    def get_notes(self, entity_type: str = "global",
                  entity_id: int = 0) -> List[Dict[str, Any]]:
        if entity_type == "global":
            return self.fetch_all(
                "SELECT * FROM notes WHERE entity_type='global' ORDER BY updated_at DESC")
        return self.fetch_all(
            "SELECT * FROM notes WHERE entity_type=? AND entity_id=? "
            "ORDER BY updated_at DESC", (entity_type, entity_id))

    def delete_note(self, note_id: int) -> bool:
        try:
            self.conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            return False

    def save_reminder(self, title: str, description: str, due_date: str,
                      check_interval: int = 60, is_done: int = 0,
                      reminder_id: int = 0) -> int:
        try:
            if reminder_id > 0:
                self.conn.execute(
                    "UPDATE reminders SET title=?, description=?, due_date=?, "
                    "check_interval=?, is_done=? WHERE id=?",
                    (title, description, due_date, check_interval, is_done, reminder_id))
                self.conn.commit()
                return reminder_id
            cur = self.conn.execute(
                "INSERT INTO reminders (title, description, due_date, check_interval) "
                "VALUES (?, ?, ?, ?)", (title, description, due_date, check_interval))
            self.conn.commit()
            return int(cur.lastrowid)
        except Exception:
            self.conn.rollback()
            self.log_event(f"Reminder save error: {traceback.format_exc()}", "CRITICAL")
            raise

    def get_reminders(self, include_done: bool = False) -> List[Dict[str, Any]]:
        if include_done:
            return self.fetch_all("SELECT * FROM reminders ORDER BY due_date")
        return self.fetch_all(
            "SELECT * FROM reminders WHERE is_done=0 ORDER BY due_date")

    def get_due_reminders(self) -> List[Dict[str, Any]]:
        return self.fetch_all(
            "SELECT * FROM reminders WHERE is_done=0 AND due_date <= ?",
            (datetime.now().isoformat()[:10],))

    def delete_reminder(self, reminder_id: int) -> bool:
        try:
            self.conn.execute("DELETE FROM reminders WHERE id=?", (reminder_id,))
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            return False

    def get_templates(self) -> List[Dict[str, Any]]:
        rows = self.fetch_all("SELECT * FROM custom_templates ORDER BY name")
        for r in rows:
            r["data"] = JsonUtils.loads(r.get("data_json", "{}"))
        return rows

    def get_textbook(self) -> Dict[str, str]:
        rows = self.fetch_all("SELECT short_code, full_text FROM textbook")
        return {r["short_code"]: r["full_text"] for r in rows}

    def save_textbook_entry(self, short_code: str, full_text: str) -> bool:
        try:
            self.conn.execute(
                "INSERT INTO textbook (short_code, full_text) VALUES (?, ?) "
                "ON CONFLICT(short_code) DO UPDATE SET full_text=excluded.full_text",
                (short_code, full_text))
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            return False

    def delete_textbook_entry(self, short_code: str) -> bool:
        try:
            self.conn.execute("DELETE FROM textbook WHERE short_code=?", (short_code,))
            self.conn.commit()
            return True
        except Exception:
            self.conn.rollback()
            return False

    def get_print_templates(self, template_type: str = "order") -> List[Dict[str, Any]]:
        return self.fetch_all(
            "SELECT * FROM print_templates WHERE template_type=? ORDER BY is_default DESC",
            (template_type,))

    def get_all_print_templates(self) -> List[Dict[str, Any]]:
        return self.fetch_all(
            "SELECT * FROM print_templates ORDER BY is_default DESC, name")

    def save_print_template(self, name: str, template_type: str,
                            html_content: str, css_content: str = "",
                            template_id: int = 0) -> int:
        try:
            if template_id > 0:
                self.conn.execute(
                    "UPDATE print_templates SET name=?, html_content=?, css_content=? "
                    "WHERE id=?", (name, html_content, css_content, template_id))
                self.conn.commit()
                return template_id
            cur = self.conn.execute(
                "INSERT INTO print_templates (name, template_type, html_content, css_content) "
                "VALUES (?, ?, ?, ?)", (name, template_type, html_content, css_content))
            self.conn.commit()
            return int(cur.lastrowid)
        except Exception:
            self.conn.rollback()
            self.log_event(f"Print template error: {traceback.format_exc()}", "CRITICAL")
            raise

    def get_ai_setting(self, key: str, default: str = "") -> str:
        r = self.fetch_one("SELECT value FROM ai_settings WHERE key=?", (key,))
        return r["value"] if r else default

    def set_ai_setting(self, key: str, value: str) -> None:
        try:
            self.conn.execute(
                "INSERT INTO ai_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value))
            self.conn.commit()
        except Exception:
            self.conn.rollback()

    def export_to_csv(self, table: str, file_path: Optional[str] = None) -> str:
        if not file_path:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = os.path.join(RUNTIME_PATHS.export_dir, f"{table}_{ts}.csv")
        records = self.get_json_records(table)
        fieldnames = ["id"]
        for r in records:
            for k in r:
                if k not in fieldnames:
                    fieldnames.append(k)
        with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in records:
                wr = {}
                for k in fieldnames:
                    v = r.get(k, "")
                    if isinstance(v, (list, dict)):
                        v = json.dumps(v, ensure_ascii=False)
                    wr[k] = v
                w.writerow(wr)
        self.log_event("CSV export completed", "INFO", {"table": table, "path": file_path})
        return file_path

    @staticmethod
    def sha256_file(file_path: str) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def create_backup(self) -> str:
        os.makedirs(RUNTIME_PATHS.backup_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        tmp = os.path.join(tempfile.gettempdir(), f"suot_backup_{ts}.db")
        zip_path = os.path.join(RUNTIME_PATHS.backup_dir, f"suot_backup_{ts}.zip")
        try:
            os.remove(tmp)
        except OSError:
            pass
        src = sqlite3.connect(self.database_path)
        dst = sqlite3.connect(tmp)
        with src:
            src.backup(dst)
        dst.close()
        src.close()
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.write(tmp, arcname=AppConfig.DB_NAME)
        os.remove(tmp)
        csum = self.sha256_file(zip_path)
        size_b = os.path.getsize(zip_path)
        self.conn.execute(
            "INSERT INTO backups (created_at, file_path, size_bytes, sha256) "
            "VALUES (?, ?, ?, ?)",
            (datetime.now().isoformat(), zip_path, size_b, csum))
        self.conn.commit()
        self.log_event("Backup created", "INFO", {
            "path": zip_path, "size": size_b, "sha256": csum})
        return zip_path

    def get_backups(self) -> List[Dict[str, Any]]:
        return self.fetch_all("SELECT * FROM backups ORDER BY created_at DESC")

    def restore_backup(self, backup_id: int) -> bool:
        try:
            bk = self.fetch_one("SELECT * FROM backups WHERE id=?", (backup_id,))
            if not bk:
                self.log_event("Backup not found", "ERROR", {"id": backup_id})
                return False
            zip_path = bk["file_path"]
            if not os.path.isfile(zip_path):
                self.log_event("Backup file missing", "ERROR", {"path": zip_path})
                return False
            expected = bk["sha256"]
            actual = self.sha256_file(zip_path)
            if expected != actual:
                self.log_event("Backup checksum mismatch", "CRITICAL",
                               {"expected": expected, "actual": actual})
                return False
            tmp = os.path.join(tempfile.gettempdir(), "suot_restore_tmp.db")
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extract(AppConfig.DB_NAME, tempfile.gettempdir())
                extracted = os.path.join(tempfile.gettempdir(), AppConfig.DB_NAME)
                os.replace(extracted, tmp)
            self.conn.close()
            shutil.copy2(tmp, self.database_path)
            self.conn = sqlite3.connect(self.database_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self._configure_pragmas()
            os.remove(tmp)
            self.log_event("Database restored from backup", "WARNING",
                           {"backup_id": backup_id, "path": zip_path})
            return True
        except Exception:
            self.log_event(f"Restore error: {traceback.format_exc()}", "CRITICAL")
            return False

    def delete_backup(self, backup_id: int) -> bool:
        try:
            bk = self.fetch_one("SELECT * FROM backups WHERE id=?", (backup_id,))
            if bk:
                fp = bk["file_path"]
                if os.path.isfile(fp):
                    os.remove(fp)
                self.conn.execute("DELETE FROM backups WHERE id=?", (backup_id,))
                self.conn.commit()
                self.log_event("Backup deleted", "INFO", {"id": backup_id, "path": fp})
            return True
        except Exception:
            self.conn.rollback()
            self.log_event(f"Delete backup error: {traceback.format_exc()}", "CRITICAL")
            return False

    def _configure_pragmas(self) -> None:
        try:
            self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.execute("PRAGMA synchronous=NORMAL;")
            self.conn.execute("PRAGMA foreign_keys=ON;")
            self.conn.execute("PRAGMA busy_timeout=5000;")
            self.conn.execute("PRAGMA cache_size=-8000;")
        except Exception:
            pass

    def get_statistics(self) -> Dict[str, Any]:
        emp_count = self.fetch_one("SELECT COUNT(*) as c FROM employees")
        viol_count = self.fetch_one("SELECT COUNT(*) as c FROM violations")
        comp_count = self.fetch_one("SELECT COUNT(*) as c FROM companies")
        now = datetime.now()
        overdue = 0
        fines_total = 0.0
        for v in self.get_json_records("violations"):
            dj = v.get("data_json", {})
            status = dj.get("Статус", "")
            deadline_str = dj.get("Срок устранения", "")
            if status == "Просрочено":
                overdue += 1
            elif status == "Активно" and deadline_str:
                try:
                    parts = deadline_str.split(".")
                    if len(parts) == 3:
                        dl = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
                        if dl < now:
                            overdue += 1
                except Exception:
                    pass
            fine_str = str(dj.get("Штраф", "0")).replace(" ", "").replace(",", ".")
            try:
                fines_total += float(fine_str)
            except Exception:
                pass
        return {
            "employees_total": emp_count["c"] if emp_count else 0,
            "violations_total": viol_count["c"] if viol_count else 0,
            "companies_total": comp_count["c"] if comp_count else 0,
            "overdue_total": overdue,
            "fines_total": fines_total,
        }

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass
