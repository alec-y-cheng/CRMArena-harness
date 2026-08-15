"""Shared privacy-gate helpers for general-runtime drivers."""

from typing import Any, Dict, List, Mapping

from dsl.external_facing.actions import (
    evaluate_final_response,
    evaluate_intended_retrieval,
    evaluate_retrieved_evidence,
    render_refusal,
    render_unavailable_response,
)
from dsl.general_runtime.state import ExecutionState


def gate_retrieval(info: Dict[str, Any], symbolic_action: str, evidence_classes: List[Any], subject_scope: str) -> bool:
    decision = evaluate_intended_retrieval(evidence_classes, subject_scope)
    info["external_gate_decisions"].append(
        {
            "stage": "pre_retrieval",
            "symbolic_action": symbolic_action,
            "evidence_classes": evidence_classes,
            "subject_scope": subject_scope,
            "decision": decision.as_dict(),
        }
    )
    if not decision.allowed:
        info["external_gate_refusal"] = render_refusal(decision.reason)
        return False
    return True


def gate_retrieved(info: Dict[str, Any], symbolic_action: str, evidence_class: str, records: List[Mapping[str, Any]]) -> bool:
    decision = evaluate_retrieved_evidence(evidence_class, records)
    info["external_gate_decisions"].append(
        {
            "stage": "post_retrieval",
            "symbolic_action": symbolic_action,
            "evidence_class": evidence_class,
            "record_count": len(records),
            "decision": decision.as_dict(),
        }
    )
    if not decision.allowed:
        info["external_gate_refusal"] = render_refusal(decision.reason)
        return False
    return True


def gate_final_response(
    info: Dict[str, Any],
    state: ExecutionState,
    response: str,
    evidence_classes: List[str],
) -> bool:
    decision = evaluate_final_response(response, evidence_classes)
    info["external_gate_decisions"].append(
        {
            "stage": "final_response",
            "evidence_classes": evidence_classes,
            "decision": decision.as_dict(),
        }
    )
    state.privacy_gate_decisions.append(decision.as_dict())
    if not decision.allowed:
        info["external_gate_refusal"] = render_refusal(decision.reason)
        return False
    return True


def gate_external_router_followup(
    external_router,
    task_query: str,
    conversation_text: str,
    turn: int,
    info: Dict[str, Any],
    allowed_route: str,
    driver_name: str,
    strict_route_match: bool = False,
) -> str:
    if turn == 0 or external_router is None:
        return ""
    route = external_router.route(task_query.strip(), conversation_text)
    gate = external_router.gate_intended_retrieval(route)
    route_info = dict(external_router.last_info)
    route_info["driver"] = driver_name
    route_info["driver_turn"] = turn + 1
    route_info["pre_retrieval_gate"] = gate.as_dict()
    info.setdefault("external_router_followup_checks", []).append(route_info)
    if route.route == allowed_route and gate.allowed:
        return ""
    if route.route == "refuse" or not gate.allowed:
        info["external_gate_refusal"] = external_router.build_refusal(route)
        return info["external_gate_refusal"]

    # Once a workflow is active, route drift and weak follow-up classifications
    # should not override the workflow unless the privacy gate says the requested
    # evidence is unsafe. This keeps public KQA follow-ups from becoming refusals
    # just because the router labels a short follow-up as "unsupported".
    if route.route in ("clarify", "unsupported") and not strict_route_match:
        return ""
    if not strict_route_match:
        return ""

    info["external_gate_refusal"] = render_unavailable_response()
    return info["external_gate_refusal"]
