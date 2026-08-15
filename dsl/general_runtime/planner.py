"""LLM-facing planner skeleton for the generic runtime."""

from typing import Any, Callable, Dict, List

from dsl.general_runtime.parser import parse_action_selection_json, parse_instance_frame_json
from dsl.general_runtime.prompts import ACTION_SELECTION_SYSTEM_PROMPT, INSTANCE_FRAME_SYSTEM_PROMPT, build_action_selection_prompt, build_instance_frame_prompt
from dsl.general_runtime.state import ExecutionState, InstanceFrame, WorkflowSpec

Message = Dict[str, str]
CompletionFn = Callable[[List[Message]], str]


class RuntimePlanner:
    """Thin wrapper around generic runtime LLM calls."""

    def __init__(self, completion_fn: CompletionFn):
        self.completion_fn = completion_fn

    def populate_instance_frame(self, spec: WorkflowSpec, conversation_text: str) -> InstanceFrame:
        output = self.completion_fn([
            {"role": "system", "content": INSTANCE_FRAME_SYSTEM_PROMPT},
            {"role": "user", "content": build_instance_frame_prompt(spec, conversation_text)},
        ])
        return parse_instance_frame_json(output)

    def select_action(self, state: ExecutionState) -> Dict[str, Any]:
        output = self.completion_fn([
            {"role": "system", "content": ACTION_SELECTION_SYSTEM_PROMPT},
            {"role": "user", "content": build_action_selection_prompt(state)},
        ])
        return parse_action_selection_json(output)
