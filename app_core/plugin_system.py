"""Plugin system — load, manage, and hook third-party modules."""

import importlib
import inspect
import json
import os
import sys
from typing import Any, Callable, Dict, List, Optional, Type


class PluginInterface:
    name: str = ""
    version: str = "1.0.0"
    author: str = ""
    description: str = ""

    def on_startup(self) -> None:
        """Called when the application starts, after all modules are loaded."""

    def on_record_added(self, table: str, record_id: int, data: dict) -> None:
        """Called when a record is created."""

    def on_record_edited(self, table: str, record_id: int, data: dict) -> None:
        """Called when a record is updated."""

    def on_record_deleted(self, table: str, record_id: int) -> None:
        """Called when a record is deleted."""

    def on_export(self, table: str, format: str, count: int) -> None:
        """Called when data is exported."""


class PluginInfo:
    def __init__(
        self,
        name: str,
        instance: PluginInterface,
        enabled: bool = True,
        module_path: str = "",
    ):
        self.name = name
        self.instance = instance
        self.enabled = enabled
        self.module_path = module_path


class PluginLoader:
    def __init__(self, plugin_dir: str):
        self._plugin_dir = plugin_dir
        self._plugins: Dict[str, PluginInfo] = {}

    def discover(self) -> List[PluginInfo]:
        self._plugins.clear()
        if not os.path.isdir(self._plugin_dir):
            return []
        for entry in os.listdir(self._plugin_dir):
            plugin_path = os.path.join(self._plugin_dir, entry)
            init_path = os.path.join(plugin_path, "__init__.py")
            if os.path.isfile(init_path):
                plugin_info = self._load_plugin(entry, plugin_path)
                if plugin_info:
                    self._plugins[entry] = plugin_info
        return list(self._plugins.values())

    def _load_plugin(self, name: str, path: str) -> Optional[PluginInfo]:
        try:
            if path not in sys.path:
                sys.path.insert(0, path)
            mod = importlib.import_module(name)
            for _, obj in inspect.getmembers(mod, inspect.isclass):
                if issubclass(obj, PluginInterface) and obj is not PluginInterface:
                    instance = obj()
                    return PluginInfo(name=name, instance=instance, module_path=path)
            return None
        except Exception:
            return None

    def get_plugin(self, name: str) -> Optional[PluginInfo]:
        return self._plugins.get(name)

    def all_plugins(self) -> List[PluginInfo]:
        return list(self._plugins.values())

    def enabled_plugins(self) -> List[PluginInfo]:
        return [p for p in self._plugins.values() if p.enabled]

    def set_enabled(self, name: str, enabled: bool) -> None:
        if name in self._plugins:
            self._plugins[name].enabled = enabled


class PluginManager:
    def __init__(self, plugin_dir: str):
        self.loader = PluginLoader(plugin_dir)
        self._hooks: Dict[str, List[Callable]] = {
            "startup": [],
            "record_added": [],
            "record_edited": [],
            "record_deleted": [],
            "export": [],
        }

    def discover_plugins(self) -> List[PluginInfo]:
        plugins = self.loader.discover()
        self._rebind_hooks()
        return plugins

    def _rebind_hooks(self) -> None:
        for key in self._hooks:
            self._hooks[key].clear()
        for p in self.loader.enabled_plugins():
            inst = p.instance
            self._hooks["startup"].append(inst.on_startup)
            self._hooks["record_added"].append(inst.on_record_added)
            self._hooks["record_edited"].append(inst.on_record_edited)
            self._hooks["record_deleted"].append(inst.on_record_deleted)
            self._hooks["export"].append(inst.on_export)

    def trigger(self, hook: str, *args: Any, **kwargs: Any) -> None:
        for cb in self._hooks.get(hook, []):
            try:
                cb(*args, **kwargs)
            except Exception:
                pass

    def set_plugin_enabled(self, name: str, enabled: bool) -> None:
        self.loader.set_enabled(name, enabled)
        self._rebind_hooks()
