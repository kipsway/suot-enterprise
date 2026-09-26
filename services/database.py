import os, csv, json, sqlite3, hashlib, shutil, zipfile, tempfile, traceback
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime, timedelta
from app_core.config import AppConfig, RUNTIME_PATHS
from app_core.db_interface import create_backend, SQLiteBackend
from app_core.utils import JsonUtils
from services.security import SecurityEngine
from services.session import SessionManager


# Значения статуса, считающиеся "завершёнными" для smart-фильтров
# active/done (единый список для системных и пользовательских таблиц).
DONE_STATUS_VALUES = [
    "устранено",
    "исполнено",
    "resolved",
    "соответствует",
    "выполнено",
    "готово",
    "закрыто",
    "done",
    "архив",
    "уволен",
    "отменено",
    "closed",
]

# Типы колонок с датами в формате ДД.ММ.ГГГГ (системные и custom).
DATE_COLUMN_TYPES = {"Годен до", "Дата проведения", "Дата"}

# Имена колонок статуса (системные и custom).
STATUS_COLUMN_NAMES = {"Статус", "Тяжесть"}


def smart_filter_clause(
    columns: List[Dict[str, Any]], smart_filter: str
) -> Tuple[str, List[Any]]:
    """SQL-кусок smart-фильтра (overdue/active/done) по описанию колонок.

    columns: [{"name":..., "type":...}]. Возвращает (where_sql, params);
    пустая строка — фильтр неприменим (нет подходящих колонок).
    """
    if smart_filter == "overdue":
        date_cols = [
            c["name"]
            for c in columns
            if c.get("type") in DATE_COLUMN_TYPES and c.get("name")
        ]
        if not date_cols:
            return "", []
        tests = [
            f"date(substr(json_extract(data_json, '$.\"{c}\"'), 7, 4) || '-' || substr(json_extract(data_json, '$.\"{c}\"'), 4, 2) || '-' || substr(json_extract(data_json, '$.\"{c}\"'), 1, 2)) < date('now', '-1 day')"
            for c in date_cols
        ]
        status = next(
            (
                c["name"]
                for c in columns
                if c.get("name") in STATUS_COLUMN_NAMES or c.get("type") == "Статус"
            ),
            "",
        )
        clause = "(" + " OR ".join(tests) + ")"
        params: List[Any] = []
        if status:
            # NOTE: overdue всегда исключает завершённые (как в системных таблицах).
            clause = (
                "("
                + clause
                + " AND pylower(coalesce(json_extract(data_json, '$.\"%s\"'),'')) NOT IN (%s))"
                % (
                    status,
                    ",".join("?" for _ in DONE_STATUS_VALUES),
                )
            )
            params.extend(DONE_STATUS_VALUES)
        return clause, params
    if smart_filter in {"active", "done"}:
        status = next(
            (
                c["name"]
                for c in columns
                if c.get("name") in STATUS_COLUMN_NAMES or c.get("type") == "Статус"
            ),
            "",
        )
        if not status:
            return "", []
        op = "NOT IN" if smart_filter == "active" else "IN"
        return (
            f"pylower(coalesce(json_extract(data_json, '$.\"{status}\"'),'')) {op} ({','.join('?' for _ in DONE_STATUS_VALUES)})",
            list(DONE_STATUS_VALUES),
        )
    return "", []


