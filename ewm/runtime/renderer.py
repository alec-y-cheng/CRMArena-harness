"""Response rendering interfaces."""

from ewm.ir.frame import InstanceFrame
from ewm.ir.state import CompletionState, ExecutionState


def render_response(frame: InstanceFrame, state: ExecutionState, completion: CompletionState) -> str:
    """Render the current user-facing response.

    Phase 5 keeps rendering simple: the controller supplies the candidate
    response, and the completion verifier decides whether it is ready. Later
    phases can replace this with a bounded renderer/verifier pair.
    """

    if completion.ready and state.candidates.get("response") is not None:
        return str(state.candidates["response"])

    if completion.status == "needs_action" and _needs_source(completion) == "user":
        needed = completion.needed[0] if completion.needed else {}
        description = str(needed.get("description") or completion.reason or "").strip()
        if description:
            return description
        return ""

    return ""


def _needs_source(completion: CompletionState) -> str:
    if not completion.needed:
        return ""
    first = completion.needed[0]
    if not isinstance(first, dict):
        return ""
    return str(first.get("source") or "")
