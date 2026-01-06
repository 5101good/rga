"""Business logic services."""

from __future__ import annotations

from typing import Any

from .database import DatabaseService, get_database_service

__all__ = ["AgentBayService", "DatabaseService", "get_database_service"]


def __getattr__(name: str) -> Any:
    """
    Lazy exports to avoid circular imports during package initialization.
    """
    if name == "AgentBayService":
        from .agentbay import AgentBayService

        return AgentBayService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
