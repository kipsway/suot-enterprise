"""Example plugin: Hello World — demonstrates the plugin system."""

from app_core.plugin_system import PluginInterface
from services.database import DatabaseManager


class HelloWorldPlugin(PluginInterface):
    name = "hello_world"
    version = "1.0.0"
    author = "SUOT Team"
    description = "Пример плагина: логирует добавление записей"

    def on_startup(self) -> None:
        db = DatabaseManager()
        db.log_event("HelloWorld plugin loaded", "INFO")

    def on_record_added(self, table: str, record_id: int, data: dict) -> None:
        db = DatabaseManager()
        db.log_event(f"[HelloWorld] Record added: {table}#{record_id}", "INFO")

    def on_record_deleted(self, table: str, record_id: int) -> None:
        db = DatabaseManager()
        db.log_event(f"[HelloWorld] Record deleted: {table}#{record_id}", "INFO")

    def on_export(self, table: str, fmt: str, count: int) -> None:
        db = DatabaseManager()
        db.log_event(f"[HelloWorld] Exported {count} {table} as {fmt}", "INFO")
