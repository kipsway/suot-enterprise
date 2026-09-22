from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Permission:
    view: str
    create: str
    edit: str
    delete: str
    export: str


_ACTIONS = ["view", "create", "edit", "delete", "export"]
_MODULES = [
    "employees",
    "violations",
    "incidents",
    "ppe",
    "training",
    "permits",
    "companies",
    "settings",
    "users",
    "audit",
    "backup",
    "ai",
    "analytics",
    "print",
    "import_export",
]


_PERMISSION_TABLE: Dict[str, Dict[str, bool]] = {
    "Administrator": {f"{mod}.{act}": True for mod in _MODULES for act in _ACTIONS},
    "Manager": {
        f"{mod}.{act}": True
        for mod in _MODULES
        for act in _ACTIONS
        if act in ("view", "create", "edit")
    },
    "Inspector": {
        f"{mod}.{act}": True for mod in _MODULES for act in _ACTIONS if act in ("view",)
    },
    "Viewer": {
        f"{mod}.{act}": True for mod in _MODULES for act in _ACTIONS if act == "view"
    },
    "Observer": {
        f"{mod}.{act}": True for mod in _MODULES for act in _ACTIONS if act == "view"
    },
}

_OVERRIDES: Dict[str, Dict[str, bool]] = {
    "Inspector": {
        "incidents.create": True,
        "incidents.edit": True,
        "violations.create": True,
        "violations.edit": True,
        "ppe.view": True,
        "training.view": True,
    },
    "Manager": {
        "settings.view": True,
        "users.view": False,
        "audit.view": True,
        "backup.create": True,
    },
}

for role, overrides in _OVERRIDES.items():
    if role in _PERMISSION_TABLE:
        _PERMISSION_TABLE[role].update(overrides)


@dataclass
class UserPermissions:
    role: str
    _cache: Dict[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._cache = dict(
            _PERMISSION_TABLE.get(self.role, _PERMISSION_TABLE["Inspector"])
        )

    def can(self, module: str, action: str) -> bool:
        key = f"{module}.{action}"
        return self._cache.get(key, False)

    def can_view(self, module: str) -> bool:
        return self.can(module, "view")

    def can_create(self, module: str) -> bool:
        return self.can(module, "create")

    def can_edit(self, module: str) -> bool:
        return self.can(module, "edit")

    def can_delete(self, module: str) -> bool:
        return self.can(module, "delete")

    def can_export(self, module: str) -> bool:
        return self.can(module, "export")

    @staticmethod
    def roles() -> List[str]:
        return list(_PERMISSION_TABLE.keys())

    @staticmethod
    def modules() -> List[str]:
        return list(_MODULES)

    @staticmethod
    def actions() -> List[str]:
        return list(_ACTIONS)