class DatabaseManager:
    _instance: Optional["DatabaseManager"] = None
    _lock: Any = None
    _cache: Dict[str, tuple] = {}
    JSON_TABLES = {
        "employees",
        "violations",
        "custom_ledger",
        "incidents",
        "ppe",
        "training",
        "permits",
        "work_orders",
        "ppe_inspections",
        "companies",
    }

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
        self._lock = __import__("threading").Lock()
        self._session_manager: Optional[SessionManager] = None
        self._backend = SQLiteBackend(str(self.database_path))
        cfg = self._load_db_config()
        if cfg.get("type") == "postgresql":
            self._backend = create_backend(cfg)
        self._init_schema()
        self._seed_defaults()
        self._fix_column_types()

    def _load_db_config(self) -> Dict[str, Any]:
        try:
            cfg = {}
            if self._backend.table_exists("settings"):
                for row in self._backend.fetch_all(
                    "SELECT key, value FROM settings WHERE key LIKE 'db_%'"
                ):
                    cfg[row["key"][3:]] = row["value"]
            if "port" in cfg:
                cfg["port"] = int(cfg["port"])
            return cfg
        except Exception:
            return {"type": "sqlite"}

    @property
    def session_manager(self) -> SessionManager:
        if self._session_manager is None:
            self._session_manager = SessionManager(self)
        return self._session_manager

    def _init_schema(self) -> None:
        try:
            self._backend.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'Inspector',
                    session_token TEXT,
                    token_expiry TEXT,
                    totp_secret TEXT DEFAULT '',
                    backup_codes TEXT DEFAULT '[]',
                    full_name TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS bulk_jobs (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    target TEXT NOT NULL,
                    ids_json TEXT NOT NULL DEFAULT '[]',
                    processed_ids_json TEXT NOT NULL DEFAULT '[]',
                    field TEXT NOT NULL DEFAULT '',
                    value TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'queued',
                    done INTEGER NOT NULL DEFAULT 0,
                    total INTEGER NOT NULL DEFAULT 0,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT NOT NULL DEFAULT '',
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL DEFAULT 0,
                    started_at REAL,
                    finished_at REAL
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
                CREATE TABLE IF NOT EXISTS work_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS ppe_inspections (
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
                CREATE TABLE IF NOT EXISTS calendar_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL DEFAULT 0,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS calendar_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL DEFAULT 0,
                    name TEXT NOT NULL DEFAULT '',
                    color TEXT NOT NULL DEFAULT '#4F8DFF',
                    is_default INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS npa_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parent_id INTEGER NOT NULL DEFAULT 0,
                    kind TEXT NOT NULL DEFAULT 'приказ',
                    number TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    date TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'действует',
                    category TEXT NOT NULL DEFAULT 'Общее',
                    audience TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS npa_favs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL DEFAULT 0,
                    npa_id INTEGER NOT NULL DEFAULT 0
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
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL DEFAULT 'default',
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    model TEXT DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS chat_threads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL DEFAULT 0,
                    title TEXT NOT NULL DEFAULT 'Новый диалог',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_chat_messages_thread ON chat_messages(thread_id);
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
                CREATE TABLE IF NOT EXISTS webhooks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    events TEXT NOT NULL DEFAULT '*',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_status TEXT NOT NULL DEFAULT '',
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS import_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                    table_name TEXT NOT NULL,
                    source_file TEXT,
                    imported INTEGER NOT NULL DEFAULT 0,
                    updated INTEGER NOT NULL DEFAULT 0,
                    errors INTEGER NOT NULL DEFAULT 0,
                    details TEXT,
                    user_id INTEGER DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_audit_severity ON audit_log(severity);
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
                CREATE INDEX IF NOT EXISTS idx_employees_json ON employees(data_json);
                CREATE INDEX IF NOT EXISTS idx_violations_json ON violations(data_json);
                CREATE INDEX IF NOT EXISTS idx_notes_entity ON notes(entity_type, entity_id);
                CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(due_date);
            """)
            self._backend.commit()
        except Exception:
            self._backend.rollback()
            raise

        for tbl in (
            "employees",
            "violations",
            "custom_ledger",
            "incidents",
            "ppe",
            "training",
            "permits",
            "import_history",
        ):
            try:
                self._backend.execute(
                    f"ALTER TABLE {tbl} ADD COLUMN user_id INTEGER DEFAULT 0"
                )
            except Exception:
                pass
        self._backend.execute("""CREATE TABLE IF NOT EXISTS change_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            record_id INTEGER NOT NULL,
            field TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            username TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        )""")
        self._backend.execute("""CREATE TABLE IF NOT EXISTS tab_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tab_index INTEGER NOT NULL DEFAULT 0,
            tab_text TEXT NOT NULL DEFAULT '',
            tab_type TEXT NOT NULL DEFAULT 'home',
            tab_data TEXT DEFAULT '',
            is_locked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )""")
        self._backend.execute("""CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL,
            ip TEXT DEFAULT '',
            user_agent TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_seen TEXT NOT NULL DEFAULT (datetime('now')),
            expires_at TEXT DEFAULT '',
            revoked INTEGER NOT NULL DEFAULT 0
        )""")
        self._backend.execute("""CREATE INDEX IF NOT EXISTS idx_sessions_user
            ON sessions(user_id)""")
        self._backend.execute("""CREATE TABLE IF NOT EXISTS home_layout (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tile_key TEXT NOT NULL,
            tile_label TEXT NOT NULL DEFAULT '',
            tile_color TEXT NOT NULL DEFAULT '#007AFF',
            tile_icon TEXT NOT NULL DEFAULT '📁',
            position INTEGER NOT NULL DEFAULT 0,
            visible INTEGER NOT NULL DEFAULT 1
        )""")
        self._backend.execute("""CREATE TABLE IF NOT EXISTS record_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_table TEXT NOT NULL,
            source_id INTEGER NOT NULL,
            target_table TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            link_type TEXT NOT NULL DEFAULT 'related',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(source_table, source_id, target_table, target_id)
        )""")
        self._backend.execute("""CREATE TABLE IF NOT EXISTS ot_protocols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL DEFAULT (date('now')),
            topic TEXT NOT NULL DEFAULT '',
            participants TEXT NOT NULL DEFAULT '',
            agenda TEXT NOT NULL DEFAULT '',
            decisions TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )""")
        self._backend.execute("""CREATE TABLE IF NOT EXISTS inspection_checklists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '',
            description TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )""")
        self._backend.execute("""CREATE TABLE IF NOT EXISTS checklist_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            checklist_id INTEGER NOT NULL,
            item_text TEXT NOT NULL DEFAULT '',
            position INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (checklist_id) REFERENCES inspection_checklists(id) ON DELETE CASCADE
        )""")
        self._backend.execute("""CREATE TABLE IF NOT EXISTS inspection_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            checklist_id INTEGER NOT NULL,
            conducted_date TEXT NOT NULL DEFAULT (date('now')),
            conducted_by TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pass',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (checklist_id) REFERENCES inspection_checklists(id)
        )""")
        self._backend.execute("""CREATE TABLE IF NOT EXISTS inspection_result_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            result_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            value TEXT NOT NULL DEFAULT 'na',
            comment TEXT DEFAULT '',
            FOREIGN KEY (result_id) REFERENCES inspection_results(id) ON DELETE CASCADE,
            FOREIGN KEY (item_id) REFERENCES checklist_items(id)
        )""")
        self._backend.execute("""CREATE TABLE IF NOT EXISTS capa_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            root_cause TEXT DEFAULT '',
            action_plan TEXT DEFAULT '',
            severity TEXT NOT NULL DEFAULT 'medium',
            status TEXT NOT NULL DEFAULT 'open',
            assigned_to TEXT DEFAULT '',
            deadline TEXT DEFAULT '',
            closed_date TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )""")
        self._backend.execute("""CREATE TABLE IF NOT EXISTS risk_assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '',
            description TEXT DEFAULT '',
            category TEXT DEFAULT '',
            probability INTEGER NOT NULL DEFAULT 1,
            consequence INTEGER NOT NULL DEFAULT 1,
            risk_level INTEGER NOT NULL DEFAULT 1,
            mitigation TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )""")
        self._backend.commit()
        # ── Отложенные миграции (после создания всех таблиц) ──
        try:
            ucols = {r["name"] for r in self.fetch_all("PRAGMA table_info(users)")}
            if "full_name" not in ucols:
                self._backend.execute(
                    "ALTER TABLE users ADD COLUMN full_name TEXT DEFAULT ''"
                )
            for tbl in (
                "work_orders",
                "ppe_inspections",
                "companies",
                "ot_protocols",
                "inspection_checklists",
                "inspection_results",
                "capa_records",
                "risk_assessments",
            ):
                tcols = {r["name"] for r in self.fetch_all(f"PRAGMA table_info({tbl})")}
                if tcols and "user_id" not in tcols:
                    self._backend.execute(
                        f"ALTER TABLE {tbl} ADD COLUMN user_id INTEGER DEFAULT 0"
                    )
            cc = {
                r["name"]
                for r in self.fetch_all("PRAGMA table_info(inspection_checklists)")
            }
            if cc and "is_template" not in cc:
                self._backend.execute(
                    "ALTER TABLE inspection_checklists "
                    "ADD COLUMN is_template INTEGER DEFAULT 0"
                )
            cp = {r["name"] for r in self.fetch_all("PRAGMA table_info(capa_records)")}
            if cp and "effectiveness" not in cp:
                self._backend.execute(
                    "ALTER TABLE capa_records ADD COLUMN effectiveness TEXT DEFAULT ''"
                )
            self._backend.execute("""CREATE TABLE IF NOT EXISTS custom_tables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                icon TEXT DEFAULT 'database',
                color TEXT DEFAULT '#6366F1',
                columns_json TEXT NOT NULL DEFAULT '[]',
                user_id INTEGER DEFAULT 0,
                deleted_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )""")
            self._backend.execute("""CREATE TABLE IF NOT EXISTS custom_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_key TEXT NOT NULL,
                data_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                user_id INTEGER DEFAULT 0
            )""")
            self._backend.execute(
                "CREATE INDEX IF NOT EXISTS idx_custom_records_key "
                "ON custom_records(table_key)"
            )
            self._backend.execute(
                "CREATE INDEX IF NOT EXISTS idx_custom_tables_user "
                "ON custom_tables(user_id)"
            )
            self._backend.execute("""CREATE TABLE IF NOT EXISTS user_views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 0,
                scope TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL DEFAULT '',
                query_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )""")
            self._backend.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_views_owner "
                "ON user_views(user_id, scope)"
            )
            self._backend.execute("""CREATE TABLE IF NOT EXISTS user_columns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_key TEXT NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'Текст',
                template TEXT DEFAULT '',
                position INTEGER NOT NULL DEFAULT 0,
                visible INTEGER NOT NULL DEFAULT 1,
                user_id INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(table_key, name, user_id)
            )""")
            self._backend.commit()
        except Exception:
            pass
        self._seed_home_layout_if_empty()

    def _seed_home_layout_if_empty(self) -> None:
        cur = self._backend.execute("SELECT COUNT(*) AS cnt FROM home_layout")
        row = cur.fetchone()
        if row and row["cnt"] > 0:
            return
        defaults = [
            ("employees", "Сотрудники", "#007AFF", "🧑‍💼"),
            ("violations", "Нарушения", "#FF3B30", "⚠️"),
            ("incidents", "Происшествия", "#FF9500", "🔥"),
            ("ppe", "СИЗ", "#34C759", "🛡️"),
            ("training", "Обучение", "#5856D6", "📚"),
            ("permits", "Наряды-допуски", "#FF2D55", "📋"),
            ("custom_ledger", "Журнал", "#AF52DE", "📓"),
            ("companies", "Компании", "#5AC8FA", "🏢"),
        ]
        for i, (key, label, color, icon) in enumerate(defaults):
            self._backend.execute(
                "INSERT INTO home_layout (tile_key, tile_label, tile_color, tile_icon, position, visible) "
                "VALUES (?, ?, ?, ?, ?, 1)",
                (key, label, color, icon, i),
            )

    def _insert_or_ignore(self, table: str, values: Dict[str, Any]) -> None:
        if table not in {
            "settings",
            "users",
            "ai_settings",
            "columns_config",
            "violation_types",
            "reminders",
            "notes",
            "audit_log",
            "employees",
            "violations",
            "custom_ledger",
            "companies",
            "incidents",
            "ppe",
            "training",
            "permits",
            "ot_protocols",
            "inspection_checklists",
            "checklist_items",
            "inspection_results",
            "inspection_result_items",
            "capa_records",
            "risk_assessments",
            "textbook",
            "custom_templates",
        }:
            raise ValueError(f"Invalid table: {table}")
        try:
            cols = ", ".join(values.keys())
            plc = ", ".join(["?" for _ in values])
            self._backend.execute(
                f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({plc})",
                tuple(values.values()),
            )
        except Exception:
            self._backend.rollback()

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
                    cur = self._backend.execute(
                        "SELECT type FROM columns_config WHERE category=? AND name=?",
                        (cat, col_name),
                    )
                    row = cur.fetchone()
                    if row and row["type"] != expected_type:
                        self._backend.execute(
                            "UPDATE columns_config SET type=? WHERE category=? AND name=?",
                            (expected_type, cat, col_name),
                        )
            self._backend.commit()
        except Exception:
            self._backend.rollback()

    def _seed_defaults(self) -> None:
        steps = [
            ("settings", self._seed_settings),
            ("column_configs", self._seed_column_configs),
            ("textbook", self._seed_textbook),
            ("templates", self._seed_templates),
            ("admin_user", self._seed_admin_user),
            ("print_templates", self._seed_print_templates),
            ("npa_documents", self._seed_npa),
        ]
        # Демо-записи (companies/employees/violations) — только для реальных БД.
        # Тестовая БД (SUOT_E2E_DB) должна быть детерминированной: демо грузится
        # явно через POST /api/demo/seed или кнопкой «Загрузить демо» в UI.
        if not os.environ.get("SUOT_E2E_DB"):
            steps += [
                ("companies", self._seed_companies),
                ("employees", self._seed_employees),
                ("violations", self._seed_violations),
            ]
        for name, fn in steps:
            try:
                fn()
                self._backend.commit()
            except Exception:
                self._backend.rollback()
                self.log_event(
                    f"Seed step '{name}' failed",
                    "ERROR",
                    {"error": traceback.format_exc()},
                )

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
                ("ID", "Число", 0),
                ("ФИО", "Текст", 1),
                ("Должность", "Текст", 2),
                ("Подразделение", "Текст", 3),
                ("Фирма", "Текст", 4),
                ("Телефон", "Текст", 5),
                ("Дата медосмотра", "Годен до", 6),
                ("Квалификация", "Текст", 7),
                ("Дата проведения", "Дата проведения", 8),
                ("Фото", "Медиа", 9),
                ("Статус", "Статус", 10),
            ],
            "violations": [
                ("ID", "Число", 0),
                ("Дата", "Годен до", 1),
                ("Фирма", "Текст", 2),
                ("Подразделение", "Текст", 3),
                ("Категория риска", "Текст", 4),
                ("Описание", "Текст", 5),
                ("Ответственный", "Текст", 6),
                ("Срок устранения", "Годен до", 7),
                ("Штраф", "Число", 8),
                ("Статус", "Статус", 9),
                ("Фото", "Медиа", 10),
            ],
            "custom_ledger": [
                ("ID", "Число", 0),
                ("Дата", "Годен до", 1),
                ("Категория", "Текст", 2),
                ("Описание", "Текст", 3),
                ("Ответственный", "Текст", 4),
                ("Статус", "Статус", 5),
                ("Фото", "Медиа", 6),
                ("Примечание", "Текст", 7),
            ],
            "incidents": [
                ("ID", "Число", 0),
                ("Дата происшествия", "Годен до", 1),
                ("Время", "Текст", 2),
                ("Тип", "Текст", 3),
                ("Тяжесть", "Статус", 4),
                ("Место", "Текст", 5),
                ("Описание", "Текст", 6),
                ("Пострадавшие", "Текст", 7),
                ("Причина", "Текст", 8),
                ("Корректирующие меры", "Текст", 9),
                ("Срок устранения", "Годен до", 10),
                ("Статус", "Статус", 11),
                ("Фото", "Медиа", 12),
            ],
            "ppe": [
                ("ID", "Число", 0),
                ("Сотрудник", "Текст", 1),
                ("Наименование СИЗ", "Текст", 2),
                ("Тип", "Текст", 3),
                ("ГОСТ/ТР", "Текст", 4),
                ("Ед.изм.", "Текст", 5),
                ("Количество", "Число", 6),
                ("Норма на год", "Число", 7),
                ("Дата выдачи", "Годен до", 8),
                ("Срок замены", "Годен до", 9),
                ("Статус", "Статус", 10),
                ("Примечание", "Текст", 11),
            ],
            "training": [
                ("ID", "Число", 0),
                ("Сотрудник", "Текст", 1),
                ("Наименование", "Текст", 2),
                ("Тип обучения", "Текст", 3),
                ("Обучающая организация", "Текст", 4),
                ("Дата проведения", "Годен до", 5),
                ("Срок действия", "Годен до", 6),
                ("Номер удостоверения", "Текст", 7),
                ("Статус", "Статус", 8),
                ("Примечание", "Текст", 9),
            ],
            "permits": [
                ("ID", "Число", 0),
                ("Номер наряда", "Текст", 1),
                ("Тип работ", "Текст", 2),
                ("Описание работ", "Текст", 3),
                ("Место проведения", "Текст", 4),
                ("Ответственный", "Текст", 5),
                ("Состав бригады", "Текст", 6),
                ("Дата начала", "Годен до", 7),
                ("Дата окончания", "Годен до", 8),
                ("Меры безопасности", "Текст", 9),
                ("Статус", "Статус", 10),
                ("Примечание", "Текст", 11),
            ],
            "companies": [
                ("ID", "Число", 0),
                ("Наименование", "Текст", 1),
                ("Адрес", "Текст", 2),
                ("Телефон", "Текст", 3),
                ("ИНН", "Текст", 4),
                ("Ответственный", "Текст", 5),
            ],
            "ppe_inspections": [
                ("ID", "Число", 0),
                ("Дата осмотра", "Дата проведения", 1),
                ("Сотрудник", "Текст", 2),
                ("Наименование СИЗ", "Текст", 3),
                ("Вид осмотра", "Текст", 4),
                ("Результат", "Статус", 5),
                ("Выявленные дефекты", "Текст", 6),
                ("Дата следующего осмотра", "Годен до", 7),
                ("Ответственный", "Текст", 8),
                ("Фото", "Медиа", 9),
            ],
            "work_orders": [
                ("ID", "Число", 0),
                ("Номер наряда", "Текст", 1),
                ("Задание", "Текст", 2),
                ("Фирма", "Текст", 3),
                ("Подразделение", "Текст", 4),
                ("Ответственный", "Текст", 5),
                ("Исполнители", "Текст", 6),
                ("Дата начала", "Дата проведения", 7),
                ("Срок выполнения", "Годен до", 8),
                ("Статус", "Статус", 9),
                ("Примечание", "Текст", 10),
            ],
        }
        for cat, cols in configs.items():
            for name, typ, pos in cols:
                self._insert_or_ignore(
                    "columns_config",
                    {
                        "category": cat,
                        "name": name,
                        "type": typ,
                        "position": pos,
                    },
                )

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
            {
                "name": "Нарушение применения СИЗ",
                "data": {
                    "category": "Средства индивидуальной защиты",
                    "risk_level": "Средний",
                    "regulation": "Требования охраны труда по применению СИЗ",
                    "recommended_action": "Выдать средства защиты, провести повторный инструктаж, зафиксировать нарушение в журнале.",
                },
            },
            {
                "name": "Отсутствие ограждения",
                "data": {
                    "category": "Опасные зоны",
                    "risk_level": "Высокий",
                    "regulation": "Требования к ограждению опасных производственных зон",
                    "recommended_action": "Установить временное или постоянное ограждение опасной зоны, разместить предупреждающие знаки.",
                },
            },
            {
                "name": "Непроведение инструктажа",
                "data": {
                    "category": "Обучение и инструктаж",
                    "risk_level": "Высокий",
                    "regulation": "Требования к проведению инструктажей по охране труда",
                    "recommended_action": "Немедленно провести целевой инструктаж, внести запись в журнал, назначить ответственное лицо.",
                },
            },
            {
                "name": "Нарушение электробезопасности",
                "data": {
                    "category": "Электробезопасность",
                    "risk_level": "Высокий",
                    "regulation": "Правила устройства электроустановок (ПУЭ)",
                    "recommended_action": "Отстранить работника, провести внеочередную проверку знаний, устранить нарушение.",
                },
            },
            {
                "name": "Пожарная безопасность",
                "data": {
                    "category": "Пожарная безопасность",
                    "risk_level": "Критический",
                    "regulation": "Правила противопожарного режима в РФ",
                    "recommended_action": "Устранить нарушение, провести внеплановый противопожарный инструктаж.",
                },
            },
        ]
        for t in templates:
            self._insert_or_ignore(
                "custom_templates",
                {
                    "name": t["name"],
                    "data_json": JsonUtils.dumps(t["data"]),
                },
            )

    def _seed_admin_user(self) -> None:
        if self.fetch_one("SELECT id FROM users"):
            return
        # Часть 21: в production первый админ создаётся мастером запуска.
        # Сид admin/admin — только для автотестов (SUOT_E2E_DB).
        import os

        if not os.environ.get("SUOT_E2E_DB"):
            self.log_event("Seed admin skipped: setup wizard will create it", "INFO")
            return
        pw_hash, salt = SecurityEngine.generate_hash("admin")
        self._backend.execute(
            "INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)",
            ("admin", pw_hash, salt, "Administrator"),
        )
        self.log_event("Default admin user created (admin/admin)", "WARNING")

    def _seed_companies(self) -> None:
        if self.fetch_one("SELECT id FROM companies"):
            return
        companies = [
            ("ООО ТехСтрой", "г. Москва, ул. Строителей, 15", "+7 (495) 123-45-67"),
            (
                "АО ПромБезопасность",
                "г. Санкт-Петербург, пр. Промышленный, 42",
                "+7 (812) 765-43-21",
            ),
            ("ИП Иванов", "г. Новосибирск, ул. Рабочая, 8", "+7 (383) 987-65-43"),
        ]
        for name, addr, contact in companies:
            self._backend.execute(
                "INSERT INTO companies (name, address, contact) VALUES (?, ?, ?)",
                (name, addr, contact),
            )
        self.log_event("Demo companies seeded", "INFO")

    def _seed_employees(self) -> None:
        if self.fetch_one("SELECT id FROM employees"):
            return
        now = datetime.now()
        employees = [
            (
                "Иванов Иван Иванович",
                "Инженер по охране труда",
                "ОТиПБ",
                "ООО ТехСтрой",
                "+7 (495) 111-11-11",
                (now - timedelta(days=30)).strftime("%d.%m.%Y"),
                "5-й уровень",
                (now - timedelta(days=180)).strftime("%d.%m.%Y"),
                "Активен",
            ),
            (
                "Петров Пётр Петрович",
                "Начальник цеха",
                "Цех №1",
                "ООО ТехСтрой",
                "+7 (495) 111-11-12",
                (now - timedelta(days=45)).strftime("%d.%m.%Y"),
                "4-й уровень",
                (now - timedelta(days=90)).strftime("%d.%m.%Y"),
                "Активен",
            ),
            (
                "Сидоров Сидор Сидорович",
                "Электромонтёр",
                "Электроцех",
                "ООО ТехСтрой",
                "+7 (495) 111-11-13",
                (now - timedelta(days=320)).strftime("%d.%m.%Y"),
                "3-й уровень",
                (now - timedelta(days=60)).strftime("%d.%m.%Y"),
                "Активен",
            ),
            (
                "Кузнецов Алексей Сергеевич",
                "Сварщик",
                "Цех №2",
                "ООО ТехСтрой",
                "+7 (495) 111-11-14",
                (now - timedelta(days=15)).strftime("%d.%m.%Y"),
                "4-й уровень",
                (now - timedelta(days=30)).strftime("%d.%m.%Y"),
                "Активен",
            ),
            (
                "Смирнова Ольга Владимировна",
                "Бухгалтер",
                "Бухгалтерия",
                "ООО ТехСтрой",
                "+7 (495) 111-11-15",
                (now - timedelta(days=180)).strftime("%d.%m.%Y"),
                "5-й уровень",
                "",
                "Активен",
            ),
            (
                "Васильев Дмитрий Андреевич",
                "Инспектор по охране труда",
                "ОТиПБ",
                "АО ПромБезопасность",
                "+7 (812) 222-22-21",
                (now - timedelta(days=10)).strftime("%d.%m.%Y"),
                "5-й уровень",
                (now - timedelta(days=45)).strftime("%d.%m.%Y"),
                "Активен",
            ),
            (
                "Николаев Артём Павлович",
                "Начальник смены",
                "Смена №1",
                "АО ПромБезопасность",
                "+7 (812) 222-22-22",
                (now - timedelta(days=365)).strftime("%d.%m.%Y"),
                "4-й уровень",
                (now - timedelta(days=365)).strftime("%d.%m.%Y"),
                "Архив",
            ),
            (
                "Козлова Елена Михайловна",
                "Химик-лаборант",
                "Лаборатория",
                "АО ПромБезопасность",
                "+7 (812) 222-22-23",
                (now - timedelta(days=200)).strftime("%d.%m.%Y"),
                "4-й уровень",
                (now - timedelta(days=120)).strftime("%d.%m.%Y"),
                "Активен",
            ),
            (
                "Морозов Сергей Викторович",
                "Грузчик",
                "Склад",
                "АО ПромБезопасность",
                "+7 (812) 222-22-24",
                (now - timedelta(days=5)).strftime("%d.%m.%Y"),
                "2-й уровень",
                (now - timedelta(days=15)).strftime("%d.%m.%Y"),
                "Активен",
            ),
            (
                "Фёдорова Анна Павловна",
                "Секретарь",
                "Администрация",
                "АО ПромБезопасность",
                "+7 (812) 222-22-25",
                (now - timedelta(days=90)).strftime("%d.%m.%Y"),
                "3-й уровень",
                "",
                "Активен",
            ),
            (
                "Григорьев Илья Алексеевич",
                "Разнорабочий",
                "Производство",
                "ИП Иванов",
                "+7 (383) 333-33-31",
                (now - timedelta(days=60)).strftime("%d.%m.%Y"),
                "2-й уровень",
                (now - timedelta(days=10)).strftime("%d.%m.%Y"),
                "Активен",
            ),
            (
                "Тимофеев Максим Денисович",
                "Водитель",
                "Транспорт",
                "ИП Иванов",
                "+7 (383) 333-33-32",
                (now - timedelta(days=365 + 30)).strftime("%d.%m.%Y"),
                "3-й уровень",
                (now - timedelta(days=200)).strftime("%d.%m.%Y"),
                "Активен",
            ),
            (
                "Архипов Виктор Николаевич",
                "Кладовщик",
                "Склад",
                "ИП Иванов",
                "+7 (383) 333-33-33",
                (now - timedelta(days=25)).strftime("%d.%m.%Y"),
                "3-й уровень",
                (now - timedelta(days=90)).strftime("%d.%m.%Y"),
                "Активен",
            ),
            (
                "Белова Татьяна Олеговна",
                "Уборщица",
                "Хоз. часть",
                "ИП Иванов",
                "+7 (383) 333-33-34",
                (now - timedelta(days=150)).strftime("%d.%m.%Y"),
                "1-й уровень",
                "",
                "Активен",
            ),
            (
                "Дмитриев Константин Борисович",
                "Менеджер",
                "Офис",
                "ИП Иванов",
                "+7 (383) 333-33-35",
                (now - timedelta(days=45)).strftime("%d.%m.%Y"),
                "4-й уровень",
                (now - timedelta(days=30)).strftime("%d.%m.%Y"),
                "Активен",
            ),
        ]
        for emp in employees:
            data = {
                "ФИО": emp[0],
                "Должность": emp[1],
                "Подразделение": emp[2],
                "Фирма": emp[3],
                "Телефон": emp[4],
                "Дата медосмотра": emp[5],
                "Квалификация": emp[6],
                "Дата проведения": emp[7],
                "Статус": emp[8],
                "Фото": [],
            }
            self._backend.execute(
                "INSERT INTO employees (data_json) VALUES (?)", (JsonUtils.dumps(data),)
            )
        self.log_event("Demo employees seeded (15 records)", "INFO")

    def _seed_violations(self) -> None:
        if self.fetch_one("SELECT id FROM violations"):
            return
        now = datetime.now()
        violations = [
            (
                "10.01.2024",
                "ООО ТехСтрой",
                "Цех №1",
                "Средства индивидуальной защиты",
                "Работник находился на рабочем месте без защитной каски",
                "Петров Пётр Петрович",
                (now - timedelta(days=10)).strftime("%d.%m.%Y"),
                "5000",
                "Активно",
            ),
            (
                "15.02.2024",
                "ООО ТехСтрой",
                "Цех №2",
                "Электробезопасность",
                "Неисправность заземления электрооборудования",
                "Кузнецов Алексей Сергеевич",
                (now + timedelta(days=20)).strftime("%d.%m.%Y"),
                "15000",
                "Активно",
            ),
            (
                "20.03.2024",
                "АО ПромБезопасность",
                "Лаборатория",
                "Пожарная безопасность",
                "Загромождение путей эвакуации",
                "Козлова Елена Михайловна",
                (now - timedelta(days=5)).strftime("%d.%m.%Y"),
                "10000",
                "Активно",
            ),
            (
                "05.04.2024",
                "АО ПромБезопасность",
                "Склад",
                "Опасные зоны",
                "Отсутствует ограждение опасной зоны погрузки",
                "Морозов Сергей Викторович",
                (now - timedelta(days=60)).strftime("%d.%m.%Y"),
                "20000",
                "Просрочено",
            ),
            (
                "12.05.2024",
                "ИП Иванов",
                "Производство",
                "Обучение и инструктаж",
                "Не проведён инструктаж новому работнику",
                "Григорьев Илья Алексеевич",
                (now + timedelta(days=5)).strftime("%d.%m.%Y"),
                "8000",
                "Активно",
            ),
            (
                "01.06.2024",
                "ИП Иванов",
                "Транспорт",
                "Средства индивидуальной защиты",
                "Отсутствие сигнального жилета у водителя",
                "Тимофеев Максим Денисович",
                (now - timedelta(days=90)).strftime("%d.%m.%Y"),
                "3000",
                "Исполнено",
            ),
            (
                "15.06.2024",
                "ООО ТехСтрой",
                "ОТиПБ",
                "Документация",
                "Отсутствует журнал регистрации инструктажей",
                "Иванов Иван Иванович",
                (now + timedelta(days=45)).strftime("%d.%m.%Y"),
                "5000",
                "Активно",
            ),
            (
                "20.07.2024",
                "АО ПромБезопасность",
                "Администрация",
                "Пожарная безопасность",
                "Не проведена проверка огнетушителей",
                "Фёдорова Анна Павловна",
                (now - timedelta(days=365)).strftime("%d.%m.%Y"),
                "7000",
                "Исполнено",
            ),
        ]
        for v in violations:
            data = {
                "Дата": v[0],
                "Фирма": v[1],
                "Подразделение": v[2],
                "Категория риска": v[3],
                "Описание": v[4],
                "Ответственный": v[5],
                "Срок устранения": v[6],
                "Штраф": v[7],
                "Статус": v[8],
                "Фото": [],
            }
            self._backend.execute(
                "INSERT INTO violations (data_json) VALUES (?)",
                (JsonUtils.dumps(data),),
            )
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
        self._backend.execute(
            """INSERT INTO print_templates (name, template_type, html_content, is_default)
            VALUES (?, ?, ?, 1)""",
            ("Стандартное предписание", "order", default_order_html),
        )
        self._backend.execute(
            """INSERT INTO print_templates (name, template_type, html_content, is_default)
            VALUES (?, ?, ?, 1)""",
            ("Стандартный отчёт", "report", default_report_html),
        )
        self.log_event("Default print templates seeded", "INFO")

    def execute(self, sql: str, params: Tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock:
            try:
                return self._backend.execute(sql, params)
            except Exception:
                self._backend.rollback()
                self.log_event(f"SQL error: {traceback.format_exc()}", "CRITICAL")
                raise

    def commit(self) -> None:
        with self._lock:
            try:
                self._backend.commit()
            except Exception:
                self._backend.rollback()
                self.log_event(f"Commit error: {traceback.format_exc()}", "CRITICAL")
                raise

    def rollback(self) -> None:
        with self._lock:
            try:
                self._backend.rollback()
            except Exception:
                self.log_event(f"Rollback error: {traceback.format_exc()}", "CRITICAL")

    def fetch_all(self, sql: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        with self._lock:
            try:
                return [dict(r) for r in self._backend.execute(sql, params).fetchall()]
            except Exception:
                self._backend.rollback()
                self.log_event(f"Fetch error: {traceback.format_exc()}", "CRITICAL")
                return []

    def fetch_one(
        self, sql: str, params: Tuple[Any, ...] = ()
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            try:
                r = self._backend.execute(sql, params).fetchone()
                return dict(r) if r else None
            except Exception:
                self._backend.rollback()
                self.log_event(f"Fetch one error: {traceback.format_exc()}", "CRITICAL")
                return None

    def upsert_setting(self, key: str, value: Any) -> None:
        try:
            self._backend.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )
            self._backend.commit()
        except Exception:
            self._backend.rollback()
            self.log_event(
                f"Setting upsert error: {traceback.format_exc()}", "CRITICAL"
            )

    def get_setting(self, key: str, default: Any = None) -> Any:
        r = self.fetch_one("SELECT value FROM settings WHERE key=?", (key,))
        return r["value"] if r else default

    def get_all_settings(self) -> Dict[str, str]:
        rows = self.fetch_all("SELECT key, value FROM settings")
        return {r["key"]: r["value"] for r in rows}

    def get_settings_like(self, pattern: str) -> List[str]:
        rows = self.fetch_all("SELECT key FROM settings WHERE key LIKE ?", (pattern,))
        return [r["key"] for r in rows]

    def log_event(
        self,
        event: str,
        severity: str = "INFO",
        details: Optional[Dict[str, Any]] = None,
        username: str = "",
    ) -> None:
        try:
            self._backend.execute(
                "INSERT INTO audit_log (timestamp, event, severity, details, username) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    datetime.now().isoformat(),
                    event,
                    severity,
                    JsonUtils.dumps(details or {}),
                    username,
                ),
            )
            self._backend.commit()
        except Exception:
            self._backend.rollback()

    def get_audit_events(
        self, limit: int = 500, severity: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        if severity:
            return self.fetch_all(
                "SELECT * FROM audit_log WHERE severity=? ORDER BY id DESC LIMIT ?",
                (severity, limit),
            )
        return self.fetch_all(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        )

    def get_audit_events_for_record(
        self, table: str, record_id: int, limit: int = 100
    ) -> List[Dict[str, Any]]:
        rows = self.fetch_all(
            "SELECT * FROM audit_log WHERE event LIKE ? AND details LIKE ? "
            "ORDER BY id DESC LIMIT ?",
            (f"%{table}%", f"%{record_id}%", limit),
        )
        result = []
        for row in rows:
            try:
                details = JsonUtils.loads(row.get("details", "{}"))
            except Exception:
                details = {}
            if details.get("id") == record_id or details.get("table") == table:
                result.append(row)
        return result

    def log_change(
        self,
        table: str,
        record_id: int,
        field: str,
        old_value: str,
        new_value: str,
        username: str = "",
    ) -> None:
        if old_value == new_value:
            return
        try:
            self._backend.execute(
                "INSERT INTO change_history (table_name, record_id, field, "
                "old_value, new_value, username) VALUES (?, ?, ?, ?, ?, ?)",
                (table, record_id, field, str(old_value), str(new_value), username),
            )
            self._backend.commit()
        except Exception:
            self._backend.rollback()

    def get_change_history(
        self, table: str, record_id: int, limit: int = 100
    ) -> List[Dict[str, Any]]:
        rows = self.fetch_all(
            "SELECT * FROM change_history WHERE table_name=? AND record_id=? "
            "ORDER BY id DESC LIMIT ?",
            (table, record_id, limit),
        )
        return [dict(r) for r in rows]

    def rollback_change(self, history_id: int) -> bool:
        try:
            row = self.fetch_one(
                "SELECT * FROM change_history WHERE id=?", (history_id,)
            )
            if not row:
                return False
            data = self.fetch_one(
                f"SELECT data_json FROM {row['table_name']} WHERE id=?",
                (row["record_id"],),
            )
            if not data:
                return False
            try:
                dj = json.loads(data["data_json"]) if data["data_json"] else {}
            except (json.JSONDecodeError, TypeError):
                dj = {}
            old = row["old_value"]
            try:
                parsed = json.loads(old) if old is not None else ""
            except (json.JSONDecodeError, TypeError):
                parsed = old or ""
            dj[row["field"]] = parsed
            self._backend.execute(
                f"UPDATE {row['table_name']} SET data_json=?, "
                f"updated_at=datetime('now') WHERE id=?",
                (JsonUtils.dumps(dj), row["record_id"]),
            )
            self._backend.commit()
            self.log_change(
                row["table_name"],
                row["record_id"],
                row["field"],
                row["new_value"],
                row["old_value"],
                "rollback",
            )
            return True
        except Exception:
            self._backend.rollback()
            return False

    def _validate_json_table(self, name: str) -> str:
        if name not in self.JSON_TABLES:
            raise ValueError(f"Unsupported JSON table: {name}")
        return name

    def query_json_records(
        self,
        table: str,
        owner_id: Optional[int],
        is_admin: bool = False,
        q: str = "",
        filters: Optional[Dict[str, List[str]]] = None,
        sort_by: str = "",
        order: str = "asc",
        page: int = 1,
        page_size: int = 50,
        order_cast: str = "",
        smart_filter: str = "",
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Серверные список+счётчик: поиск, фильтры по колонкам, сортировка, пагинация.

        owner_id=None и is_admin=True → видеть все записи.
        order_cast="num" → сортировать колонку как число (для текстовых с цифрами)."""
        self._validate_json_table(table)
        where: List[str] = []
        params: List[Any] = []

        if not is_admin:
            where.append("(user_id=? OR user_id=0)")
            params.append(int(owner_id or 0))

        if q:
            where.append("pylower(data_json) LIKE pylower(?)")
            params.append(f"%{q}%")

        valid_cols = {c["name"]: c for c in self.get_columns_config(table)}
        for col_name, values in (filters or {}).items():
            if col_name not in valid_cols or not values:
                continue
            expr = f"json_extract(data_json, '$.\"{col_name}\"')"
            placeholders = ",".join("?" for _ in values)
            where.append(f"{expr} IN ({placeholders})")
            params.extend(values)

        if smart_filter == "overdue":
            date_cols = [
                c["name"]
                for c in valid_cols.values()
                if c.get("type") in {"Годен до", "Дата проведения", "Дата"}
            ]
            if date_cols:
                tests = [
                    f"date(substr(json_extract(data_json, '$.\"{c}\"'), 7, 4) || '-' || substr(json_extract(data_json, '$.\"{c}\"'), 4, 2) || '-' || substr(json_extract(data_json, '$.\"{c}\"'), 1, 2)) < date('now', '-1 day')"
                    for c in date_cols
                ]
                status = next(
                    (
                        c["name"]
                        for c in valid_cols.values()
                        if c.get("name") in {"Статус", "Тяжесть"}
                    ),
                    "",
                )
                clause = "(" + " OR ".join(tests) + ")"
                if status:
                    clause = (
                        "("
                        + clause
                        + " AND pylower(coalesce(json_extract(data_json, '$.\"%s\"'),'')) NOT IN (%s))"
                        % (
                            status,
                            ",".join("?" for _ in DONE_STATUS_VALUES),
                        )
                    )
                    params.extend(DONE_STATUS_VALUES)
                where.append(clause)
        elif smart_filter in {"active", "done"}:
            vals = DONE_STATUS_VALUES
            status = next(
                (
                    c["name"]
                    for c in valid_cols.values()
                    if c.get("name") in {"Статус", "Тяжесть"}
                ),
                "",
            )
            if status:
                op = "NOT IN" if smart_filter == "active" else "IN"
                where.append(
                    f"pylower(coalesce(json_extract(data_json, '$.\"{status}\"'),'')) {op} ({','.join('?' for _ in vals)})"
                )
                params.extend(vals)

        where_sql = (" WHERE " + " AND ".join(where)) if where else ""
        total = (
            self.fetch_one(
                f"SELECT COUNT(*) AS n FROM {table}{where_sql}", tuple(params)
            )
            or {"n": 0}
        )["n"]

        sort_expr = "id"
        if sort_by and sort_by != "id":
            if sort_by in valid_cols:
                raw = f"json_extract(data_json, '$.\"{sort_by}\"')"
                if order_cast == "num" or valid_cols[sort_by].get("type") == "Число":
                    sort_expr = f"CAST({raw} AS REAL)"
                else:
                    sort_expr = f"pylower({raw})"
        direction = "DESC" if str(order).lower() == "desc" else "ASC"

        page = max(1, int(page))
        page_size = min(500, max(1, int(page_size)))
        offset = (page - 1) * page_size

        # companies (легаси-схема) не имеет created_at/updated_at
        avail = {r["name"] for r in self.fetch_all(f"PRAGMA table_info({table})")}
        sel_cols = ["id", "data_json"]
        for extra in ("created_at", "updated_at", "user_id"):
            if extra in avail:
                sel_cols.append(extra)

        sql = (
            f"SELECT {', '.join(sel_cols)} "
            f"FROM {table}{where_sql} "
            f"ORDER BY {sort_expr} {direction}, id DESC "
            f"LIMIT ? OFFSET ?"
        )
        rows = self.fetch_all(sql, tuple(params) + (page_size, offset))

        result: List[Dict[str, Any]] = []
        for r in rows:
            dj = JsonUtils.loads(r["data_json"])
            rec: Dict[str, Any] = {"id": r["id"], "data_json": dj}
            rec.update(dj)
            result.append(rec)
        return result, int(total)

    def distinct_column_values(
        self,
        table: str,
        column: str,
        owner_id: Optional[int],
        is_admin: bool = False,
        limit: int = 300,
    ) -> List[str]:
        """Уникальные непустые значения колонки (для фильтров UI)."""
        self._validate_json_table(table)
        if column == "id":
            return []
        if column not in {c["name"] for c in self.get_columns_config(table)}:
            raise ValueError(f"Unknown column: {column}")
        where: List[str] = [
            f"json_extract(data_json, '$.\"{column}\"') IS NOT NULL",
            "data_json != '{}'",
        ]
        params: List[Any] = []
        if not is_admin:
            where.append("(user_id=? OR user_id=0)")
            params.append(int(owner_id or 0))
        rows = self.fetch_all(
            f"SELECT DISTINCT json_extract(data_json, '$.\"{column}\"') AS v "
            f"FROM {table} WHERE {' AND '.join(where)} LIMIT ?",
            tuple(params) + (limit,),
        )
        out = sorted(
            {
                str(r["v"]).strip()
                for r in rows
                if r["v"] is not None and str(r["v"]).strip()
            }
        )
        return out[:limit]

    def count_records_for(self, owner_id: int) -> Dict[str, int]:
        """Количества записей пользователя по таблицам (для демо-баннера)."""
        counts: Dict[str, int] = {}
        for tbl in sorted(self.JSON_TABLES):
            try:
                r = self.fetch_one(
                    f"SELECT COUNT(*) AS n FROM {tbl} WHERE user_id=?", (owner_id,)
                )
                counts[tbl] = int(r["n"]) if r else 0
            except Exception:
                counts[tbl] = 0
        return counts

    # ═══ Пользовательские таблицы (Часть 7) ═══

    # ── Сохранённые виды таблиц (SUOT Next, Query Engine) ──

    def list_views(
        self, scope: str, owner_id: Optional[int], is_admin: bool = False
    ) -> List[Dict[str, Any]]:
        """Виды таблицы: свои (+ общие user_id=0); админ видит все."""
        if is_admin:
            rows = self.fetch_all(
                "SELECT * FROM user_views WHERE scope=? ORDER BY id",
                (scope,),
            )
        else:
            rows = self.fetch_all(
                "SELECT * FROM user_views WHERE scope=? AND (user_id=? OR user_id=0) ORDER BY id",
                (scope, int(owner_id or 0)),
            )
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["query"] = JsonUtils.loads(d.get("query_json") or "{}")
            except Exception:
                d["query"] = {}
            out.append(d)
        return out

    def create_view(
        self, scope: str, name: str, query: Dict[str, Any], user_id: int
    ) -> Dict[str, Any]:
        cur = self._backend.execute(
            "INSERT INTO user_views (user_id, scope, name, query_json) VALUES (?, ?, ?, ?)",
            (int(user_id), scope, name, JsonUtils.dumps(query)),
        )
        self._backend.commit()
        return {"id": int(cur.lastrowid)}

    def update_view(
        self,
        vid: int,
        user_id: int,
        is_admin: bool,
        name: Optional[str] = None,
        query: Optional[Dict[str, Any]] = None,
    ) -> bool:
        row = self.fetch_one("SELECT * FROM user_views WHERE id=?", (vid,))
        if not row:
            return False
        if int(row["user_id"]) != int(user_id or 0) and not is_admin:
            raise PermissionError("чужой вид")
        sets: List[str] = []
        params: List[Any] = []
        if name is not None:
            sets.append("name=?")
            params.append(name)
        if query is not None:
            sets.append("query_json=?")
            params.append(JsonUtils.dumps(query))
        if not sets:
            return True
        sets.append("updated_at=datetime('now')")
        params.append(vid)
        self._backend.execute(
            f"UPDATE user_views SET {', '.join(sets)} WHERE id=?", tuple(params)
        )
        self._backend.commit()
        return True

    def delete_view(self, vid: int, user_id: int, is_admin: bool) -> bool:
        row = self.fetch_one("SELECT * FROM user_views WHERE id=?", (vid,))
        if not row:
            return False
        if int(row["user_id"]) != int(user_id or 0) and not is_admin:
            raise PermissionError("чужой вид")
        self._backend.execute("DELETE FROM user_views WHERE id=?", (vid,))
        self._backend.commit()
        return True

    def get_custom_tables(
        self,
        owner_id: Optional[int],
        is_admin: bool = False,
        include_deleted: bool = False,
    ) -> List[Dict[str, Any]]:
        where, params = (
            ("1=1", [])
            if is_admin
            else ("(user_id=? OR user_id=0)", [int(owner_id or 0)])
        )
        if not include_deleted:
            where += " AND deleted_at=''"
        rows = self.fetch_all(
            f"SELECT * FROM custom_tables WHERE {where} ORDER BY id", tuple(params)
        )
        return [dict(r) for r in rows]

    def get_custom_table(self, key: str) -> Optional[Dict[str, Any]]:
        r = self.fetch_one("SELECT * FROM custom_tables WHERE key=?", (key,))
        return dict(r) if r else None

    def create_custom_table(
        self,
        label: str,
        icon: str,
        color: str,
        columns: List[Dict[str, Any]],
        user_id: int,
    ) -> Dict[str, Any]:
        import uuid

        key = f"u_{uuid.uuid4().hex[:10]}"
        cur = self._backend.execute(
            "INSERT INTO custom_tables (key, label, icon, color, "
            "columns_json, user_id) VALUES (?, ?, ?, ?, ?, ?)",
            (key, label, icon, color, JsonUtils.dumps(columns), int(user_id)),
        )
        self._backend.commit()
        return {"id": int(cur.lastrowid), "key": key}

    def update_custom_table(
        self, tid: int, label: str, icon: str, color: str, columns: List[Dict[str, Any]]
    ) -> None:
        self._backend.execute(
            "UPDATE custom_tables SET label=?, icon=?, color=?, "
            "columns_json=? WHERE id=?",
            (label, icon, color, JsonUtils.dumps(columns), tid),
        )
        self._backend.commit()

    def soft_delete_custom_table(self, tid: int) -> None:
        self._backend.execute(
            "UPDATE custom_tables SET deleted_at=datetime('now') WHERE id=?", (tid,)
        )
        self._backend.commit()

    def restore_custom_table(self, tid: int) -> None:
        self._backend.execute(
            "UPDATE custom_tables SET deleted_at='' WHERE id=?", (tid,)
        )
        self._backend.commit()

    def purge_custom_table(self, tid: int) -> None:
        t = self.fetch_one("SELECT key FROM custom_tables WHERE id=?", (tid,))
        if not t:
            return
        self._backend.execute(
            "DELETE FROM custom_records WHERE table_key=?", (t["key"],)
        )
        self._backend.execute("DELETE FROM custom_tables WHERE id=?", (tid,))
        self._backend.commit()

    def purge_old_custom_tables(self, days: int = 30) -> int:
        rows = self.fetch_all(
            "SELECT id FROM custom_tables WHERE deleted_at != '' AND "
            "deleted_at < datetime('now', ?)",
            (f"-{int(days)} day",),
        )
        for r in rows:
            self.purge_custom_table(int(r["id"]))
        return len(rows)

    def custom_columns(self, key: str) -> List[Dict[str, Any]]:
        t = self.get_custom_table(key)
        if not t:
            return []
        try:
            cols = JsonUtils.loads(t["columns_json"] or "[]")
            return cols if isinstance(cols, list) else []
        except Exception:
            return []

    def query_custom_records(
        self,
        key: str,
        owner_id: Optional[int],
        is_admin: bool = False,
        q: str = "",
        filters: Optional[Dict[str, List[str]]] = None,
        sort_by: str = "",
        order: str = "asc",
        page: int = 1,
        page_size: int = 50,
        order_cast: str = "",
        smart_filter: str = "",
    ) -> Tuple[List[Dict[str, Any]], int]:
        where: List[str] = ["table_key=?"]
        params: List[Any] = [key]
        if not is_admin:
            where.append("(user_id=? OR user_id=0)")
            params.append(int(owner_id or 0))
        if q:
            where.append("pylower(data_json) LIKE pylower(?)")
            params.append(f"%{q}%")
        valid_cols = {
            c["name"]: c for c in self.custom_columns(key) if c.get("visible", True)
        }
        for col_name, values in (filters or {}).items():
            if col_name not in valid_cols or not values:
                continue
            expr = f"json_extract(data_json, '$.\"{col_name}\"')"
            ph = ",".join("?" for _ in values)
            where.append(f"{expr} IN ({ph})")
            params.extend(values)
        if smart_filter in {"overdue", "active", "done"}:
            clause, sparams = smart_filter_clause(
                [
                    {"name": n, "type": (c or {}).get("type", "")}
                    for n, c in valid_cols.items()
                ],
                smart_filter,
            )
            if clause:
                where.append(clause)
                params.extend(sparams)
        where_sql = " WHERE " + " AND ".join(where)
        total = (
            self.fetch_one(
                f"SELECT COUNT(*) AS n FROM custom_records{where_sql}", tuple(params)
            )
            or {"n": 0}
        )["n"]
        sort_expr = "id"
        if sort_by and sort_by != "id" and sort_by in valid_cols:
            raw = f"json_extract(data_json, '$.\"{sort_by}\"')"
            if order_cast == "num" or valid_cols[sort_by].get("type") == "Число":
                sort_expr = f"CAST({raw} AS REAL)"
            else:
                sort_expr = f"pylower({raw})"
        direction = "DESC" if str(order).lower() == "desc" else "ASC"
        page = max(1, int(page))
        page_size = min(500, max(1, int(page_size)))
        offset = (page - 1) * page_size
        rows = self.fetch_all(
            f"SELECT id, data_json, created_at, updated_at, user_id "
            f"FROM custom_records{where_sql} "
            f"ORDER BY {sort_expr} {direction}, id DESC LIMIT ? OFFSET ?",
            tuple(params) + (page_size, offset),
        )
        result: List[Dict[str, Any]] = []
        for r in rows:
            dj = JsonUtils.loads(r["data_json"])
            rec: Dict[str, Any] = {"id": r["id"], "data_json": dj}
            rec.update(dj)
            result.append(rec)
        return result, int(total)

    def get_custom_record(self, key: str, rid: int) -> Optional[Dict[str, Any]]:
        r = self.fetch_one(
            "SELECT id, data_json, created_at, updated_at, user_id "
            "FROM custom_records WHERE id=? AND table_key=?",
            (rid, key),
        )
        if not r:
            return None
        dj = JsonUtils.loads(r["data_json"])
        rec: Dict[str, Any] = {"id": r["id"], "data_json": dj}
        rec.update(dj)
        return rec

    def save_custom_record(
        self, key: str, rid: int, data: Dict[str, Any], user_id: int
    ) -> int:
        payload = JsonUtils.dumps(data)
        if rid > 0:
            self._backend.execute(
                "UPDATE custom_records SET data_json=?, "
                "updated_at=datetime('now') WHERE id=? AND table_key=?",
                (payload, rid, key),
            )
            self._backend.commit()
            return rid
        cur = self._backend.execute(
            "INSERT INTO custom_records (table_key, data_json, user_id) "
            "VALUES (?, ?, ?)",
            (key, payload, int(user_id)),
        )
        self._backend.commit()
        return int(cur.lastrowid)

    def delete_custom_record(self, key: str, rid: int) -> bool:
        self._backend.execute(
            "DELETE FROM custom_records WHERE id=? AND table_key=?", (rid, key)
        )
        self._backend.commit()
        return True

    def count_custom_for(self, owner_id: int) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for t in self.get_custom_tables(owner_id, is_admin=False):
            r = self.fetch_one(
                "SELECT COUNT(*) AS n FROM custom_records WHERE table_key=?",
                (t["key"],),
            )
            counts[t["key"]] = int(r["n"]) if r else 0
        return counts

    def migrate_user_isolation(self) -> Dict[str, Any]:
        """Web-миграция: колонка user_id во всех JSON-таблицах,
        legacy-записи (user_id=0) закрепляются за первым администратором."""
        report: Dict[str, Any] = {
            "tables_patched": [],
            "records_assigned": 0,
            "indexes_created": 0,
        }
        structured = (
            "ot_protocols",
            "inspection_checklists",
            "inspection_results",
            "capa_records",
            "risk_assessments",
        )
        all_tables = tuple(sorted(self.JSON_TABLES)) + structured
        try:
            try:
                ucols = {r["name"] for r in self.fetch_all("PRAGMA table_info(users)")}
                if "full_name" not in ucols:
                    self._backend.execute(
                        "ALTER TABLE users ADD COLUMN full_name TEXT DEFAULT ''"
                    )
                    self._backend.commit()
                    report["tables_patched"].append("users.full_name")
            except Exception:
                pass

            for tbl in all_tables:
                try:
                    cols = [
                        r["name"] for r in self.fetch_all(f"PRAGMA table_info({tbl})")
                    ]
                    if not cols:
                        self._backend.execute(f"DROP TABLE IF EXISTS {tbl}")
                        self._backend.execute(
                            f"CREATE TABLE {tbl} ("
                            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                            "data_json TEXT NOT NULL DEFAULT '{}', "
                            "created_at TEXT NOT NULL DEFAULT (datetime('now')), "
                            "updated_at TEXT NOT NULL DEFAULT (datetime('now')), "
                            "user_id INTEGER DEFAULT 0)"
                        )
                        report["tables_patched"].append(f"{tbl} (recreated)")
                        continue
                    if "user_id" not in cols:
                        self._backend.execute(
                            f"ALTER TABLE {tbl} ADD COLUMN user_id INTEGER DEFAULT 0"
                        )
                        report["tables_patched"].append(tbl)
                except Exception:
                    report.setdefault("tables_failed", []).append(tbl)
                    continue
            self._backend.commit()

            admin = self.fetch_one(
                "SELECT id FROM users "
                "ORDER BY CASE WHEN role='Administrator' THEN 0 ELSE 1 END, id "
                "LIMIT 1"
            )
            if admin:
                admin_id = int(admin["id"])
                total = 0
                for tbl in all_tables:
                    try:
                        cur = self._backend.execute(
                            f"UPDATE {tbl} SET user_id=? "
                            f"WHERE user_id=0 OR user_id IS NULL",
                            (admin_id,),
                        )
                        total += max(0, cur.rowcount)
                    except Exception:
                        report.setdefault("tables_failed", []).append(tbl)
                report["records_assigned"] = total
                report["owner_admin_id"] = admin_id

            for tbl in all_tables:
                try:
                    self._backend.execute(
                        f"CREATE INDEX IF NOT EXISTS idx_{tbl}_user ON {tbl}(user_id)"
                    )
                    report["indexes_created"] += 1
                except Exception:
                    pass
            self._backend.commit()
            if report["tables_patched"] or report["records_assigned"]:
                self.log_event("User isolation migration applied", "INFO", report)
            return report
        except Exception:
            self._backend.rollback()
            self.log_event(
                f"Isolation migration error: {traceback.format_exc()}", "CRITICAL"
            )
            return report

    def migrate_legacy_qt(self) -> Dict[str, Any]:
        """Часть 30: миграция старой Qt-базы suot_platform.db.

        Старая Qt-версия (suot_platform.py) создаёт users без колонок
        full_name/totp/backup_codes/is_active/sec_*, и не имеет таблицы
        sessions. Идемпотентно: добавляет недостающие колонки, базу record_links
        и индексы без потери данных.
        """
        report: Dict[str, Any] = {"patched": [], "note": ""}
        try:
            cols = {r["name"] for r in self.fetch_all("PRAGMA table_info(users)")}
            for col, decl in (
                ("full_name", "TEXT DEFAULT ''"),
                ("totp_secret", "TEXT DEFAULT ''"),
                ("backup_codes", "TEXT DEFAULT '[]'"),
                ("is_active", "INTEGER NOT NULL DEFAULT 1"),
                ("sec_question", "TEXT DEFAULT ''"),
                ("sec_answer_hash", "TEXT DEFAULT ''"),
                ("sec_salt", "TEXT DEFAULT ''"),
            ):
                if col not in cols:
                    try:
                        self._backend.execute(
                            f"ALTER TABLE users ADD COLUMN {col} {decl}"
                        )
                        report["patched"].append(f"users.{col}")
                    except Exception:
                        pass
            self._backend.commit()
            # таблица сессий появилась в _init_schema, но для старой БД гарантируем
            self._backend.execute(
                "CREATE TABLE IF NOT EXISTS sessions ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "user_id INTEGER NOT NULL,"
                "token_hash TEXT NOT NULL,"
                "ip TEXT DEFAULT '',"
                "user_agent TEXT DEFAULT '',"
                "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
                "last_seen TEXT NOT NULL DEFAULT (datetime('now')),"
                "expires_at TEXT DEFAULT '',"
                "revoked INTEGER NOT NULL DEFAULT 0)"
            )
            self._backend.commit()
            if report["patched"]:
                report["note"] = "legacy Qt schema upgraded"
                self.log_event("Legacy Qt migration applied", "INFO", report)
            return report
        except Exception:
            self._backend.rollback()
            self.log_event(
                f"Legacy Qt migration error: {traceback.format_exc()}", "CRITICAL"
            )
            return report

    def find_violation_duplicate(
        self, data: Dict[str, Any], exclude_id: int = 0, user_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
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

    def find_duplicate(
        self,
        table: str,
        data: Dict[str, Any],
        exclude_id: int = 0,
        user_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        self._validate_json_table(table)
        cols = self.get_columns_config(table)
        text_cols = {c["name"] for c in cols if c["type"] == "Текст"}
        name_col = None
        for n in (
            "ФИО",
            "Наименование",
            "Наименование СИЗ",
            "Номер наряда",
            "Описание",
            "Сотрудник",
        ):
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

    def get_import_history(
        self,
        limit: int = 100,
        user_id: Optional[int] = None,
        is_admin: bool = False,
    ) -> List[Dict[str, Any]]:
        # IDOR-фикс (аудит 7.2 п.6): не-админ видит только свои импорты.
        if is_admin:
            rows = self.fetch_all(
                "SELECT * FROM import_history ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
        else:
            rows = self.fetch_all(
                "SELECT * FROM import_history WHERE user_id=? "
                "ORDER BY timestamp DESC LIMIT ?",
                (int(user_id or 0), limit),
            )
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
                self.save_json_record(
                    "employees", existing["id"], merged_data, user_id=user_id
                )
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
                self.save_json_record(
                    "violations", existing["id"], merged_data, user_id=user_id
                )
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
                self.save_json_record(
                    "custom_ledger", existing["id"], merged_data, user_id=user_id
                )
                self.delete_json_record("custom_ledger", rec["id"])
                merged += 1
            else:
                seen[key] = rec
        return merged

    def save_json_record(
        self, table: str, record_id: int, data: Dict[str, Any], user_id: int = 0
    ) -> int:
        self._validate_json_table(table)
        self.invalidate_cache(table)
        try:
            payload = JsonUtils.dumps(data)

            # companies: легаси-колонки name/address/contact (NOT NULL/UNIQUE)
            comp_legacy: Optional[Tuple[str, str, str]] = None
            if table == "companies":
                nm = str(data.get("Наименование", "")).strip()
                if not nm:
                    raise ValueError("COMPANY_NAME_REQUIRED")
                comp_legacy = (
                    nm,
                    str(data.get("Адрес", "")),
                    str(data.get("Телефон", "")),
                )

            if record_id > 0:
                exists = self.fetch_one(
                    f"SELECT data_json FROM {table} WHERE id=?", (record_id,)
                )
                if exists:
                    try:
                        old_data = (
                            json.loads(exists["data_json"])
                            if exists["data_json"]
                            else {}
                        )
                        for key in data:
                            old_val = str(old_data.get(key, ""))
                            new_val = str(data[key])
                            if old_val != new_val:
                                self.log_change(table, record_id, key, old_val, new_val)
                    except (json.JSONDecodeError, TypeError):
                        pass
                    if comp_legacy:
                        # у companies нет updated_at (легаси-схема)
                        self._backend.execute(
                            f"UPDATE {table} SET data_json=?, name=?, "
                            f"address=?, contact=? WHERE id=?",
                            (payload, *comp_legacy, record_id),
                        )
                    else:
                        self._backend.execute(
                            f"UPDATE {table} SET data_json=?, updated_at=datetime('now') "
                            f"WHERE id=?",
                            (payload, record_id),
                        )
                    self._backend.commit()
                    self.log_event(
                        f"Record updated in {table}", "INFO", {"id": record_id}
                    )
                    return record_id
            if table == "companies":
                cur = self._backend.execute(
                    "INSERT INTO companies (name, address, contact, "
                    "data_json, user_id) VALUES (?, ?, ?, ?, ?)",
                    (*comp_legacy, payload, user_id),
                )
            else:
                cur = self._backend.execute(
                    f"INSERT INTO {table} (data_json, user_id) VALUES (?, ?)",
                    (payload, user_id),
                )
            self._backend.commit()
            new_id = int(cur.lastrowid)
            self.log_event(f"Record inserted in {table}", "INFO", {"id": new_id})
            return new_id
        except sqlite3.IntegrityError as e:
            self._backend.rollback()
            if "companies.name" in str(e):
                raise ValueError("DUPLICATE_COMPANY") from e
            raise
        except ValueError:
            self._backend.rollback()
            raise
        except Exception:
            self._backend.rollback()
            self.log_event(f"Save record error: {traceback.format_exc()}", "CRITICAL")
            raise

    def get_json_records(
        self, table: str, limit: int = 2000, user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
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
                (user_id, limit),
            )
        else:
            rows = self.fetch_all(
                f"SELECT id, data_json, created_at, updated_at, user_id "
                f"FROM {table} ORDER BY id DESC LIMIT ?",
                (limit,),
            )
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
        avail = {r["name"] for r in self.fetch_all(f"PRAGMA table_info({table})")}
        sel_cols = ["id", "data_json"]
        for extra in ("created_at", "updated_at", "user_id"):
            if extra in avail:
                sel_cols.append(extra)
        r = self.fetch_one(
            f"SELECT {', '.join(sel_cols)} FROM {table} WHERE id=?", (record_id,)
        )
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
            try:
                self.create_backup()
            except Exception:
                self.log_event(
                    f"Pre-delete backup failed (delete continues): "
                    f"{traceback.format_exc()}",
                    "ERROR",
                )
            self._backend.execute(f"DELETE FROM {table} WHERE id=?", (record_id,))
            self._backend.commit()
            self.log_event(
                "Record deleted", "WARNING", {"table": table, "id": record_id}
            )
            return True
        except Exception:
            self._backend.rollback()
            self.log_event(f"Delete error: {traceback.format_exc()}", "CRITICAL")
            return False

    def record_owner_id(self, table: str, record_id: int) -> Optional[int]:
        """IDOR-фикс (аудит 7.2): user_id записи или None, если записи нет.

        Работает для JSON-таблиц и custom_records (u_*).
        """
        if table in self.JSON_TABLES:
            try:
                cols = {
                    r["name"] for r in self.fetch_all(f"PRAGMA table_info({table})")
                }
                if "user_id" not in cols:
                    # легаси-таблица без владельца (напр. companies) — общая
                    exists = self.fetch_one(
                        f"SELECT id FROM {table} WHERE id=?", (int(record_id),)
                    )
                    return 0 if exists else None
                row = self.fetch_one(
                    f"SELECT user_id FROM {table} WHERE id=?", (int(record_id),)
                )
            except Exception:
                return None
        else:
            row = self.fetch_one(
                "SELECT user_id FROM custom_records WHERE id=? AND table_key=?",
                (int(record_id), table),
            )
        if not row:
            return None
        return int(row["user_id"] or 0)

    def user_can_access(
        self, table: str, record_id: int, user_id: int, is_admin: bool = False
    ) -> bool:
        """Доступ к записи: владелец / общая (user_id=0) / админ."""
        owner = self.record_owner_id(table, record_id)
        if owner is None:
            return False
        return owner == 0 or owner == int(user_id) or is_admin

    def get_columns_config(
        self, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        from time import time

        cache_key = f"columns:{category or 'all'}"
        if cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if time() - ts < 2.0:
                return data
        if category:
            result = self.fetch_all(
                "SELECT * FROM columns_config WHERE category=? ORDER BY position",
                (category,),
            )
        else:
            result = self.fetch_all(
                "SELECT * FROM columns_config ORDER BY category, position"
            )
        self._cache[cache_key] = (time(), result)
        return result

    def set_columns_config(
        self, category: str, configs: List[Tuple[str, str, int]]
    ) -> None:
        self.invalidate_cache(f"columns:{category}")
        try:
            self.create_backup()
            self._backend.execute(
                "DELETE FROM columns_config WHERE category=?", (category,)
            )
            for name, typ, pos in configs:
                self._backend.execute(
                    "INSERT INTO columns_config (category, name, type, position) "
                    "VALUES (?, ?, ?, ?)",
                    (category, name, typ, pos),
                )
            self._backend.commit()
            self.log_event(f"Columns config updated for {category}", "INFO")
        except Exception:
            self._backend.rollback()
            self.log_event(
                f"Columns config error: {traceback.format_exc()}", "CRITICAL"
            )
            raise

    def rename_column(self, category: str, old_name: str, new_name: str) -> bool:
        if not new_name or old_name == new_name:
            return False
        dup = self.fetch_one(
            "SELECT id FROM columns_config WHERE category=? AND name=?",
            (category, new_name),
        )
        if dup:
            return False
        table_map = {
            "employees": "employees",
            "violations": "violations",
            "custom_ledger": "custom_ledger",
        }
        table = table_map.get(category)
        if not table:
            return False
        try:
            self.create_backup()
            self.invalidate_cache(f"columns:{category}")
            self._backend.execute(
                "UPDATE columns_config SET name=? WHERE category=? AND name=?",
                (new_name, category, old_name),
            )
            self._migrate_json_key(table, old_name, new_name)
            self._backend.commit()
            self.log_event(
                "Column renamed",
                "INFO",
                {"category": category, "old": old_name, "new": new_name},
            )
            return True
        except Exception:
            self._backend.rollback()
            self.log_event(f"Rename column error: {traceback.format_exc()}", "CRITICAL")
            return False

    def add_column(self, category: str, name: str, typ: str) -> bool:
        if not name:
            return False
        dup = self.fetch_one(
            "SELECT id FROM columns_config WHERE category=? AND name=?",
            (category, name),
        )
        if dup:
            return False
        max_pos = self.fetch_one(
            "SELECT MAX(position) as mp FROM columns_config WHERE category=?",
            (category,),
        )
        pos = (
            (max_pos["mp"] + 1)
            if (max_pos is not None and max_pos["mp"] is not None)
            else 0
        )
        try:
            self.invalidate_cache(f"columns:{category}")
            self._backend.execute(
                "INSERT INTO columns_config (category, name, type, position) "
                "VALUES (?, ?, ?, ?)",
                (category, name, typ, pos),
            )
            self._backend.commit()
            self.log_event("Column added", "INFO", {"category": category, "name": name})
            return True
        except Exception:
            self._backend.rollback()
            self.log_event(f"Add column error: {traceback.format_exc()}", "CRITICAL")
            return False

    def delete_column(self, category: str, name: str) -> bool:
        try:
            self.create_backup()
            self.invalidate_cache(f"columns:{category}")
            self._backend.execute(
                "DELETE FROM columns_config WHERE category=? AND name=?",
                (category, name),
            )
            table_map = {
                "employees": "employees",
                "violations": "violations",
                "custom_ledger": "custom_ledger",
            }
            table = table_map.get(category)
            if table:
                rows = self.fetch_all(f"SELECT id, data_json FROM {table}")
                for r in rows:
                    dj = JsonUtils.loads(r["data_json"])
                    if name in dj:
                        del dj[name]
                        self._backend.execute(
                            f"UPDATE {table} SET data_json=? WHERE id=?",
                            (JsonUtils.dumps(dj), r["id"]),
                        )
            self._backend.commit()
            self.log_event(
                "Column deleted with data migration",
                "WARNING",
                {"category": category, "name": name},
            )
            return True
        except Exception:
            self._backend.rollback()
            self.log_event(f"Delete column error: {traceback.format_exc()}", "CRITICAL")
            return False

    def _migrate_json_key(self, table: str, old_key: str, new_key: str) -> None:
        allowed = {"employees", "violations", "custom_ledger"}
        if table not in allowed:
            self.log_event(
                f"Invalid table name in _migrate_json_key: {table}", "CRITICAL"
            )
            return
        rows = self.fetch_all(f"SELECT id, data_json FROM {table}")
        for r in rows:
            dj = JsonUtils.loads(r["data_json"])
            if old_key in dj:
                dj[new_key] = dj.pop(old_key)
                self._backend.execute(
                    f"UPDATE {table} SET data_json=? WHERE id=?",
                    (JsonUtils.dumps(dj), r["id"]),
                )

    def get_companies(self) -> List[Dict[str, Any]]:
        return self.fetch_all("SELECT * FROM companies ORDER BY name")

    def get_company(self, company_id: int) -> Optional[Dict[str, Any]]:
        return self.fetch_one("SELECT * FROM companies WHERE id=?", (company_id,))

    def save_company(
        self,
        name: str,
        address: str = "",
        contact: str = "",
        data_json: Optional[Dict[str, Any]] = None,
        company_id: int = 0,
    ) -> int:
        try:
            dj = JsonUtils.dumps(data_json or {})
            if company_id > 0:
                self._backend.execute(
                    "UPDATE companies SET name=?, address=?, contact=?, data_json=? "
                    "WHERE id=?",
                    (name, address, contact, dj, company_id),
                )
                self._backend.commit()
                return company_id
            cur = self._backend.execute(
                "INSERT INTO companies (name, address, contact, data_json) "
                "VALUES (?, ?, ?, ?)",
                (name, address, contact, dj),
            )
            self._backend.commit()
            return int(cur.lastrowid)
        except Exception:
            self._backend.rollback()
            self.log_event(f"Company save error: {traceback.format_exc()}", "CRITICAL")
            raise

    def delete_company(self, company_id: int) -> bool:
        try:
            self.create_backup()
            self._backend.execute("DELETE FROM companies WHERE id=?", (company_id,))
            self._backend.commit()
            self.log_event("Company deleted", "WARNING", {"id": company_id})
            return True
        except Exception:
            self._backend.rollback()
            self.log_event(
                f"Delete company error: {traceback.format_exc()}", "CRITICAL"
            )
            return False

    def save_note(
        self,
        entity_type: str = "global",
        entity_id: int = 0,
        title: str = "",
        content: str = "",
        note_id: int = 0,
    ) -> int:
        try:
            if note_id > 0:
                self._backend.execute(
                    "UPDATE notes SET title=?, content=?, updated_at=datetime('now') "
                    "WHERE id=?",
                    (title, content, note_id),
                )
                self._backend.commit()
                return note_id
            cur = self._backend.execute(
                "INSERT INTO notes (entity_type, entity_id, title, content) "
                "VALUES (?, ?, ?, ?)",
                (entity_type, entity_id, title, content),
            )
            self._backend.commit()
            return int(cur.lastrowid)
        except Exception:
            self._backend.rollback()
            self.log_event(f"Note save error: {traceback.format_exc()}", "CRITICAL")
            raise

    def get_notes(
        self, entity_type: str = "global", entity_id: int = 0
    ) -> List[Dict[str, Any]]:
        if entity_type == "global":
            return self.fetch_all(
                "SELECT * FROM notes WHERE entity_type='global' ORDER BY updated_at DESC"
            )
        return self.fetch_all(
            "SELECT * FROM notes WHERE entity_type=? AND entity_id=? "
            "ORDER BY updated_at DESC",
            (entity_type, entity_id),
        )

    def delete_note(self, note_id: int) -> bool:
        try:
            self._backend.execute("DELETE FROM notes WHERE id=?", (note_id,))
            self._backend.commit()
            return True
        except Exception:
            self._backend.rollback()
            return False

    # ─── Календарь (Часть 25) ───────────────────────────────────────────
    def calendar_list_events(
        self,
        user_id: int,
        is_admin: bool,
        start: str = "",
        end: str = "",
    ) -> List[Dict[str, Any]]:
        """События календаря. Диапазон [start,end] фильтруется в Python,
        т.к. дата хранится внутри data_json."""
        if is_admin:
            rows = self.fetch_all("SELECT * FROM calendar_events ORDER BY id")
        else:
            rows = self.fetch_all(
                "SELECT * FROM calendar_events WHERE user_id=? OR user_id=0 "
                "ORDER BY id",
                (user_id,),
            )
        out = []
        for r in rows:
            dj = JsonUtils.loads(r["data_json"] or "{}")
            rec = {
                "id": r["id"],
                "user_id": r["user_id"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            rec.update(dj)
            ev_date = str(dj.get("date", ""))
            if start and ev_date and ev_date < start:
                continue
            if end and ev_date and ev_date > end:
                continue
            out.append(rec)
        return out

    def calendar_save_event(
        self, user_id: int, record_id: int, data: Dict[str, Any]
    ) -> int:
        """Вставка/обновление события календаря. Возвращает id."""
        try:
            payload = JsonUtils.dumps(data)
            if record_id > 0:
                cur = self._backend.execute(
                    "UPDATE calendar_events SET data_json=?, "
                    "updated_at=datetime('now') WHERE id=?",
                    (payload, record_id),
                )
                self._backend.commit()
                return record_id
            cur = self._backend.execute(
                "INSERT INTO calendar_events (user_id, data_json) VALUES (?, ?)",
                (user_id, payload),
            )
            self._backend.commit()
            return int(cur.lastrowid)
        except Exception:
            self._backend.rollback()
            self.log_event(f"Calendar save error: {traceback.format_exc()}", "CRITICAL")
            raise

    def calendar_delete_event(self, event_id: int) -> bool:
        try:
            self._backend.execute("DELETE FROM calendar_events WHERE id=?", (event_id,))
            self._backend.commit()
            self.log_event("Calendar event deleted", "WARNING", {"id": event_id})
            return True
        except Exception:
            self._backend.rollback()
            return False

    def calendar_list_categories(
        self, user_id: int, is_admin: bool
    ) -> List[Dict[str, Any]]:
        if is_admin:
            rows = self.fetch_all("SELECT * FROM calendar_categories ORDER BY id")
        else:
            rows = self.fetch_all(
                "SELECT * FROM calendar_categories WHERE user_id=? OR user_id=0 "
                "ORDER BY id",
                (user_id,),
            )
        return [dict(r) for r in rows]

    def calendar_save_category(
        self,
        user_id: int,
        cat_id: int,
        name: str,
        color: str,
        is_default: bool = False,
    ) -> int:
        try:
            if cat_id > 0:
                # IDOR-фикс (аудит 7.2 п.9): обновлять можно только свои
                # категории (или общие user_id=0), чужие — нельзя.
                cur = self._backend.execute(
                    "UPDATE calendar_categories SET name=?, color=?, "
                    "is_default=? WHERE id=? AND (user_id=? OR user_id=0)",
                    (name, color, 1 if is_default else 0, cat_id, user_id),
                )
                self._backend.commit()
                if cur.rowcount == 0:
                    raise ValueError("Категория не найдена или нет доступа")
                return cat_id
            cur = self._backend.execute(
                "INSERT INTO calendar_categories (user_id, name, color, "
                "is_default) VALUES (?, ?, ?, ?)",
                (user_id, name, color, 1 if is_default else 0),
            )
            self._backend.commit()
            return int(cur.lastrowid)
        except Exception:
            self._backend.rollback()
            raise

    def calendar_delete_category(self, cat_id: int, user_id: int) -> bool:
        try:
            self._backend.execute(
                "DELETE FROM calendar_categories WHERE id=? AND "
                "(user_id=? OR user_id=0)",
                (cat_id, user_id),
            )
            self._backend.commit()
            return True
        except Exception:
            self._backend.rollback()
            return False

    def calendar_seed_categories(self, user_id: int) -> int:
        """Заполнить категории по умолчанию, если их пока нет."""
        existing = self.calendar_list_categories(user_id, False)
        if existing:
            return 0
        defaults = [
            ("Совещание", "#4F8DFF"),
            ("Проверка СИЗ", "#FF9F43"),
            ("Обучение", "#2ECC71"),
            ("Медосмотр", "#E74C3C"),
            ("День рождения", "#9B59B6"),
            ("Прочее", "#95A5A6"),
        ]
        n = 0
        for name, color in defaults:
            self.calendar_save_category(user_id, 0, name, color, False)
            n += 1
        return n

    def _seed_npa(self) -> None:
        """Заполнить каталог НПА по охране труда, если он пуст."""
        from services.npa_seed import seed_npa

        seed_npa(self)

    # ═══ Правовая база: НПА (Часть 26) ═══

    @staticmethod
    def _npa_year(date_str: str) -> str:
        """Извлечь год из даты DD.MM.YYYY / YYYY-MM-DD / YYYY."""
        d = (date_str or "").strip()
        if len(d) == 10:
            if d[2] == ".":
                return d[6:10]
            if d[4] == "-":
                return d[0:4]
        if len(d) == 4 and d.isdigit():
            return d
        return ""

    def npa_list(
        self,
        kind: str = "",
        category: str = "",
        status: str = "",
        q: str = "",
        year: str = "",
        fav_only: bool = False,
        user_id: int = 0,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """Список НПА с фильтрами. Фильтрация выполняется в Python,
        т.к. данные хранятся в отдельных колонках."""
        rows = self.fetch_all("SELECT * FROM npa_documents ORDER BY date DESC, id")
        fav_ids: set = set()
        rows_f = self.fetch_all(
            "SELECT npa_id FROM npa_favs WHERE user_id=?", (user_id,)
        )
        fav_ids = {r["npa_id"] for r in rows_f}
        out: List[Dict[str, Any]] = []
        q_l = (q or "").strip().lower()
        for r in rows:
            rec = dict(r)
            rec["is_fav"] = rec["id"] in fav_ids
            if kind and rec["kind"] != kind:
                continue
            if category and rec["category"] != category:
                continue
            if status and rec["status"] != status:
                continue
            if year and self._npa_year(rec.get("date", "")) != year:
                continue
            if fav_only and not rec["is_fav"]:
                continue
            if q_l:
                from services.npa_seed import npa_hay_match

                hay = " ".join(
                    [
                        str(rec.get("number", "")),
                        str(rec.get("title", "")),
                        str(rec.get("kind", "")),
                        str(rec.get("category", "")),
                        str(rec.get("audience", "")),
                        str(rec.get("notes", "")),
                    ]
                )
                if not npa_hay_match(q, hay):
                    continue
            out.append(rec)
        return out[:limit]

    def npa_get(self, doc_id: int) -> Optional[Dict[str, Any]]:
        rows = self.fetch_all("SELECT * FROM npa_documents WHERE id=?", (doc_id,))
        return dict(rows[0]) if rows else None

    def npa_save(self, data: Dict[str, Any], record_id: int = 0) -> int:
        try:
            fields = (
                "parent_id",
                "kind",
                "number",
                "title",
                "date",
                "status",
                "category",
                "audience",
                "url",
                "notes",
            )
            if record_id > 0:
                sets = ", ".join(f"{f}=?" for f in fields)
                vals = [data.get(f) for f in fields] + [record_id]
                self._backend.execute(
                    f"UPDATE npa_documents SET {sets}, "
                    "updated_at=datetime('now') WHERE id=?",
                    tuple(vals),
                )
                self._backend.commit()
                return record_id
            cols = ", ".join(fields)
            ph = ", ".join(["?"] * len(fields))
            cur = self._backend.execute(
                f"INSERT INTO npa_documents ({cols}) VALUES ({ph})",
                tuple(data.get(f) for f in fields),
            )
            self._backend.commit()
            return int(cur.lastrowid)
        except Exception:
            self._backend.rollback()
            raise

    def npa_delete(self, doc_id: int) -> bool:
        try:
            self._backend.execute("DELETE FROM npa_documents WHERE id=?", (doc_id,))
            self._backend.execute("DELETE FROM npa_favs WHERE npa_id=?", (doc_id,))
            self._backend.commit()
            self.log_event("NPA document deleted", "WARNING", {"id": doc_id})
            return True
        except Exception:
            self._backend.rollback()
            return False

    def npa_facets(self, user_id: int) -> Dict[str, List[Dict[str, Any]]]:
        """Фасетные срезы: количество документов по виду, категории, статусу, году."""
        rows = self.fetch_all("SELECT * FROM npa_documents ORDER BY id")
        kind_map: Dict[str, int] = {}
        cat_map: Dict[str, int] = {}
        status_map: Dict[str, int] = {}
        year_map: Dict[str, int] = {}
        for r in rows:
            k = str(r["kind"])
            kind_map[k] = kind_map.get(k, 0) + 1
            cat = str(r["category"] or "Прочее")
            cat_map[cat] = cat_map.get(cat, 0) + 1
            st = str(r["status"])
            status_map[st] = status_map.get(st, 0) + 1
            y = self._npa_year(str(r["date"] or ""))
            if y:
                year_map[y] = year_map.get(y, 0) + 1
        return {
            "kinds": [{"value": k, "count": v} for k, v in sorted(kind_map.items())],
            "categories": [
                {"value": k, "count": v} for k, v in sorted(cat_map.items())
            ],
            "statuses": [
                {"value": k, "count": v} for k, v in sorted(status_map.items())
            ],
            "years": [
                {"value": k, "count": v}
                for k, v in sorted(year_map.items(), reverse=True)
            ],
        }

    def npa_toggle_fav(self, user_id: int, doc_id: int) -> bool:
        rows = self.fetch_all(
            "SELECT id FROM npa_favs WHERE user_id=? AND npa_id=?", (user_id, doc_id)
        )
        try:
            if rows:
                self._backend.execute(
                    "DELETE FROM npa_favs WHERE user_id=? AND npa_id=?",
                    (user_id, doc_id),
                )
                fav = False
            else:
                self._backend.execute(
                    "INSERT INTO npa_favs (user_id, npa_id) VALUES (?, ?)",
                    (user_id, doc_id),
                )
                fav = True
            self._backend.commit()
            return fav
        except Exception:
            self._backend.rollback()
            return False

    def npa_import(self, records: List[Dict[str, Any]]) -> int:
        """Массовый импорт НПА из списка словарей. Возвращает число добавленных."""
        n = 0
        try:
            for rec in records:
                self.npa_save(rec)
                n += 1
            self._backend.commit()
            return n
        except Exception:
            self._backend.rollback()
            raise

    def save_tab_session(self, tabs: List[Dict[str, Any]]) -> None:
        try:
            self._backend.execute("DELETE FROM tab_sessions")
            for i, t in enumerate(tabs):
                self._backend.execute(
                    "INSERT INTO tab_sessions "
                    "(tab_index, tab_text, tab_type, tab_data, is_locked) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        i,
                        t.get("text", ""),
                        t.get("type", "home"),
                        t.get("data", ""),
                        1 if t.get("locked") else 0,
                    ),
                )
            self._backend.commit()
        except Exception:
            self._backend.rollback()

    def load_tab_session(self) -> List[Dict[str, Any]]:
        try:
            rows = self.fetch_all("SELECT * FROM tab_sessions ORDER BY tab_index")
            return [
                {
                    "text": r["tab_text"],
                    "type": r["tab_type"],
                    "data": r["tab_data"],
                    "locked": bool(r["is_locked"]),
                }
                for r in rows
            ]
        except Exception:
            return []

    def save_home_layout(self, tiles: List[Dict[str, Any]]) -> None:
        try:
            self._backend.execute("DELETE FROM home_layout")
            for i, t in enumerate(tiles):
                self._backend.execute(
                    "INSERT INTO home_layout (tile_key, tile_label, tile_color, tile_icon, position, visible) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        t.get("key", ""),
                        t.get("label", ""),
                        t.get("color", "#007AFF"),
                        t.get("icon", "📁"),
                        i,
                        1 if t.get("visible", True) else 0,
                    ),
                )
            self._backend.commit()
        except Exception:
            self._backend.rollback()

    def load_home_layout(self) -> List[Dict[str, Any]]:
        try:
            rows = self.fetch_all(
                "SELECT * FROM home_layout WHERE visible=1 ORDER BY position"
            )
            return [
                {
                    "key": r["tile_key"],
                    "label": r["tile_label"],
                    "color": r["tile_color"],
                    "icon": r["tile_icon"],
                }
                for r in rows
            ]
        except Exception:
            return []

    def all_available_modules(self) -> List[Dict[str, Any]]:
        try:
            hidden = self.fetch_all(
                "SELECT * FROM home_layout WHERE visible=0 ORDER BY position"
            )
            visible_keys = {
                r["tile_key"]
                for r in self.fetch_all(
                    "SELECT tile_key FROM home_layout WHERE visible=1"
                )
            }
        except Exception:
            return []
        all_modules = [
            ("employees", "Сотрудники", "#007AFF", "🧑‍💼"),
            ("violations", "Нарушения", "#FF3B30", "⚠️"),
            ("incidents", "Происшествия", "#FF9500", "🔥"),
            ("ppe", "СИЗ", "#34C759", "🛡️"),
            ("training", "Обучение", "#5856D6", "📚"),
            ("permits", "Наряды-допуски", "#FF2D55", "📋"),
            ("custom_ledger", "Журнал", "#AF52DE", "📓"),
            ("companies", "Компании", "#5AC8FA", "🏢"),
            ("notes", "Заметки", "#FF6482", "📝"),
            ("reminders", "Напоминания", "#F39C12", "⏰"),
            ("statistics", "Статистика", "#1ABC9C", "📊"),
            ("timeline", "Таймлайн", "#9B59B6", "📅"),
            ("ai_chat", "AI Чат", "#2ECC71", "🤖"),
        ]
        result = []
        for key, label, color, icon in all_modules:
            result.append(
                {
                    "key": key,
                    "label": label,
                    "color": color,
                    "icon": icon,
                    "visible": key in visible_keys,
                }
            )
        return result

    def add_record_link(
        self,
        source_table: str,
        source_id: int,
        target_table: str,
        target_id: int,
        link_type: str = "related",
    ) -> bool:
        try:
            self._backend.execute(
                "INSERT OR IGNORE INTO record_links "
                "(source_table, source_id, target_table, target_id, link_type) "
                "VALUES (?, ?, ?, ?, ?)",
                (source_table, source_id, target_table, target_id, link_type),
            )
            self._backend.commit()
            return True
        except Exception:
            self._backend.rollback()
            return False

    def remove_record_link(self, link_id: int) -> bool:
        try:
            self._backend.execute("DELETE FROM record_links WHERE id=?", (link_id,))
            self._backend.commit()
            return True
        except Exception:
            self._backend.rollback()
            return False

    def get_record_links(self, table: str, record_id: int) -> List[Dict[str, Any]]:
        try:
            rows = self._backend.execute(
                "SELECT * FROM record_links WHERE "
                "(source_table=? AND source_id=?) OR "
                "(target_table=? AND target_id=?)",
                (table, record_id, table, record_id),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_linked_record_name(self, table: str, record_id: int) -> str:
        try:
            if table == "companies":
                cur = self._backend.execute(
                    "SELECT name FROM companies WHERE id=?", (record_id,)
                )
                r = cur.fetchone()
                return r["name"] if r else f"#{record_id}"
            else:
                records = self.get_json_records(table)
                for rec in records:
                    if rec["id"] == record_id:
                        dj = rec.get("data_json", {})
                        for field in (
                            "full_name",
                            "name",
                            "title",
                            "description",
                            "ФИО",
                        ):
                            if dj.get(field):
                                return dj[field][:50]
                        return f"#{record_id}"
                return f"#{record_id}"
        except Exception:
            return f"#{record_id}"

    def save_reminder(
        self,
        title: str,
        description: str,
        due_date: str,
        check_interval: int = 60,
        is_done: int = 0,
        reminder_id: int = 0,
    ) -> int:
        try:
            if reminder_id > 0:
                self._backend.execute(
                    "UPDATE reminders SET title=?, description=?, due_date=?, "
                    "check_interval=?, is_done=? WHERE id=?",
                    (
                        title,
                        description,
                        due_date,
                        check_interval,
                        is_done,
                        reminder_id,
                    ),
                )
                self._backend.commit()
                return reminder_id
            cur = self._backend.execute(
                "INSERT INTO reminders (title, description, due_date, check_interval) "
                "VALUES (?, ?, ?, ?)",
                (title, description, due_date, check_interval),
            )
            self._backend.commit()
            return int(cur.lastrowid)
        except Exception:
            self._backend.rollback()
            self.log_event(f"Reminder save error: {traceback.format_exc()}", "CRITICAL")
            raise

    def get_reminders(self, include_done: bool = False) -> List[Dict[str, Any]]:
        if include_done:
            return self.fetch_all("SELECT * FROM reminders ORDER BY due_date")
        return self.fetch_all(
            "SELECT * FROM reminders WHERE is_done=0 ORDER BY due_date"
        )

    def get_due_reminders(self) -> List[Dict[str, Any]]:
        return self.fetch_all(
            "SELECT * FROM reminders WHERE is_done=0 AND due_date <= ?",
            (datetime.now().isoformat()[:10],),
        )

    def delete_reminder(self, reminder_id: int) -> bool:
        try:
            self._backend.execute("DELETE FROM reminders WHERE id=?", (reminder_id,))
            self._backend.commit()
            return True
        except Exception:
            self._backend.rollback()
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
            self._backend.execute(
                "INSERT INTO textbook (short_code, full_text) VALUES (?, ?) "
                "ON CONFLICT(short_code) DO UPDATE SET full_text=excluded.full_text",
                (short_code, full_text),
            )
            self._backend.commit()
            return True
        except Exception:
            self._backend.rollback()
            return False

    def delete_textbook_entry(self, short_code: str) -> bool:
        try:
            self._backend.execute(
                "DELETE FROM textbook WHERE short_code=?", (short_code,)
            )
            self._backend.commit()
            return True
        except Exception:
            self._backend.rollback()
            return False

    def get_print_templates(self, template_type: str = "order") -> List[Dict[str, Any]]:
        return self.fetch_all(
            "SELECT * FROM print_templates WHERE template_type=? ORDER BY is_default DESC",
            (template_type,),
        )

    def get_all_print_templates(self) -> List[Dict[str, Any]]:
        return self.fetch_all(
            "SELECT * FROM print_templates ORDER BY is_default DESC, name"
        )

    def save_print_template(
        self,
        name: str,
        template_type: str,
        html_content: str,
        css_content: str = "",
        template_id: int = 0,
    ) -> int:
        try:
            if template_id > 0:
                self._backend.execute(
                    "UPDATE print_templates SET name=?, html_content=?, css_content=? "
                    "WHERE id=?",
                    (name, html_content, css_content, template_id),
                )
                self._backend.commit()
                return template_id
            cur = self._backend.execute(
                "INSERT INTO print_templates (name, template_type, html_content, css_content) "
                "VALUES (?, ?, ?, ?)",
                (name, template_type, html_content, css_content),
            )
            self._backend.commit()
            return int(cur.lastrowid)
        except Exception:
            self._backend.rollback()
            self.log_event(
                f"Print template error: {traceback.format_exc()}", "CRITICAL"
            )
            raise

    def get_ai_setting(self, key: str, default: str = "") -> str:
        r = self.fetch_one("SELECT value FROM ai_settings WHERE key=?", (key,))
        return r["value"] if r else default

    def set_ai_setting(self, key: str, value: str) -> None:
        try:
            self._backend.execute(
                "INSERT INTO ai_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            self._backend.commit()
        except Exception:
            self._backend.rollback()

    # --- Encryption for sensitive settings ---

    def _get_encryption_key(self) -> bytes:
        key = self.get_setting("_master_enc_key", "")
        if not key:
            try:
                from cryptography.fernet import Fernet

                key = Fernet.generate_key().decode()
                self.upsert_setting("_master_enc_key", key)
            except Exception:
                return b""
        return key.encode() if isinstance(key, str) else key

    def encrypt_value(self, plaintext: str) -> str:
        if not plaintext:
            return ""
        try:
            from cryptography.fernet import Fernet

            f = Fernet(self._get_encryption_key())
            return f.encrypt(plaintext.encode()).decode()
        except Exception:
            return plaintext

    def decrypt_value(self, ciphertext: str) -> str:
        if not ciphertext:
            return ""
        try:
            from cryptography.fernet import Fernet

            f = Fernet(self._get_encryption_key())
            return f.decrypt(ciphertext.encode()).decode()
        except Exception:
            return ciphertext

    # --- Chat history persistence ---

    def save_chat_message(
        self, session_id: str, role: str, content: str, model: str = ""
    ) -> int:
        try:
            cur = self._backend.execute(
                "INSERT INTO chat_history (session_id, role, content, model) "
                "VALUES (?, ?, ?, ?)",
                (session_id, role, content, model),
            )
            self._backend.commit()
            return int(cur.lastrowid)
        except Exception:
            self._backend.rollback()
            return 0

    def get_chat_history(
        self, session_id: str = "default", limit: int = 100
    ) -> List[Dict[str, Any]]:
        return self.fetch_all(
            "SELECT * FROM chat_history WHERE session_id=? ORDER BY id ASC LIMIT ?",
            (session_id, limit),
        )

    def clear_chat_history(self, session_id: str = "default") -> None:
        try:
            self._backend.execute(
                "DELETE FROM chat_history WHERE session_id=?", (session_id,)
            )
            self._backend.commit()
        except Exception:
            self._backend.rollback()

    def get_chat_sessions(self) -> List[str]:
        rows = self.fetch_all(
            "SELECT DISTINCT session_id FROM chat_history ORDER BY session_id"
        )
        return [r["session_id"] for r in rows]

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
        self.log_event(
            "CSV export completed", "INFO", {"table": table, "path": file_path}
        )
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
        self._backend.execute(
            "INSERT INTO backups (created_at, file_path, size_bytes, sha256) "
            "VALUES (?, ?, ?, ?)",
            (datetime.now().isoformat(), zip_path, size_b, csum),
        )
        self._backend.commit()
        self.log_event(
            "Backup created", "INFO", {"path": zip_path, "size": size_b, "sha256": csum}
        )
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
                self.log_event(
                    "Backup checksum mismatch",
                    "CRITICAL",
                    {"expected": expected, "actual": actual},
                )
                return False
            tmp = os.path.join(tempfile.gettempdir(), "suot_restore_tmp.db")
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extract(AppConfig.DB_NAME, tempfile.gettempdir())
                extracted = os.path.join(tempfile.gettempdir(), AppConfig.DB_NAME)
                os.replace(extracted, tmp)
            self._backend.close()
            shutil.copy2(tmp, self.database_path)
            self._configure_pragmas()
            os.remove(tmp)
            self.log_event(
                "Database restored from backup",
                "WARNING",
                {"backup_id": backup_id, "path": zip_path},
            )
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
                self._backend.execute("DELETE FROM backups WHERE id=?", (backup_id,))
                self._backend.commit()
                self.log_event("Backup deleted", "INFO", {"id": backup_id, "path": fp})
            return True
        except Exception:
            self._backend.rollback()
            self.log_event(f"Delete backup error: {traceback.format_exc()}", "CRITICAL")
            return False

    def _configure_pragmas(self) -> None:
        pass

    def get_table_count(self, table: str) -> int:
        self._validate_json_table(table)
        r = self.fetch_one(f"SELECT COUNT(*) as c FROM {table}")
        return r["c"] if r else 0

    def count_overdue(
        self,
        table: str,
        date_col: str = "Срок устранения",
        status_col: str = "Статус",
        overdue_status: str = "Просрочено",
    ) -> int:
        self._validate_json_table(table)
        now = datetime.now()
        overdue = 0
        for rec in self.get_json_records(table):
            dj = rec.get("data_json", {})
            status = str(dj.get(status_col, ""))
            dl_str = str(dj.get(date_col, ""))
            if status == overdue_status:
                overdue += 1
            elif dl_str:
                try:
                    parts = dl_str.split(".")
                    if len(parts) == 3:
                        dl = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
                        if dl < now and status not in (
                            "Закрыто",
                            "Аннулирован",
                            "Списано",
                            "Архив",
                        ):
                            overdue += 1
                except Exception:
                    pass
        return overdue

    def get_statistics(self) -> Dict[str, Any]:
        emp_count = self.get_table_count("employees")
        viol_count = self.get_table_count("violations")
        comp_count = self.fetch_one("SELECT COUNT(*) as c FROM companies")
        now = datetime.now()
        fines_total = 0.0
        for v in self.get_json_records("violations"):
            dj = v.get("data_json", {})
            fine_str = str(dj.get("Штраф", "0")).replace(" ", "").replace(",", ".")
            try:
                fines_total += float(fine_str)
            except Exception:
                pass
        return {
            "employees_total": emp_count,
            "violations_total": viol_count,
            "companies_total": comp_count["c"] if comp_count else 0,
            "fines_total": fines_total,
            "incidents_total": self.get_table_count("incidents"),
            "ppe_total": self.get_table_count("ppe"),
            "training_total": self.get_table_count("training"),
            "permits_total": self.get_table_count("permits"),
            "overdue_total": self.count_overdue(
                "violations", "Срок устранения", "Статус", "Просрочено"
            ),
            "overdue_ppe": self.count_overdue(
                "ppe", "Срок замены", "Статус", "Активно"
            ),
            "overdue_training": self.count_overdue(
                "training", "Срок действия", "Статус", "Активно"
            ),
            "overdue_permits": self.count_overdue(
                "permits", "Дата окончания", "Статус", "Оформлен"
            ),
        }

    def get_health(self) -> Dict[str, Any]:
        import os

        info = {"tables": {}, "db_size_bytes": 0, "cache_entries": len(self._cache)}
        try:
            bh = self._backend.health()
            info["backend"] = bh
            if os.path.exists(self.database_path):
                info["db_size_bytes"] = os.path.getsize(self.database_path)
        except Exception:
            pass
        for tbl in sorted(self.JSON_TABLES):
            try:
                info["tables"][tbl] = self.get_table_count(tbl)
            except Exception:
                info["tables"][tbl] = -1
        try:
            r = self.fetch_one("SELECT COUNT(*) as c FROM users")
            info["users"] = r["c"] if r else 0
        except Exception:
            info["users"] = 0
        try:
            r = self.fetch_one("SELECT COUNT(*) as c FROM audit_log")
            info["audit_entries"] = r["c"] if r else 0
        except Exception:
            info["audit_entries"] = 0
        try:
            r = self.fetch_one("SELECT COUNT(*) as c FROM reminders WHERE is_done=0")
            info["active_reminders"] = r["c"] if r else 0
        except Exception:
            info["active_reminders"] = 0
        try:
            r = self.fetch_one("SELECT COUNT(*) as c FROM webhooks WHERE enabled=1")
            info["active_webhooks"] = r["c"] if r else 0
        except Exception:
            info["active_webhooks"] = 0
        try:
            info["media_size_bytes"] = (
                sum(
                    os.path.getsize(os.path.join(dirpath, f))
                    for dirpath, _, filenames in os.walk(RUNTIME_PATHS.media_dir)
                    for f in filenames
                )
                if os.path.isdir(RUNTIME_PATHS.media_dir)
                else 0
            )
        except Exception:
            info["media_size_bytes"] = 0
        return info

    # ── AI: история диалогов (Часть 27) ──

    def chat_threads_list(self, user_id: int) -> List[Dict[str, Any]]:
        try:
            rows = self.fetch_all(
                "SELECT * FROM chat_threads WHERE user_id=? "
                "ORDER BY updated_at DESC, id DESC",
                (user_id,),
            )
            return [dict(r) for r in rows]
        except Exception:
            return []

    def chat_thread_create(self, user_id: int, title: str = "") -> int:
        t = title.strip() or "Новый диалог"
        cur = self._backend.execute(
            "INSERT INTO chat_threads (user_id, title) VALUES (?, ?)",
            (user_id, t),
        )
        self._backend.commit()
        return cur.lastrowid

    def chat_thread_rename(self, thread_id: int, user_id: int, title: str) -> bool:
        try:
            cur = self._backend.execute(
                "UPDATE chat_threads SET title=?, updated_at=datetime('now') "
                "WHERE id=? AND user_id=?",
                (title.strip(), thread_id, user_id),
            )
            self._backend.commit()
            return cur.rowcount > 0
        except Exception:
            self._backend.rollback()
            return False

    def chat_thread_delete(self, thread_id: int, user_id: int) -> bool:
        try:
            self._backend.execute(
                "DELETE FROM chat_messages WHERE thread_id=?", (thread_id,)
            )
            cur = self._backend.execute(
                "DELETE FROM chat_threads WHERE id=? AND user_id=?",
                (thread_id, user_id),
            )
            self._backend.commit()
            return cur.rowcount > 0
        except Exception:
            self._backend.rollback()
            return False

    def chat_messages_list(self, thread_id: int, user_id: int) -> List[Dict[str, Any]]:
        try:
            rows = self.fetch_all(
                "SELECT * FROM chat_messages WHERE thread_id=? ORDER BY id",
                (thread_id,),
            )
            return [dict(r) for r in rows]
        except Exception:
            return []

    def chat_message_add(self, thread_id: int, role: str, content: str) -> None:
        if not content.strip():
            return
        try:
            self._backend.execute(
                "INSERT INTO chat_messages (thread_id, role, content) VALUES (?, ?, ?)",
                (thread_id, role, content),
            )
            self._backend.execute(
                "UPDATE chat_threads SET updated_at=datetime('now') WHERE id=?",
                (thread_id,),
            )
            self._backend.commit()
        except Exception:
            self._backend.rollback()

    def close(self) -> None:
        try:
            self._backend.close()
        except Exception:
            pass
