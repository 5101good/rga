"""
GLMAgent Service - Based on GLM models with streaming support.

Features:
- Streaming thinking output
- Full context management (complete conversation history)
- XML-style output format: <think>...</think><answer>do(action=...)</answer>
- Model parameters: temp=0.0, top_p=0.85
"""

import asyncio
import time
from typing import Any, AsyncGenerator, Callable, Optional, cast

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from app.agents.base import BaseAgentService
from app.agents.glm.model import MessageBuilder
from app.agents.glm.prompts import get_system_prompt
from app.core.config import settings
from app.core.logging import get_logger
from app.models import EventType, StreamEvent
from app.phone_agent.adb import get_screenshot
from app.phone_agent.actions import ActionHandler, parse_action, finish
from app.services.agentbay import get_agentbay_service

logger = get_logger("glm_agent")


class GLMAgentService(BaseAgentService):
    """
    GLMAgent implementation (based on GLM models).

    Features:
    - Streaming thinking output with real-time chunks
    - Full context management (keeps complete conversation history)
    - XML-style output format
    - Model parameters: temp=0.0, top_p=0.85, freq_penalty=0.2
    """

    def __init__(
        self,
        device_id: str,
        on_takeover: Optional[Callable[[str], asyncio.Future]] = None,
        session_id: Optional[str] = None,
    ):
        """Initialize GLMAgentService."""
        super().__init__(device_id, on_takeover, session_id)

        # Get GLM-specific model configuration
        glm_config = settings.glm_config

        logger.info(f"Initialized with device_id: {device_id}")
        logger.info(f"Using model: {glm_config['model_name']} at {glm_config['base_url']}")

        # Initialize model client with GLM config
        self.client = OpenAI(
            base_url=glm_config["base_url"],
            api_key=glm_config["api_key"],
        )
        self.model_name = glm_config["model_name"]

        # Action handler
        self.action_handler = ActionHandler(
            device_id=device_id,
            session_id=session_id,
            confirmation_callback=self._default_confirmation,
            takeover_callback=self._handle_takeover_sync,
        )

        # Context for multi-turn conversation
        self._context: list[dict[str, Any]] = []
        self._step_count = 0
        self._max_steps = 60

    def reset(self):
        """Reset agent state."""
        self._context = []
        self._step_count = 0
        self._should_stop = False

    def stop(self):
        """Stop the current task execution."""
        logger.info("Stop requested")
        self._should_stop = True

    async def run_task(
        self,
        task: str,
        system_prompt: str,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Run a task with streaming output.

        Args:
            task: Task description
            system_prompt: System prompt for the model

        Yields:
            StreamEvent objects for thinking, actions, screenshots, etc.
        """
        self.reset()

        logger.info(f"Starting task: {task[:100]}...")

        # Add system message
        self._context.append({
            "role": "system",
            "content": system_prompt,
        })

        # First step
        logger.debug("Executing first step...")
        async for event in self._execute_step(task, is_first=True):
            yield event

            if self._should_stop:
                logger.info("Task stopped by user")
                yield StreamEvent(
                    type=EventType.COMPLETED,
                    data={"message": "任务已停止"},
                )
                return

            if event.type == EventType.COMPLETED:
                logger.info("Task completed on first step")
                return

        # Continue until finished or max steps
        while self._step_count < self._max_steps:
            if self._should_stop:
                logger.info("Task stopped by user")
                yield StreamEvent(
                    type=EventType.COMPLETED,
                    data={"message": "任务已停止"},
                )
                return

            logger.debug(f"Executing step {self._step_count + 1}...")
            async for event in self._execute_step(is_first=False):
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

    async def _execute_step(
        self,
        user_prompt: Optional[str] = None,
        is_first: bool = False,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Execute a single step of the agent loop."""
        self._step_count += 1
        step_start_time = time.time()

        logger.info(f"[STEP {self._step_count}] Starting {'(first step)' if is_first else ''}")

        if self._should_stop:
            logger.debug("Stop flag detected, skipping step")
            return

        # Get screenshot from device
        logger.debug(f"[STEP {self._step_count}] Getting screenshot...")
        loop = asyncio.get_event_loop()
        if settings.use_agentbay_mobile and self.session_id:
            agentbay_service = get_agentbay_service()
            screenshot = await loop.run_in_executor(
                None, agentbay_service.mobile_screenshot_base64, self.session_id
            )
        else:
            screenshot = await loop.run_in_executor(None, get_screenshot, self.device_id)
        current_app: str | None = None
        if settings.phone_agent_include_current_app:
            # Lazy import to avoid hard ADB dependency when disabled
            from app.phone_agent.adb import get_current_app  # type: ignore

            current_app = await loop.run_in_executor(None, get_current_app, self.device_id)

        if self._should_stop:
            logger.debug("Stop flag detected after screenshot")
            return

        logger.debug(
            f"[STEP {self._step_count}] Screenshot: {screenshot.width}x{screenshot.height}"
            + (f", app={current_app}" if current_app else "")
        )

        # Send screenshot event
        yield StreamEvent(
            type=EventType.SCREENSHOT,
            data={
                "base64": screenshot.base64_data,
                "width": screenshot.width,
                "height": screenshot.height,
            },
        )

        # Build messages
        if is_first:
            screen_info = MessageBuilder.build_screen_info(current_app)
            text_content = f"{user_prompt}\n\n{screen_info}"

            self._context.append(
                MessageBuilder.create_user_message(
                    text=text_content, image_base64=screenshot.base64_data
                )
            )
        else:
            screen_info = MessageBuilder.build_screen_info(current_app)
            text_content = f"** Screen Info **\n\n{screen_info}"

            self._context.append(
                MessageBuilder.create_user_message(
                    text=text_content, image_base64=screenshot.base64_data
                )
            )

        # Stream model response
        logger.info(f"[MODEL] Calling model: {self.model_name}")
        logger.info(f"[MODEL] Request params: max_tokens=3000, temp=0.0, top_p=0.85, freq_penalty=0.2")
        logger.debug(f"[MODEL] Context messages: {len(self._context)}")

        thinking_start_time = time.time()
        raw_content = ""
        thinking_buffer = ""
        in_action_phase = False
        action_markers = ["finish(message=", "do(action="]
        token_count = 0

        try:
            stream = self.client.chat.completions.create(
                messages=cast(list[ChatCompletionMessageParam], self._context),
                model=self.model_name,
                max_tokens=3000,
                temperature=0.0,
                top_p=0.85,
                frequency_penalty=0.2,
                stream=True,
            )

            for chunk in stream:
                token_count += 1
                if self._should_stop:
                    logger.debug("Stop flag detected during streaming")
                    stream.close()
                    return

                if len(chunk.choices) == 0:
                    continue
                if chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    raw_content += content

                    if not in_action_phase:
                        thinking_buffer += content

                        # Check if we hit an action marker
                        for marker in action_markers:
                            if marker in thinking_buffer:
                                thinking_part = thinking_buffer.split(marker, 1)[0]
                                in_action_phase = True
                                thinking_duration = time.time() - thinking_start_time
                                logger.debug(f"Thinking duration: {thinking_duration:.3f}s")

                                # Send complete thinking with duration
                                yield StreamEvent(
                                    type=EventType.THINKING,
                                    data={
                                        "chunk": "",
                                        "full": thinking_part.replace("<think>", "").replace("</think>", "").strip(),
                                        "duration": thinking_duration,
                                    },
                                )
                                break

                        if not in_action_phase:
                            # Stream thinking chunks
                            yield StreamEvent(
                                type=EventType.THINKING,
                                data={
                                    "chunk": content,
                                    "full": thinking_buffer.replace("<think>", "").replace("</think>", "").strip(),
                                },
                            )

        except Exception as e:
            logger.error(f"[MODEL] Model call failed: {e}", exc_info=True)
            yield StreamEvent(
                type=EventType.ERROR,
                data={"message": f"Model error: {e}"},
            )
            return

        # Log model response stats
        model_duration = time.time() - thinking_start_time
        logger.info(f"[MODEL] Response completed: {token_count} chunks, {model_duration:.2f}s, {len(raw_content)} chars")
        logger.debug(f"[MODEL] Raw response (first 500 chars): {raw_content[:500]}")

        # Parse response
        thinking, action_str = self._parse_response(raw_content)
        logger.info(f"[MODEL] Parsed action: {action_str[:100]}{'...' if len(action_str) > 100 else ''}")

        # Parse action
        try:
            action = parse_action(action_str)
        except ValueError:
            action = finish(message=action_str)

        logger.debug(f"Action: {action}")

        # Remove images from context to save space
        self._context[-1] = MessageBuilder.remove_images_from_message(self._context[-1])

        # Execute action
        logger.info(f"[ACTION] Executing: {action.get('action') or action.get('_metadata')}")
        action_start_time = time.time()
        result = await loop.run_in_executor(
            None,
            self.action_handler.execute,
            action,
            screenshot.width,
            screenshot.height,
        )
        action_duration = time.time() - action_start_time
        step_duration = time.time() - step_start_time
        logger.info(f"[STEP {self._step_count}] Completed: action={action.get('action') or action.get('_metadata')}, success={result.success}, step_duration={step_duration:.2f}s")

        # Send action event
        yield StreamEvent(
            type=EventType.ACTION,
            data={
                "action": action,
                "duration": action_duration,
            },
        )

        # Add assistant response to context
        self._context.append(
            MessageBuilder.create_assistant_message(
                f"<think>{thinking}</think><answer>{action_str}</answer>"
            )
        )

        # Handle takeover
        if action.get("action") == "Take_over":
            yield StreamEvent(
                type=EventType.TAKEOVER,
                data={"message": action.get("message", "User intervention required")},
            )

            if self.on_takeover:
                await self.on_takeover(action.get("message", ""))

        # Check if finished
        if result.should_finish or action.get("_metadata") == "finish":
            yield StreamEvent(
                type=EventType.COMPLETED,
                data={"message": result.message or action.get("message", "Task completed")},
            )

    def _parse_response(self, content: str) -> tuple[str, str]:
        """Parse the model response into thinking and action parts."""
        # Rule 1: Check for finish(message=
        if "finish(message=" in content:
            parts = content.split("finish(message=", 1)
            thinking = parts[0].strip()
            action = "finish(message=" + parts[1]
            return thinking, action

        # Rule 2: Check for do(action=
        if "do(action=" in content:
            parts = content.split("do(action=", 1)
            thinking = parts[0].strip()
            action = "do(action=" + parts[1]
            return thinking, action

        # Rule 3: Fallback to legacy XML tag parsing
        if "<answer>" in content:
            parts = content.split("<answer>", 1)
            thinking = parts[0].replace("<think>", "").replace("</think>", "").strip()
            action = parts[1].replace("</answer>", "").strip()
            return thinking, action

        # Rule 4: No markers found
        return "", content

    @property
    def agent_type(self) -> str:
        """Return agent type identifier."""
        return "glm"

    @property
    def default_max_steps(self) -> int:
        """Return default maximum steps."""
        return 60

    @staticmethod
    def _default_confirmation(message: str) -> bool:
        """Default confirmation - auto approve for web interface."""
        logger.debug(f"Auto-approved: {message}")
        return True

    def _handle_takeover_sync(self, message: str) -> None:
        """Sync takeover handler."""
        logger.info(f"Takeover requested: {message}")
