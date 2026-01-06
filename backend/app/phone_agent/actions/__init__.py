"""Actions module for handling AI model outputs."""

from __future__ import annotations

from typing import Any

__all__ = ["ActionHandler", "ActionResult", "parse_action", "do", "finish"]


def __getattr__(name: str) -> Any:
    """
    Lazy exports to avoid circular imports during package initialization.
    """
    if name in __all__:
        from app.phone_agent.actions.handler import (
            ActionHandler,
            ActionResult,
            do,
            finish,
            parse_action,
        )

        return {
            "ActionHandler": ActionHandler,
            "ActionResult": ActionResult,
            "parse_action": parse_action,
            "do": do,
            "finish": finish,
        }[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

