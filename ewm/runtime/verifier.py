"""Generic validators and verifiers for EWM actions and evidence."""

from ewm.ir.environment import EnvironmentIR
from ewm.ir.state import ExecutionState
from ewm.mcp.client import MCPCall, MCPToolSchema, ValidationResult


def validate_mcp_call(
    call: MCPCall,
    state: ExecutionState,
    env_ir: EnvironmentIR,
    tool_schema: MCPToolSchema,
) -> ValidationResult:
    if call.name != tool_schema.name:
        return ValidationResult(False, "Call name does not match provided tool schema.")
    return ValidationResult(True, "Basic tool-name validation passed.")

