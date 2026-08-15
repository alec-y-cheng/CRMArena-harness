"""Verification helpers for workflow specs, instance frames, and actions."""

from typing import Any, Mapping, List

from dsl.external_facing.actions import ALLOWED_EVIDENCE_TYPES, DISALLOWED_EVIDENCE_TYPES, SUBJECT_SCOPES
from dsl.general_runtime.actions import ACTION_CATEGORIES, ACTION_DEFINITIONS
from dsl.general_runtime.state import EnabledAction, ExecutionState, InstanceFrame, WorkflowSpec


class RuntimeVerificationError(ValueError):
    pass


KNOWN_PREDICATES = set([
    "answer_contract_satisfied", "refusal_required", "clarification_paused",
    "max_turns_reached", "record_id_available", "search_terms_available",
    "query_terms_available", "parent_id_available", "relationship_verified",
    "source_record_available", "reference_verified", "aggregation_schema_verified",
    "current_customer_scope_allowed", "product_terms_available",
    "retrieved_records_available", "pending_requirements_exist",
    "selected_evidence_available", "evidence_items_available",
    "comparison_values_available", "numeric_inputs_available", "candidates_available",
    "none_answer_allowed", "missing_information_blocks_progress",
    "workflow_scope_is_external", "privacy_precheck_allows_public_knowledge",
])


def validate_workflow_spec(spec: WorkflowSpec) -> None:
    if not spec.workflow_id:
        raise RuntimeVerificationError("workflow_id is required")
    if spec.request_scope not in ("external_customer", "internal_user", "unknown"):
        raise RuntimeVerificationError("Invalid request_scope: {}".format(spec.request_scope))
    if not spec.requirements:
        raise RuntimeVerificationError("WorkflowSpec requires at least one requirement")
    _validate_allowed_actions(spec)
    _validate_requirements(spec)
    _validate_completion(spec.completion)


def validate_instance_frame(frame: InstanceFrame, spec: WorkflowSpec) -> None:
    if frame.workflow_id != spec.workflow_id:
        raise RuntimeVerificationError("InstanceFrame workflow_id does not match WorkflowSpec")
    requirement_names = set(spec.requirement_names())
    allowed_evidence = set(ALLOWED_EVIDENCE_TYPES + DISALLOWED_EVIDENCE_TYPES)
    for item in frame.required_evidence_instances:
        requirement = str(item.get("requirement", ""))
        if requirement not in requirement_names:
            raise RuntimeVerificationError("Unknown requirement in InstanceFrame: {}".format(requirement))
        evidence_type = str(item.get("evidence_type", ""))
        if evidence_type not in allowed_evidence:
            raise RuntimeVerificationError("Unknown evidence type: {}".format(evidence_type))
        subject_scope = str(item.get("subject_scope", ""))
        if subject_scope not in SUBJECT_SCOPES:
            raise RuntimeVerificationError("Unknown subject scope: {}".format(subject_scope))


def compute_enabled_actions(state: ExecutionState) -> List[EnabledAction]:
    enabled = []
    for action in state.workflow_spec.allowed_actions():
        action_spec = ACTION_DEFINITIONS[action]
        if _preconditions_satisfied(action_spec.get("preconditions", {}), state):
            enabled.append(EnabledAction(
                action=action,
                category=str(action_spec.get("category", "")),
                reason="preconditions satisfied",
                required_args=list(action_spec.get("required_args", [])),
                optional_args=list(action_spec.get("optional_args", [])),
            ))
    state.enabled_actions = enabled
    return enabled


def validate_action_selection(selection: Mapping[str, Any], state: ExecutionState) -> None:
    action = str(selection.get("action", ""))
    enabled = set(item.action for item in state.enabled_actions)
    if action not in enabled:
        raise RuntimeVerificationError("Action is not enabled: {}".format(action))
    action_spec = ACTION_DEFINITIONS[action]
    args = selection.get("arguments", {})
    if not isinstance(args, dict):
        raise RuntimeVerificationError("Action arguments must be an object")
    missing = [name for name in action_spec.get("required_args", []) if name not in args]
    if missing:
        raise RuntimeVerificationError("Action missing required args: {}".format(", ".join(missing)))


