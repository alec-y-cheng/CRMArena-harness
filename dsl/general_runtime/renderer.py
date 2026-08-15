"""Answer rendering skeleton for generic runtime answer contracts."""

from dsl.general_runtime.state import ExecutionState


def render_final_response(state: ExecutionState) -> str:
    contract_type = state.workflow_spec.answer_contract.get("type", "")
    if state.completion_state == "paused_for_clarification":
        return state.clarification_prompt
    if state.completion_state == "refused":
        return state.final_answer or "I can't provide that information."
    if state.answer_candidate and "answer" in state.answer_candidate:
        return str(state.answer_candidate["answer"])
    if contract_type.endswith("or_none"):
        return "None"
    return state.final_answer
