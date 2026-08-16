"""Action-selection interfaces for the generic read runtime."""

from typing import List

from ewm.ir.environment import ReachableInfo
from ewm.ir.frame import InstanceFrame
from ewm.ir.state import ExecutionState
from ewm.mcp.client import MCPCall, MCPToolSchema


def select_mcp_read_action(
    frame: InstanceFrame,
    state: ExecutionState,
    reachable: List[ReachableInfo],
    tools: List[MCPToolSchema],
) -> MCPCall:
    raise NotImplementedError("LLM-backed action selection is implemented in a later phase.")