def _validate_allowed_actions(spec: WorkflowSpec) -> None:
    for category, actions in spec.allowed_action_categories.items():
        if category not in ACTION_CATEGORIES:
            raise RuntimeVerificationError("Unknown action category: {}".format(category))
        if not isinstance(actions, list):
            raise RuntimeVerificationError("allowed_action_categories.{} must be a list".format(category))
        for action in actions:
            if action not in ACTION_DEFINITIONS:
                raise RuntimeVerificationError("Unknown action in WorkflowSpec: {}".format(action))
            actual = ACTION_DEFINITIONS[action].get("category")
            if actual != category:
                raise RuntimeVerificationError("Action {} is category {}, not {}".format(action, actual, category))


def _validate_requirements(spec: WorkflowSpec) -> None:
    allowed = set(ALLOWED_EVIDENCE_TYPES + DISALLOWED_EVIDENCE_TYPES)
    for item in spec.requirements:
        if not item.get("name"):
            raise RuntimeVerificationError("Requirement missing name")
        for evidence_type in item.get("required_evidence_types", []):
            if evidence_type not in allowed:
                raise RuntimeVerificationError("Unknown requirement evidence type: {}".format(evidence_type))


def _validate_completion(completion: Mapping[str, Any]) -> None:
    if not isinstance(completion, dict):
        raise RuntimeVerificationError("completion must be an object")
    keys = [key for key in ("any_of", "all_of") if key in completion]
    if not keys:
        raise RuntimeVerificationError("completion must include any_of or all_of")
    for key in keys:
        values = completion.get(key)
        if not isinstance(values, list) or not values:
            raise RuntimeVerificationError("completion.{} must be a non-empty list".format(key))
        unknown = [value for value in values if value not in KNOWN_PREDICATES]
        if unknown:
            raise RuntimeVerificationError("Unknown completion predicates: {}".format(", ".join(unknown)))


def _preconditions_satisfied(preconditions: Mapping[str, Any], state: ExecutionState) -> bool:
    if not preconditions:
        return True
    if "all_of" in preconditions:
        return all(_predicate_true(str(name), state) for name in preconditions.get("all_of", []))
    if "any_of" in preconditions:
        return any(_predicate_true(str(name), state) for name in preconditions.get("any_of", []))
    return False


def _predicate_true(name: str, state: ExecutionState) -> bool:
    frame = state.instance_frame
    if name == "record_id_available":
        return bool(frame and _frame_has_salesforce_id(frame))
    if name == "query_terms_available": return bool(frame and frame.query_terms)
    if name == "product_terms_available": return bool(frame and frame.product_terms)
    if name == "search_terms_available": return bool(frame and (frame.query_terms or frame.product_terms))
    if name == "retrieved_records_available": return any(state.retrieved_records.values())
    if name == "pending_requirements_exist": return bool(state.pending_requirements)
    if name == "selected_evidence_available": return bool(state.selected_evidence)
    if name == "evidence_items_available": return bool(state.evidence_items)
    if name == "current_customer_scope_allowed": return state.workflow_spec.request_scope == "external_customer"
    if name == "workflow_scope_is_external": return state.workflow_spec.request_scope == "external_customer"
    if name == "privacy_precheck_allows_public_knowledge": return True
    if name == "missing_information_blocks_progress": return bool(frame and frame.missing_information)
    if name == "answer_contract_satisfied": return bool(state.answer_candidate)
    if name == "refusal_required": return any(decision.get("allowed") is False for decision in state.privacy_gate_decisions)
    if name == "clarification_paused": return state.completion_state == "paused_for_clarification"
    if name == "max_turns_reached": return state.completion_state == "max_turns_reached"
    if name == "none_answer_allowed": return state.workflow_spec.answer_contract.get("type", "").endswith("or_none")
    return False


def _frame_has_salesforce_id(frame: InstanceFrame) -> bool:
    for entity in frame.target_entities:
        if not isinstance(entity, Mapping):
            continue
        for key in ("record_id", "id", "Id", "opportunity_id", "case_id"):
            if entity.get(key):
                return True
    for constraint in frame.constraints:
        if not isinstance(constraint, Mapping):
            continue
        for key in ("record_id", "id", "Id", "opportunity_id", "case_id"):
            if constraint.get(key):
                return True
    return False
