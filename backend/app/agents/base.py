"""
Base Agent Service - Abstract interface for all agents.

This module defines the abstract base class that all agent implementations must inherit.
It ensures a unified interface for:
1. Consistent input/output format (StreamEvent)
2. Unified lifecycle management
3. Pluggable agent strategies
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Callable, Optional
import asyncio

from app.models import StreamEvent


class BaseAgentService(ABC):
    """
    Abstract base class for all Agent services.

    All agents must implement this interface to ensure:
    1. Unified StreamEvent output format
    2. Consistent lifecycle management
    3. Pluggable agent strategies
    """

    def __init__(
        self,
        device_id: str,
        on_takeover: Optional[Callable[[str], asyncio.Future]] = None,
        session_id: Optional[str] = None,
    ):
        """
        Initialize the agent service.

        Args:
            device_id: The AgentBay device ID to control
            on_takeover: Optional callback when human takeover is needed
            session_id: The AgentBay session ID for accessing native APIs
        """
        self.device_id = device_id
        self.session_id = session_id
        self.on_takeover = on_takeover
        self._should_stop = False

    @abstractmethod
    def run_task(
        self,
        task: str,
        system_prompt: str,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Execute a task with streaming output.

        Args:
            task: User task description
            system_prompt: System prompt for the model (may be ignored by some agents)

        Yields:
            StreamEvent: Stream events (thinking, action, screenshot, etc.)
        """
        pass

    @abstractmethod
    def reset(self):
        """Reset agent state for a new task."""
        pass

    def stop(self):
        """Stop the current task execution."""
        self._should_stop = True

    @property
    @abstractmethod
    def agent_type(self) -> str:
        """Return the agent type identifier."""
        pass

    @property
    @abstractmethod
    def default_max_steps(self) -> int:
        """Return the default maximum number of steps."""
        pass
