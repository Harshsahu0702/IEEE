import os
import sys
import inspect
import importlib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Type

from backend.monitoring.base import MonitoringPlugin, PluginMetadata

logger = logging.getLogger(__name__)


class PluginRegistry:
    """
    Central registry for OmniSense monitoring plugins.
    Features:
    - Auto-discovery in monitoring/*/ folders
    - Dynamic plugin instantiation
    - Metadata queries for AI Agent planning
    - Strict rule: Agent never hardcodes monitoring logic; it queries the registry.
    """
    _instance: Optional["PluginRegistry"] = None

    def __init__(self):
        self._plugins: Dict[str, Type[MonitoringPlugin]] = {}
        self._metadata_cache: Dict[str, PluginMetadata] = {}
        self.discover_plugins()

    @classmethod
    def get_instance(cls) -> "PluginRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_plugin(self, plugin_cls: Type[MonitoringPlugin]):
        """Registers a plugin class and caches its metadata."""
        try:
            # Instantiate temporary instance to retrieve metadata
            temp_instance = plugin_cls()
            meta = temp_instance.get_metadata()
            name = meta.name
            self._plugins[name] = plugin_cls
            self._metadata_cache[name] = meta
            logger.info(f"Registered plugin '{name}' ({meta.display_name})")
        except Exception as e:
            logger.error(f"Failed to register plugin {plugin_cls}: {e}")

    def discover_plugins(self):
        """
        Scans all subdirectories in backend/monitoring/ for MonitoringPlugin implementations.
        """
        monitoring_dir = Path(__file__).resolve().parent

        for child in monitoring_dir.iterdir():
            if child.is_dir() and not child.name.startswith("__"):
                plugin_file = child / "plugin.py"
                if plugin_file.exists():
                    module_name = f"backend.monitoring.{child.name}.plugin"
                    try:
                        module = importlib.import_module(module_name)
                        for _, obj in inspect.getmembers(module, inspect.isclass):
                            if (
                                issubclass(obj, MonitoringPlugin)
                                and obj is not MonitoringPlugin
                            ):
                                self.register_plugin(obj)
                    except Exception as e:
                        logger.error(f"Error importing plugin module {module_name}: {e}")

    def list_plugins(self) -> List[PluginMetadata]:
        """Returns metadata for all discovered plugins."""
        return list(self._metadata_cache.values())

    def get_plugin(self, name: str) -> Optional[MonitoringPlugin]:
        """Instantiates and returns a new plugin instance by name."""
        plugin_cls = self._plugins.get(name)
        if plugin_cls:
            return plugin_cls()
        return None

    def get_plugin_metadata(self, name: str) -> Optional[PluginMetadata]:
        return self._metadata_cache.get(name)


registry = PluginRegistry.get_instance()


def list_plugins() -> List[PluginMetadata]:
    return registry.list_plugins()


def get_plugin(name: str) -> Optional[MonitoringPlugin]:
    return registry.get_plugin(name)
