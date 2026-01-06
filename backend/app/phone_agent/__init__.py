"""
Phone Agent module - Shared utilities for phone automation.

This module contains shared utilities used by all agents:
- adb/: ADB operations (screenshot, input, device control)
- actions/: Action execution (ActionHandler)
- config/: Shared configuration (apps, timing, i18n)
"""

from __future__ import annotations

from typing import Any

__all__ = ["get_screenshot", "get_current_app", "ActionHandler", "parse_action", "finish"]


def __getattr__(name: str) -> Any:
    """
    Lazy exports to avoid circular imports during package initialization.
    """
    if name in ("get_screenshot", "get_current_app"):
        from app.phone_agent.adb import get_current_app, get_screenshot

        return {"get_screenshot": get_screenshot, "get_current_app": get_current_app}[name]

    if name in ("ActionHandler", "parse_action", "finish"):
        from app.phone_agent.actions import ActionHandler, finish, parse_action

        return {"ActionHandler": ActionHandler, "parse_action": parse_action, "finish": finish}[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
