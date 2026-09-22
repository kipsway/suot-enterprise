from typing import Any, Dict, List, Optional, Tuple


class _NullLock:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


_null_lock = _NullLock


class DBBackend:
    def connect(self) -> None: ...
    def close(self) -> None: ...
    def execute(self, sql: str, params: Tuple[Any, ...] = ()) -> Any: ...
    def executemany(self, sql: str, params: List[Tuple[Any, ...]]) -> None: ...
    def executescript(self, script: str) -> None: ...
    def fetch_all(
        self, sql: str, params: Tuple[Any, ...] = ()
    ) -> List[Dict[str, Any]]: ...
    def fetch_one(
        self, sql: str, params: Tuple[Any, ...] = ()
    ) -> Optional[Dict[str, Any]]: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def lastrowid(self) -> int: ...
    def table_exists(self, name: str) -> bool: ...
    def health(self) -> Dict[str, Any]: ...


class SQLiteBackend(DBBackend):
    def __init__(self, db_path: str) -> None:
        self._path = db_path
        self._conn = None
        self._lock = None
        self.connect()

    def connect(self) -> None:
        import sqlite3, threading

        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False, timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        # регистронезависимость для кириллицы (NOCASE в SQLite — только ASCII)
        self._conn.create_function(
            "pylower",
            1,
            lambda s: s.lower() if isinstance(s, str) else s,
            deterministic=True,
        )

    def close(self) -> None:
        with self._lock or _null_lock():
            if self._conn:
                self._conn.close()
                self._conn = None

    def execute(self, sql: str, params: Tuple[Any, ...] = ()) -> Any:
        with self._lock:
            return self._conn.execute(sql, params)

    def executemany(self, sql: str, params: List[Tuple[Any, ...]]) -> None:
        with self._lock:
            self._conn.executemany(sql, params)

    def executescript(self, script: str) -> None:
        with self._lock:
            self._conn.executescript(script)

    def fetch_all(self, sql: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def fetch_one(
        self, sql: str, params: Tuple[Any, ...] = ()
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            r = cur.fetchone()
            return dict(r) if r else None

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def rollback(self) -> None:
        with self._lock:
            self._conn.rollback()

    @property
    def lastrowid(self) -> int:
        return self._conn.lastrowid

    def table_exists(self, name: str) -> bool:
        r = self.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
        )
        return r is not None

    def health(self) -> Dict[str, Any]:
        try:
            r = self.fetch_one("SELECT COUNT(*) AS cnt FROM sqlite_master")
            return {"status": "ok", "type": "sqlite", "tables": r["cnt"] if r else 0}
        except Exception as e:
            return {"status": "error", "error": str(e)}


class PostgreSQLBackend(DBBackend):
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        dbname: str = "suot",
        user: str = "suot",
        password: str = "",
    ) -> None:
        self._config = {
            "host": host,
            "port": port,
            "dbname": dbname,
            "user": user,
            "password": password,
        }
        self._conn = None
        self.connect()

    def connect(self) -> None:
        try:
            import psycopg2
            import psycopg2.extras

            self._conn = psycopg2.connect(**self._config)
            self._conn.autocommit = False
        except ImportError:
            raise ImportError(
                "psycopg2 is required for PostgreSQL support. "
                "Install: pip install psycopg2-binary"
            )

    def close(self) -> None:
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None

    def execute(self, sql: str, params: Tuple[Any, ...] = ()) -> Any:
        cur = self._conn.cursor()
        cur.execute(sql.replace("?", "%s"), params)
        return cur

    def executemany(self, sql: str, params: List[Tuple[Any, ...]]) -> None:
        cur = self._conn.cursor()
        cur.executemany(sql.replace("?", "%s"), params)

    def executescript(self, script: str) -> None:
        cur = self._conn.cursor()
        for stmt in script.split(";"):
            s = stmt.strip()
            if s:
                try:
                    cur.execute(s)
                except Exception:
                    pass

    def fetch_all(self, sql: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        import psycopg2.extras

        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql.replace("?", "%s"), params)
        return [dict(r) for r in cur.fetchall()]

    def fetch_one(
        self, sql: str, params: Tuple[Any, ...] = ()
    ) -> Optional[Dict[str, Any]]:
        import psycopg2.extras

        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql.replace("?", "%s"), params)
        r = cur.fetchone()
        return dict(r) if r else None

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    @property
    def lastrowid(self) -> int:
        cur = self._conn.cursor()
        cur.execute("SELECT LASTVAL()")
        r = cur.fetchone()
        return r[0] if r else 0

    def table_exists(self, name: str) -> bool:
        r = self.fetch_one(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_name=?) AS e",
            (name,),
        )
        return r and r["e"]

    def health(self) -> Dict[str, Any]:
        try:
            r = self.fetch_one(
                "SELECT COUNT(*) AS cnt FROM information_schema.tables "
                "WHERE table_schema='public'"
            )
            return {
                "status": "ok",
                "type": "postgresql",
                "tables": r["cnt"] if r else 0,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


def create_backend(config: Dict[str, Any]) -> DBBackend:
    backend_type = config.get("type", "sqlite")
    if backend_type == "postgresql":
        return PostgreSQLBackend(
            host=config.get("host", "localhost"),
            port=int(config.get("port", 5432)),
            dbname=config.get("dbname", "suot"),
            user=config.get("user", "suot"),
            password=config.get("password", ""),
        )
    db_path = config.get("path", "")
    if not db_path:
        from app_core.config import AppConfig

        db_path = str(AppConfig.db_path)
    return SQLiteBackend(db_path)
