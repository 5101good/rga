"""
GELab Agent Service - Based on GELab-Zero.

Features:
- Detailed THINK + explain + action + summary format
- Summary-based context management (lightweight)
- 9 action types with mapping to Phone actions
- Non-streaming output
"""

import asyncio
import time
from typing import AsyncGenerator, Callable, Optional, cast

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from app.agents.base import BaseAgentService
from app.agents.gelab.config import GELAB_MAX_STEPS, GELAB_MODEL_CONFIG
from app.agents.gelab.parser import GELabParser, denormalize_point
from app.agents.gelab.prompts import build_messages_for_model
from app.core.config import settings
from app.core.logging import get_logger
from app.models import EventType, StreamEvent
from app.phone_agent.adb import get_screenshot
from app.phone_agent.actions import ActionHandler
from app.services.agentbay import get_agentbay_service

logger = get_logger("gelab_agent")


class GELabAgentService(BaseAgentService):
    """
    GELabAgent implementation (based on GELab-Zero-4B).

    Features:
    - Detailed thinking with THINK tags
    - Summary-based context management (lightweight, only keeps last summary)
    - Non-streaming output
    - Model parameters: temp=0.1, top_p=0.95
    - 9 action types: CLICK, TYPE, SLIDE, LONGPRESS, AWAKE, COMPLETE, INFO, WAIT, ABORT
    """

    def __init__(
        self,
        device_id: str,
        on_takeover: Optional[Callable[[str], asyncio.Future]] = None,
        session_id: Optional[str] = None,
    ):
        """Initialize GELabAgentService."""
        super().__init__(device_id, on_takeover, session_id)

        # Get GELab-specific model configuration
        gelab_config = settings.gelab_config

        logger.info(f"Initialized with device_id: {device_id}")
        logger.info(f"Using model: {gelab_config['model_name']} at {gelab_config['base_url']}")

        # Initialize model client with GELab config
        self.client = OpenAI(
            base_url=gelab_config["base_url"],
            api_key=gelab_config["api_key"],
        )
        self.model_name = gelab_config["model_name"]

        # Action handler
        self.action_handler = ActionHandler(
            device_id=device_id,
            session_id=session_id,
            confirmation_callback=self._default_confirmation,
            takeover_callback=self._handle_takeover_sync,
        )

        # Parser
        self.parser = GELabParser()

        # State
        self._step_count = 0
        self._max_steps = GELAB_MAX_STEPS
        self._summary_history = ""  # Only keep last summary (lightweight context)

    def reset(self):
        """Reset agent state."""
        self._step_count = 0
        self._summary_history = ""
        self._should_stop = False

    async def run_task(
        self,
        task: str,
        system_prompt: str,  # Ignored - GELab uses its own prompts
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Execute a task with streaming output.

        Note: GELab uses its own prompt system, so system_prompt is ignored.
        """
        self.reset()
        logger.info(f"Starting task: {task[:100]}...")

        while self._step_count < self._max_steps:
            if self._should_stop:
                logger.info("Task stopped by user")
                yield StreamEvent(
                    type=EventType.COMPLETED,
                    data={"message": "任务已停止"},
                )
                return

            logger.debug(f"Executing step {self._step_count + 1}...")

            async for event in self._execute_step(task):
                yield event

                if self._should_stop:
                    logger.info("Task stopped by user")
                    yield StreamEvent(
                        type=EventType.COMPLETED,
                        data={"message": "任务已停止"},
                    )
                    return

                if event.type == EventType.COMPLETED:
                    logger.info("Task completed")
                    return

        # Max steps reached
        logger.warning(f"Max steps ({self._max_steps}) reached")
        yield StreamEvent(
            type=EventType.COMPLETED,
            data={"message": "Max steps reached"},
        )

    async def _execute_step(self, task: str) -> AsyncGenerator[StreamEvent, None]:
        """Execute a single step of the agent loop."""
        self._step_count += 1

        logger.info(f"[STEP {self._step_count}] Starting")

        if self._should_stop:
            return

        # Get screenshot
        logger.debug(f"[STEP {self._step_count}] Getting screenshot...")
        loop = asyncio.get_event_loop()
        if settings.use_agentbay_mobile and self.session_id:
            agentbay_service = get_agentbay_service()
            screenshot = await loop.run_in_executor(
                None, agentbay_service.mobile_screenshot_base64, self.session_id
            )
        else:
            screenshot = await loop.run_in_executor(None, get_screenshot, self.device_id)

        if self._should_stop:
            return

        logger.debug(f"[STEP {self._step_count}] Screenshot: {screenshot.width}x{screenshot.height}")

        # Send screenshot event
        yield StreamEvent(
            type=EventType.SCREENSHOT,
            data={
                "base64": screenshot.base64_data,
                "width": screenshot.width,
                "height": screenshot.height,
            },
        )

        # Build messages using GELab prompts
        messages = build_messages_for_model(
            task=task,
            current_image_b64=screenshot.base64_data,
            summary_history=self._summary_history,
        )

        # Call model (non-streaming for GELab)
        logger.info(f"[MODEL] Calling model: {self.model_name}")
        logger.info(f"[MODEL] Request params: max_tokens={GELAB_MODEL_CONFIG['max_tokens']}, temp={GELAB_MODEL_CONFIG['temperature']}, top_p={GELAB_MODEL_CONFIG['top_p']}")
        thinking_start_time = time.time()

        try:
            response = self.client.chat.completions.create(
                messages=cast(list[ChatCompletionMessageParam], messages),
                model=self.model_name,
                max_tokens=GELAB_MODEL_CONFIG["max_tokens"],
                temperature=GELAB_MODEL_CONFIG["temperature"],
                top_p=GELAB_MODEL_CONFIG["top_p"],
                frequency_penalty=GELAB_MODEL_CONFIG["frequency_penalty"],
                stream=False,
            )

            raw_content = response.choices[0].message.content or ""
            thinking_duration = time.time() - thinking_start_time
            logger.info(f"[MODEL] Response completed: {thinking_duration:.2f}s, {len(raw_content)} chars")
            logger.debug(f"[MODEL] Raw response (first 500 chars): {raw_content[:500]}")

        except Exception as e:
            logger.error(f"[MODEL] Model call failed: {e}", exc_info=True)
            yield StreamEvent(
                type=EventType.ERROR,
                data={"message": f"Model error: {e}"},
            )
            return

        # Parse response
        try:
            parsed_action = self.parser.str2action(raw_content)
            parsed_action = self.parser.action2action(parsed_action)
        except Exception as e:
            logger.error(f"[MODEL] Parse error: {e}", exc_info=True)
            yield StreamEvent(
                type=EventType.ERROR,
                data={"message": f"Parse error: {e}"},
            )
            return

        logger.info(f"[MODEL] Parsed action: {parsed_action.get('action')}")

        # Update summary history
        self._summary_history = parsed_action.get("summary", "")

        # Send thinking event with full content
        thinking_content = parsed_action.get("cot", "")
        explain_content = parsed_action.get("explain", "")
        full_thinking = f"{thinking_content}\n\n解释: {explain_content}" if explain_content else thinking_content

        yield StreamEvent(
            type=EventType.THINKING,
            data={
                "chunk": "",
                "full": full_thinking,
                "duration": thinking_duration,
            },
        )

        # Convert GELab action to Phone action format
        phone_action = self._convert_gelab_action_to_phone_action(
            parsed_action, screenshot.width, screenshot.height
        )

        if phone_action is None:
            yield StreamEvent(
                type=EventType.ERROR,
                data={"message": f"Unknown action type: {parsed_action.get('action')}"},
            )
            return

        # Handle special actions
        action_type = parsed_action.get("action")

        # COMPLETE action - task finished
        if action_type == "COMPLETE":
            yield StreamEvent(
                type=EventType.ACTION,
                data={"action": phone_action},
            )
            yield StreamEvent(
                type=EventType.COMPLETED,
                data={"message": parsed_action.get("return", "Task completed")},
            )
            return

        # ABORT action - task aborted
        if action_type == "ABORT":
            yield StreamEvent(
                type=EventType.ACTION,
                data={"action": phone_action},
            )
            yield StreamEvent(
                type=EventType.COMPLETED,
                data={"message": f"Task aborted: {parsed_action.get('value', 'Unknown reason')}"},
            )
            return

        # INFO action - need user input (takeover)
        if action_type == "INFO":
            yield StreamEvent(
                type=EventType.TAKEOVER,
                data={"message": parsed_action.get("value", "User intervention required")},
            )
            if self.on_takeover:
                await self.on_takeover(parsed_action.get("value", ""))
            return

        # WAIT action - special handling
        if action_type == "WAIT":
            wait_time = float(parsed_action.get("value", 1))
            yield StreamEvent(
                type=EventType.ACTION,
                data={"action": phone_action},
            )
            await asyncio.sleep(wait_time)
            return

        # Execute normal action
        logger.info(f"[ACTION] Executing: {phone_action.get('action')}")
        action_start_time = time.time()

        result = await loop.run_in_executor(
            None,
            self.action_handler.execute,
            phone_action,
            screenshot.width,
            screenshot.height,
        )

        action_duration = time.time() - action_start_time
        logger.info(f"[ACTION] Result: success={result.success}, duration={action_duration:.3f}s")

        # Send action event
        yield StreamEvent(
            type=EventType.ACTION,
            data={
                "action": phone_action,
                "duration": action_duration,
            },
        )

        if result.should_finish:
            yield StreamEvent(
                type=EventType.COMPLETED,
                data={"message": result.message or "Task completed"},
            )

    def _convert_gelab_action_to_phone_action(
        self, gelab_action: dict, width: int, height: int
    ) -> Optional[dict]:
        """
        Convert GELab action format to Phone action format.

        GELab actions use 0-1000 normalized coordinates, which the Phone
        action handler also expects (it converts internally).

        Mapping:
        - CLICK -> Tap (element)
        - TYPE -> Type (text)
        - SLIDE -> Swipe (start, end)
        - LONGPRESS -> Long Press (element)
        - AWAKE -> Launch (app)
        - COMPLETE -> finish (message)
        - INFO -> Take_over (message)
        - WAIT -> Wait (duration)
        - ABORT -> finish with error message
        """
        action_type = gelab_action.get("action")

        if action_type == "CLICK":
            point = gelab_action.get("point", [500, 500])
            return {
                "_metadata": "do",
                "action": "Tap",
                "element": point,  # Already in 0-1000 format
            }

        elif action_type == "TYPE":
            text = gelab_action.get("value", "")
            return {
                "_metadata": "do",
                "action": "Type",
                "text": text,
            }

        elif action_type == "SLIDE":
            point1 = gelab_action.get("point1", [500, 700])
            point2 = gelab_action.get("point2", [500, 300])
            return {
                "_metadata": "do",
                "action": "Swipe",
                "start": point1,
                "end": point2,
            }

        elif action_type == "LONGPRESS":
            point = gelab_action.get("point", [500, 500])
            return {
                "_metadata": "do",
                "action": "Long Press",
                "element": point,
            }

        elif action_type == "AWAKE":
            app_name = gelab_action.get("value", "")
            return {
                "_metadata": "do",
                "action": "Launch",
                "app": app_name,
            }

        elif action_type == "COMPLETE":
            return_value = gelab_action.get("return", "Task completed")
            return {
                "_metadata": "finish",
                "message": return_value,
            }

        elif action_type == "INFO":
            message = gelab_action.get("value", "User intervention required")
            return {
                "_metadata": "do",
                "action": "Take_over",
                "message": message,
            }

        elif action_type == "WAIT":
            duration = gelab_action.get("value", "1")
            return {
                "_metadata": "do",
                "action": "Wait",
                "duration": f"{duration} seconds",
            }

        elif action_type == "ABORT":
            reason = gelab_action.get("value", "Task aborted")
            return {
                "_metadata": "finish",
                "message": f"Aborted: {reason}",
            }

        else:
            logger.warning(f"Unknown action type: {action_type}")
            return None

    @property
    def agent_type(self) -> str:
        """Return agent type identifier."""
        return "gelab"

    @property
    def default_max_steps(self) -> int:
        """Return default maximum steps."""
        return GELAB_MAX_STEPS

    @staticmethod
    def _default_confirmation(message: str) -> bool:
        """Default confirmation - auto approve for web interface."""
        logger.debug(f"Auto-approved: {message}")
        return True

    def _handle_takeover_sync(self, message: str) -> None:
        """Sync takeover handler."""
        logger.info(f"Takeover requested: {message}")
