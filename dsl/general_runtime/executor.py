"""Deterministic executor skeleton for verified generic-runtime actions."""

from typing import Any, Callable, Dict, Mapping

from dsl.general_runtime.state import ExecutionState
from dsl.general_runtime.verifier import compute_enabled_actions, validate_action_selection

ActionHandler = Callable[[ExecutionState, Mapping[str, Any]], None]


class RuntimeExecutor:
    def __init__(self):
        self.handlers: Dict[str, ActionHandler] = {}

    def register(self, action: str, handler: ActionHandler) -> None:
        self.handlers[action] = handler

    def execute(self, state: ExecutionState, selection: Mapping[str, Any]) -> None:
        validate_action_selection(selection, state)
        action = str(selection["action"])
        handler = self.handlers.get(action)
        if handler is None:
            raise NotImplementedError("No executor handler registered for action: {}".format(action))
        handler(state, selection.get("arguments", {}))
        state.executed_actions.append(dict(selection))


def execute_driver_action(executor: RuntimeExecutor, state: ExecutionState, action: str, arguments: Mapping[str, Any]) -> None:
    """Execute a driver-selected action while the generic predicate set matures."""
    compute_enabled_actions(state)
    if action not in [item.action for item in state.enabled_actions]:
        handler = executor.handlers.get(action)
        if handler is None:
            raise RuntimeError("No handler for action: {}".format(action))
        handler(state, arguments)
        state.executed_actions.append(
            {
                "action": action,
                "arguments": dict(arguments),
                "reason": "driver-selected workflow action",
            }
        )
        return
    executor.execute(
        state,
        {
            "action": action,
            "arguments": dict(arguments),
            "reason": "driver-selected workflow action",
        },
    )
