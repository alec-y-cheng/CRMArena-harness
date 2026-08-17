"""Action-selection interfaces for the generic workflow runtime."""

from typing import Any, Callable, Dict, List, Optional

from ewm.ir.environment import ReachableInfo
from ewm.ir.frame import InstanceFrame
from ewm.ir.base import Serializable
from ewm.ir.state import Claim, ExecutionState
from ewm.mcp.client import MCPCall, MCPToolSchema


class WorkflowDecision(Serializable):
    """Controller proposal for the next workflow step.

    `decision_type` is intentionally small and structural. Natural-language
    status/reason labels can vary, but the driver needs to know whether the
    controller is proposing an environment action, a user-facing action, or a
    terminal completion candidate.
    """

    def __init__(
        self,
        decision_type: str,
        backend_action: Optional[MCPCall] = None,
        frontend_message: Optional[str] = None,
        candidate_outcome: Any = None,
        candidate_response: Optional[str] = None,
        state_updates: Optional[Dict[str, Any]] = None,
        claims: Optional[List[Claim]] = None,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.decision_type = decision_type
        self.backend_action = backend_action
        self.frontend_message = frontend_message
        self.candidate_outcome = candidate_outcome
        self.candidate_response = candidate_response
        self.state_updates = state_updates or {}
        self.claims = claims or []
        self.reason = reason
        self.metadata = metadata or {}


DecisionSelector = Callable[
    [InstanceFrame, ExecutionState, List[ReachableInfo], List[MCPToolSchema]],
    WorkflowDecision,
]


def select_workflow_decision(
    frame: InstanceFrame,
    state: ExecutionState,
    reachable: List[ReachableInfo],
    tools: List[MCPToolSchema],
) -> WorkflowDecision:
    """Default controller hook.

    The generic driver is intentionally not task-specific. A production caller
    should inject an LLM-backed selector that reads the frame, state,
    reachability view, and MCP tool menu, then returns one of:
    `backend_action`, `frontend_action`, or `complete`.
    """

    raise NotImplementedError("Inject an LLM-backed DecisionSelector before running the workflow driver.")
