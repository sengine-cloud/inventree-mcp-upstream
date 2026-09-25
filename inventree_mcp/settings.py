"""Helpers for reading InvenTreeMCP's own plugin settings.

Shared by mcp_transport.py (REQUIRE_AUTH) and proxy.py (MCP_READ_ONLY) so
there is one place that resolves the plugin instance and fails safe.
"""

from __future__ import annotations

import contextlib
import os
from typing import Any


def _get_plugin_instance() -> Any:
    from plugin import registry

    return registry.get_plugin("inventree-mcp")


_TRUE = {"1", "true", "yes", "on"}


def _env_override(key: str) -> str | None:
    """INVENTREE_MCP_<KEY> from the environment, if set.

    Lets a deployment pin a setting in its config instead of the database.
    An env value always wins over the stored setting.
    """
    value = os.environ.get(f"INVENTREE_MCP_{key}")
    return value.strip() if value is not None else None


def get_plugin_setting(key: str, default: bool = True) -> bool:
    """Read one of this plugin's own boolean settings.

    Fails safe to *default* if the plugin instance can't be resolved (e.g.
    outside of a real request) or the setting lookup raises - both of this
    plugin's settings (REQUIRE_AUTH, MCP_READ_ONLY) default to the
    more restrictive value, so "can't tell" and "restricted" should behave
    the same.
    """
    env = _env_override(key)
    if env is not None:
        return env.lower() in _TRUE

    plugin = _get_plugin_instance()

    if plugin is None:
        return default

    with contextlib.suppress(Exception):
        return bool(plugin.get_setting(key))

    return default


def get_plugin_value(key: str, default: Any = None) -> Any:
    """Read one of this plugin's settings, env override first, failing safe to *default*."""
    env = _env_override(key)
    if env is not None:
        return env
    plugin = _get_plugin_instance()
    if plugin is None:
        return default
    with contextlib.suppress(Exception):
        return plugin.get_setting(key)
    return default
