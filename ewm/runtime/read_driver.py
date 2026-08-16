"""Skeleton read driver for the generic EWM runtime."""

from typing import Any, Dict, List

from ewm.ir.environment import EnvironmentIR, reachable_information
from ewm.ir.frame import infer_instance_frame
from ewm.ir.state import ExecutionState
from ewm.mcp.salesforce_reads import execute_mcp_call
from ewm.mcp.normalizer import normalize_observation, to_observation

from .action_selector import select_mcp_read_action
from .completion import evaluate_completion
from .renderer import render_response
from .verifier import validate_mcp_call


class ReadDriver:
    """Generic read loop scaffold.

    This is intentionally incomplete. It shows the common control flow without
    implementing task-specific policies or benchmark workflows.
    """

    def __init__(self, mcp_client: Any, env_ir: EnvironmentIR) -> None:
        self.mcp_client = mcp_client
        self.env_ir = env_ir

    def initialize_state(self, messages: List[Dict[str, Any]], env_summary: Dict[str, Any]) -> ExecutionState:
        frame = infer_instance_frame(messages, env_summary)
        return ExecutionState(frame=frame)

    def step(self, state: ExecutionState) -> ExecutionState:
        tools = self.mcp_client.list_tools()
        reachable = reachable_information(state, self.env_ir)
        call = select_mcp_read_action(state.frame, state, reachable, tools)
        tool_schema = next((tool for tool in tools if tool.name == call.name), None)
        if tool_schema is None:
            state.actions["failed"].append({"call": call.to_dict(), "reason": "unknown tool"})
            return state
        validation = validate_mcp_call(call, state, self.env_ir, tool_schema)
        if not validation.valid:
            state.actions["failed"].append({"call": call.to_dict(), "reason": validation.reason})
            return state
        observation = execute_mcp_call(self.mcp_client, call)
        state.add_observation(to_observation(call, observation))
        for evidence in normalize_observation(call, observation):
            state.add_evidence(evidence)
        state.completion_state = evaluate_completion(state.frame, state)
        return state

    def render(self, state: ExecutionState) -> str:
        return render_response(state.frame, state, state.completion_state)

