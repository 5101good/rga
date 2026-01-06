"""Action handler for processing AI model outputs."""

import ast
import time
from dataclasses import dataclass
from typing import Any, Callable

from app.core.config import settings
from app.core.logging import get_logger
from app.phone_agent.adb import (
    back,
    double_tap,
    home,
    launch_app,
    long_press,
    swipe,
    tap,
)
from app.services.agentbay import get_agentbay_service

logger = get_logger("action_handler")


@dataclass
class ActionResult:
    """Result of an action execution."""
    success: bool
    should_finish: bool
    message: str | None = None
    requires_confirmation: bool = False


class ActionHandler:
    """Handles execution of actions from AI model output."""

    def __init__(
        self,
        device_id: str | None = None,
        session_id: str | None = None,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
    ):
        self.device_id = device_id
        self.session_id = session_id
        self.confirmation_callback = confirmation_callback or self._default_confirmation
        self.takeover_callback = takeover_callback or self._default_takeover

    def execute(
        self, action: dict[str, Any], screen_width: int, screen_height: int
    ) -> ActionResult:
        """Execute an action from the AI model."""
        import time
        start_time = time.time()

        action_type = action.get("_metadata")

        if action_type == "finish":
            logger.info(f"[ACTION] Finish: {action.get('message', 'No message')[:100]}")
            return ActionResult(
                success=True, should_finish=True, message=action.get("message")
            )

        if action_type != "do":
            logger.warning(f"[ACTION] Unknown action type: {action_type}")
            return ActionResult(
                success=False,
                should_finish=True,
                message=f"Unknown action type: {action_type}",
            )

        action_name = action.get("action") or ""
        handler_method = self._get_handler(action_name)

        if handler_method is None:
            logger.warning(f"[ACTION] Unknown action: {action_name}")
            return ActionResult(
                success=False,
                should_finish=False,
                message=f"Unknown action: {action_name}",
            )

        # Log action details
        action_details = {k: v for k, v in action.items() if k not in ["_metadata", "action"]}
        logger.info(f"[ACTION] Executing: {action_name} params={action_details}")

        try:
            result = handler_method(action, screen_width, screen_height)
            duration = time.time() - start_time
            logger.info(f"[ACTION] {action_name} completed: success={result.success}, duration={duration:.3f}s")
            if not result.success and result.message:
                logger.warning(f"[ACTION] {action_name} failed: {result.message}")
            return result
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"[ACTION] {action_name} exception after {duration:.3f}s: {e}", exc_info=True)
            return ActionResult(
                success=False, should_finish=False, message=f"Action failed: {e}"
            )

    def _get_handler(self, action_name: str) -> Callable | None:
        """Get the handler method for an action."""
        handlers = {
            "Launch": self._handle_launch,
            "Tap": self._handle_tap,
            "Type": self._handle_type,
            "Type_Name": self._handle_type,
            "Swipe": self._handle_swipe,
            "Back": self._handle_back,
            "Home": self._handle_home,
            "Double Tap": self._handle_double_tap,
            "Long Press": self._handle_long_press,
            "Wait": self._handle_wait,
            "Take_over": self._handle_takeover,
            "Note": self._handle_note,
            "Call_API": self._handle_call_api,
            "Interact": self._handle_interact,
        }
        return handlers.get(action_name)

    def _convert_relative_to_absolute(
        self, element: list[int], screen_width: int, screen_height: int
    ) -> tuple[int, int]:
        """Convert relative coordinates (0-1000) to absolute pixels."""
        x = int(element[0] / 1000 * screen_width)
        y = int(element[1] / 1000 * screen_height)
        return x, y

    def _handle_launch(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle app launch action."""
        app_name = action.get("app")
        if not app_name:
            return ActionResult(False, False, "No app name specified")

        if settings.use_agentbay_mobile and self.session_id:
            agentbay_service = get_agentbay_service()
            ok, err = agentbay_service.mobile_start_app(self.session_id, app_name)
            if ok:
                return ActionResult(True, False)
            logger.warning(f"[SDK] Launch failed, fallback to ADB: {err}")
            if not self.device_id:
                return ActionResult(False, False, f"Launch failed (no ADB fallback): {err}")

        success = launch_app(app_name, self.device_id)
        if success:
            return ActionResult(True, False)
        return ActionResult(False, False, f"App not found: {app_name}")

    def _handle_tap(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle tap action."""
        element = action.get("element")
        if not element:
            return ActionResult(False, False, "No element coordinates")

        x, y = self._convert_relative_to_absolute(element, width, height)

        if "message" in action:
            if not self.confirmation_callback(action["message"]):
                return ActionResult(
                    success=False,
                    should_finish=True,
                    message="User cancelled sensitive operation",
                )

        if settings.use_agentbay_mobile and self.session_id:
            agentbay_service = get_agentbay_service()
            ok, err = agentbay_service.mobile_tap(self.session_id, x, y)
            if not ok:
                logger.warning(f"[SDK] Tap failed, fallback to ADB: {err}")
                if self.device_id:
                    tap(x, y, self.device_id)
                else:
                    return ActionResult(False, False, f"Tap failed (no ADB fallback): {err}")
        else:
            tap(x, y, self.device_id)
        return ActionResult(True, False)

    def _handle_type(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle text input action using AgentBay native input."""
        text = action.get("text", "")
        logger.info(f"[ADB] Type text: '{text[:50]}{'...' if len(text) > 50 else ''}'")

        if not self.session_id:
            logger.warning("[SDK] Type failed: session_id is missing")
            return ActionResult(False, False, "Session not found")

        agentbay_service = get_agentbay_service()
        ok, err = agentbay_service.mobile_input_text(self.session_id, text)
        if not ok:
            logger.warning(f"[SDK] Type failed: {err}")
            return ActionResult(False, False, f"Input failed: {err}")
        return ActionResult(True, False)

    def _handle_swipe(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle swipe action."""
        start = action.get("start")
        end = action.get("end")

        if not start or not end:
            return ActionResult(False, False, "Missing swipe coordinates")

        start_x, start_y = self._convert_relative_to_absolute(start, width, height)
        end_x, end_y = self._convert_relative_to_absolute(end, width, height)

        if settings.use_agentbay_mobile and self.session_id:
            agentbay_service = get_agentbay_service()
            ok, err = agentbay_service.mobile_swipe(
                self.session_id, start_x, start_y, end_x, end_y
            )
            if not ok:
                logger.warning(f"[SDK] Swipe failed, fallback to ADB: {err}")
                if self.device_id:
                    swipe(start_x, start_y, end_x, end_y, device_id=self.device_id)
                else:
                    return ActionResult(False, False, f"Swipe failed (no ADB fallback): {err}")
        else:
            swipe(start_x, start_y, end_x, end_y, device_id=self.device_id)
        return ActionResult(True, False)

    def _handle_back(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle back button action."""
        if settings.use_agentbay_mobile and self.session_id:
            agentbay_service = get_agentbay_service()
            ok, err = agentbay_service.mobile_send_key(self.session_id, 4)
            if not ok:
                logger.warning(f"[SDK] Back failed, fallback to ADB: {err}")
                if self.device_id:
                    back(self.device_id)
                else:
                    return ActionResult(False, False, f"Back failed (no ADB fallback): {err}")
        else:
            back(self.device_id)
        return ActionResult(True, False)

    def _handle_home(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle home button action."""
        if settings.use_agentbay_mobile and self.session_id:
            agentbay_service = get_agentbay_service()
            ok, err = agentbay_service.mobile_send_key(self.session_id, 3)
            if not ok:
                logger.warning(f"[SDK] Home failed, fallback to ADB: {err}")
                if self.device_id:
                    home(self.device_id)
                else:
                    return ActionResult(False, False, f"Home failed (no ADB fallback): {err}")
        else:
            home(self.device_id)
        return ActionResult(True, False)

    def _handle_double_tap(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle double tap action."""
        element = action.get("element")
        if not element:
            return ActionResult(False, False, "No element coordinates")

        x, y = self._convert_relative_to_absolute(element, width, height)
        if settings.use_agentbay_mobile and self.session_id:
            agentbay_service = get_agentbay_service()
            ok, err = agentbay_service.mobile_double_tap(self.session_id, x, y)
            if not ok:
                logger.warning(f"[SDK] Double tap failed, fallback to ADB: {err}")
                if self.device_id:
                    double_tap(x, y, self.device_id)
                else:
                    return ActionResult(False, False, f"Double tap failed (no ADB fallback): {err}")
        else:
            double_tap(x, y, self.device_id)
        return ActionResult(True, False)

    def _handle_long_press(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle long press action."""
        element = action.get("element")
        if not element:
            return ActionResult(False, False, "No element coordinates")

        x, y = self._convert_relative_to_absolute(element, width, height)
        if settings.use_agentbay_mobile and self.session_id:
            agentbay_service = get_agentbay_service()
            ok, err = agentbay_service.mobile_long_press(self.session_id, x, y)
            if not ok:
                logger.warning(f"[SDK] Long press failed, fallback to ADB: {err}")
                if self.device_id:
                    long_press(x, y, device_id=self.device_id)
                else:
                    return ActionResult(False, False, f"Long press failed (no ADB fallback): {err}")
        else:
            long_press(x, y, device_id=self.device_id)
        return ActionResult(True, False)

    def _handle_wait(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle wait action."""
        duration_str = action.get("duration", "1 seconds")
        try:
            duration = float(duration_str.replace("seconds", "").strip())
        except ValueError:
            duration = 1.0

        time.sleep(duration)
        return ActionResult(True, False)

    def _handle_takeover(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle takeover request."""
        message = action.get("message", "User intervention required")
        self.takeover_callback(message)
        return ActionResult(True, False)

    def _handle_note(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle note action."""
        return ActionResult(True, False)

    def _handle_call_api(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle API call action."""
        return ActionResult(True, False)

    def _handle_interact(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle interaction request."""
        return ActionResult(True, False, message="User interaction required")

    @staticmethod
    def _default_confirmation(message: str) -> bool:
        """Default confirmation callback."""
        response = input(f"Sensitive operation: {message}\nConfirm? (Y/N): ")
        return response.upper() == "Y"

    @staticmethod
    def _default_takeover(message: str) -> None:
        """Default takeover callback."""
        input(f"{message}\nPress Enter after completing manual operation...")


def parse_action(response: str) -> dict[str, Any]:
    """Parse action from model response."""
    try:
        response = response.strip()
        if response.startswith('do(action="Type"') or response.startswith(
            'do(action="Type_Name"'
        ):
            text = response.split("text=", 1)[1][1:-2]
            action = {"_metadata": "do", "action": "Type", "text": text}
            return action
        elif response.startswith("do"):
            try:
                tree = ast.parse(response, mode="eval")
                if not isinstance(tree.body, ast.Call):
                    raise ValueError("Expected a function call")

                call = tree.body
                action = {"_metadata": "do"}
                for keyword in call.keywords:
                    key = keyword.arg
                    if key is None:
                        # Skip **kwargs or unsupported syntax
                        continue
                    value = ast.literal_eval(keyword.value)
                    action[key] = value

                return action
            except (SyntaxError, ValueError) as e:
                raise ValueError(f"Failed to parse do() action: {e}")

        elif response.startswith("finish"):
            action = {
                "_metadata": "finish",
                "message": response.replace("finish(message=", "")[1:-2],
            }
        else:
            raise ValueError(f"Failed to parse action: {response}")
        return action
    except Exception as e:
        raise ValueError(f"Failed to parse action: {e}")


def do(**kwargs) -> dict[str, Any]:
    """Helper function for creating 'do' actions."""
    kwargs["_metadata"] = "do"
    return kwargs


def finish(**kwargs) -> dict[str, Any]:
    """Helper function for creating 'finish' actions."""
    kwargs["_metadata"] = "finish"
    return kwargs

