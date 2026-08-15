"""Generic symbolic runtime harness skeleton."""

from typing import Dict, List, Optional

from dsl.general_runtime.executor import RuntimeExecutor
from dsl.general_runtime.planner import RuntimePlanner
from dsl.general_runtime.renderer import render_final_response
from dsl.general_runtime.state import ExecutionState
from dsl.general_runtime.verifier import compute_enabled_actions, validate_instance_frame
from dsl.general_runtime.workflow_specs import load_workflow_spec


class GeneralRuntimeHarness:
    def __init__(self, workflow_id: str, planner: RuntimePlanner, executor: Optional[RuntimeExecutor] = None):
        self.workflow_spec = load_workflow_spec(workflow_id)
        self.planner = planner
        self.executor = executor or RuntimeExecutor()

    def initialize_state(self, conversation_history: List[Dict[str, str]]) -> ExecutionState:
        return ExecutionState(self.workflow_spec, conversation_history=conversation_history)

    def frame_instance(self, state: ExecutionState, conversation_text: str) -> ExecutionState:
        frame = self.planner.populate_instance_frame(self.workflow_spec, conversation_text)
        validate_instance_frame(frame, self.workflow_spec)
        state.instance_frame = frame
        state.current_phase = "compute_enabled_actions"
        state.model_calls += 1
        return state

    def step(self, state: ExecutionState) -> ExecutionState:
        enabled = compute_enabled_actions(state)
        if not enabled:
            state.completion_state = "blocked_no_enabled_actions"
            return state
        if len(enabled) == 1:
            state.current_phase = "awaiting_deterministic_action_args"
            return state
        selection = self.planner.select_action(state)
        self.executor.execute(state, selection)
        state.model_calls += 1
        state.current_phase = "update_execution_state"
        return state

    def render(self, state: ExecutionState) -> str:
        return render_final_response(state)
