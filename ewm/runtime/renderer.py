"""Response rendering interfaces."""

from ewm.ir.frame import InstanceFrame
from ewm.ir.state import CompletionState, ExecutionState


def render_response(frame: InstanceFrame, state: ExecutionState, completion: CompletionState) -> str:
    raise NotImplementedError("Response rendering is implemented in a later phase.")

