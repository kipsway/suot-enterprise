from typing import Any, Dict, Optional

from services.database import DatabaseManager


class AuditService:
    def __init__(self, user: Optional[Dict[str, Any]] = None) -> None:
        self.db = DatabaseManager()
        self._user = user or {}

    def log(
        self,
        event: str,
        severity: str = "INFO",
        details: Optional[Dict[str, Any]] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
    ) -> None:
        meta = {
            "username": self._user.get("username", "system"),
            "role": self._user.get("role", "system"),
            "ip": self._user.get("ip", ""),
        }
        if details:
            meta["details"] = details
        if entity_type:
            meta["entity_type"] = entity_type
        if entity_id:
            meta["entity_id"] = entity_id

        self.db.log_event(event, severity, meta)

    def log_view(self, entity_type: str, entity_id: int, entity_name: str = "") -> None:
        self.log(
            f"Просмотр {entity_type} #{entity_id} {entity_name}",
            "INFO",
            entity_type=entity_type,
            entity_id=entity_id,
        )

    def log_create(
        self, entity_type: str, entity_id: int, entity_name: str = ""
    ) -> None:
        self.log(
            f"Создание {entity_type} #{entity_id} {entity_name}",
            "INFO",
            entity_type=entity_type,
            entity_id=entity_id,
        )

    def log_edit(
        self, entity_type: str, entity_id: int, changes: Dict[str, Any]
    ) -> None:
        self.log(
            f"Изменение {entity_type} #{entity_id}",
            "INFO",
            details=changes,
            entity_type=entity_type,
            entity_id=entity_id,
        )

    def log_delete(
        self, entity_type: str, entity_id: int, entity_name: str = ""
    ) -> None:
        self.log(
            f"Удаление {entity_type} #{entity_id} {entity_name}",
            "WARNING",
            entity_type=entity_type,
            entity_id=entity_id,
        )

    def log_login(self, username: str, success: bool, reason: str = "") -> None:
        sev = "INFO" if success else "WARNING"
        self.log(
            f"{'Успешный' if success else 'Неудачный'} вход: {username}{' - ' + reason if reason else ''}",
            sev,
        )

    def log_export(self, module: str, count: int) -> None:
        self.log(
            f"Экспорт {module}: {count} записей",
            "INFO",
            details={"module": module, "count": count},
        )

    def log_permission_denied(self, module: str, action: str) -> None:
        self.log(
            f"Отказ в доступе: {action} -> {module}",
            "WARNING",
            details={"module": module, "action": action},
        )
