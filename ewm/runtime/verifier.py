"""Generic validators and verifiers for EWM actions and completion."""

import re
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from ewm.ir.environment import EnvironmentIR
from ewm.ir.frame import InstanceFrame
from ewm.ir.base import Serializable
from ewm.ir.state import ExecutionState
from ewm.mcp.client import MCPCall, MCPToolSchema, ValidationResult

SemanticVerifier = Callable[[InstanceFrame, ExecutionState, EnvironmentIR], ValidationResult]
SemanticVerifierModel = Callable[[Dict[str, Any]], Mapping[str, Any]]


class VerifierSuiteResult(Serializable):
    def __init__(
        self,
        valid: bool,
        status: str,
        checks: Optional[List[ValidationResult]] = None,
        reason: str = "",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.valid = bool(valid)
        self.status = status
        self.checks = checks or []
        self.reason = reason
        self.metadata = dict(metadata or {})


class CompletionVerifierSuite:
    """Runs completion-time verifiers after the controller proposes completion.

    Standalone verifiers such as `validate_mcp_call` still work independently.
    This suite is the completion gate: it combines structural checks with
    optional LLM-backed semantic verifiers over the same frame/state/env IR.
    """

    def __init__(self, semantic_verifiers: Optional[List[SemanticVerifier]] = None) -> None:
        self.semantic_verifiers = semantic_verifiers or []

    def run(self, frame: InstanceFrame, state: ExecutionState, env_ir: EnvironmentIR) -> VerifierSuiteResult:
        checks = [
            verify_schema_validity(env_ir),
            verify_inferred_constraints(frame, state),
            verify_evidence_support(state),
            verify_effect_support(state),
            verify_outcome_contract(frame, state),
            verify_response_contract(frame, state),
        ]
        checks.extend(verifier(frame, state, env_ir) for verifier in self.semantic_verifiers)

        failures = [check for check in checks if not check.valid]
        for check in checks:
            state.verifier_results.append(check.to_dict())
        if failures:
            return VerifierSuiteResult(
                valid=False,
                status="blocked",
                checks=checks,
                reason="; ".join(check.reason for check in failures),
            )
        return VerifierSuiteResult(
            valid=True,
            status="allowed",
            checks=checks,
            reason="All completion verifiers passed.",
        )


class LLMCompletionVerifier:
    """Generic semantic verifier adapter for completion-time checks.

    The runtime supplies the verifier with the frame, execution state, candidate
    outcome, and candidate response. The model decides whether the candidate
    satisfies the instance constraints. Privacy is just one possible constraint;
    this adapter does not need a privacy-specific branch.
    """

    def __init__(self, model: SemanticVerifierModel, verifier_id: str = "semantic_completion") -> None:
        self.model = model
        self.verifier_id = verifier_id

    def __call__(self, frame: InstanceFrame, state: ExecutionState, env_ir: EnvironmentIR) -> ValidationResult:
        payload = _semantic_completion_payload(self.verifier_id, frame, state, env_ir)
        result = self.model(payload)
        valid = bool(result.get("valid", result.get("ready", False)))
        reason = str(result.get("reason") or result.get("rationale") or "")
        return ValidationResult(
            valid=valid,
            reason=reason or ("Semantic verifier passed." if valid else "Semantic verifier rejected completion."),
            metadata={
                "verifier": self.verifier_id,
                "raw": dict(result),
            },
        )


def validate_mcp_call(
    call: MCPCall,
    state: ExecutionState,
    env_ir: EnvironmentIR,
    tool_schema: MCPToolSchema,
) -> ValidationResult:
    if call.name != tool_schema.name:
        return ValidationResult(False, "Call name does not match provided tool schema.")
    if not isinstance(call.arguments, dict):
        return ValidationResult(False, "MCP call arguments must be an object.")
    schema = tool_schema.input_schema or {}
    if isinstance(schema, Mapping):
        for key in schema.get("required", []) or []:
            if key not in call.arguments:
                return ValidationResult(False, "Missing required MCP argument: {}".format(key))
        if schema.get("additionalProperties") is False:
            allowed = set((schema.get("properties") or {}).keys())
            extra = sorted(set(call.arguments.keys()) - allowed)
            if extra:
                return ValidationResult(False, "Unexpected MCP arguments: {}".format(", ".join(extra)))
        type_error = _first_type_error(call.arguments, schema.get("properties") or {})
        if type_error:
            return ValidationResult(False, type_error)
    return ValidationResult(True, "Basic tool-name validation passed.")


def verify_schema_validity(env_ir: EnvironmentIR) -> ValidationResult:
    if env_ir is None:
        return ValidationResult(False, "EnvironmentIR is required.")
    for object_name, schema in env_ir.objects.items():
        if not schema.name:
            return ValidationResult(False, "Object schema is missing a name.")
        if schema.name != object_name:
            return ValidationResult(False, "Object schema key/name mismatch: {}".format(object_name))
        for relationship in schema.relationships:
            if not relationship.source_object or not relationship.target_object:
                return ValidationResult(False, "Relationship on {} is missing source or target.".format(object_name))
    return ValidationResult(True, "EnvironmentIR schema is internally consistent.")


def verify_inferred_constraints(frame: InstanceFrame, state: ExecutionState) -> ValidationResult:
    if frame is None:
        return ValidationResult(False, "InstanceFrame is required.")
    for requirement in frame.evidence_requirements:
        if requirement.required and not requirement.description:
            return ValidationResult(False, "Required evidence requirement is missing a description.")
    return ValidationResult(True, "InstanceFrame constraints are structurally valid.")


def verify_evidence_support(state: ExecutionState) -> ValidationResult:
    invalid_claims = state.claims_with_invalid_support()
    if invalid_claims:
        return ValidationResult(
            False,
            "Claims cite evidence ids that are not present in ExecutionState.",
            {"claim_ids": [claim.claim_id for claim in invalid_claims]},
        )
    return ValidationResult(True, "All claim support references point to collected evidence.")


def verify_effect_support(state: ExecutionState) -> ValidationResult:
    invalid_effects = state.effects_with_invalid_support()
    if invalid_effects:
        return ValidationResult(
            False,
            "Effects cite evidence or observations that are not present in ExecutionState.",
            {"effect_ids": [effect.effect_id for effect in invalid_effects]},
        )
    return ValidationResult(True, "All effect support references point to collected state.")


def verify_outcome_contract(frame: InstanceFrame, state: ExecutionState) -> ValidationResult:
    if state.candidates.get("outcome") is None:
        return ValidationResult(False, "No candidate outcome is available.")
    if frame.outcome_contract.requires_verification and not _has_any_evidence_claim_or_effect(state):
        return ValidationResult(False, "Outcome requires verification but no evidence, claims, or effects are available.")
    return ValidationResult(True, "Outcome contract is structurally satisfied.")


def verify_response_contract(frame: InstanceFrame, state: ExecutionState) -> ValidationResult:
    response = state.candidates.get("response")
    if response is None:
        return ValidationResult(False, "No candidate response is available.")
    text = str(response).strip()
    if not text:
        return ValidationResult(False, "Candidate response is empty.")
    final_contract_result = _verify_final_answer_contract(frame, state, text)
    if not final_contract_result.valid:
        return final_contract_result
    return ValidationResult(True, "Response contract is structurally satisfied.")


def _verify_final_answer_contract(frame: InstanceFrame, state: ExecutionState, response: str) -> ValidationResult:
    contract = getattr(frame, "final_answer_contract", None)
    response_contract = getattr(frame, "response_contract", None)
    exact_instruction = str(getattr(contract, "exact_instruction", "") or "")
    response_contract_text = " ".join(
        str(part or "")
        for part in [
            getattr(response_contract, "description", ""),
            getattr(response_contract, "format_hint", ""),
            " ".join(getattr(response_contract, "constraints", []) or []),
        ]
    )
    strict = bool(getattr(contract, "strict", False))
    if not strict:
        return ValidationResult(True, "No strict final-answer contract to enforce.")

    allowed_literals = set(getattr(contract, "allowed_literals", []) or [])
    if not allowed_literals and "none" in (exact_instruction + " " + response_contract_text).lower():
        allowed_literals.add("None")
    allowed_types = set(getattr(contract, "allowed_answer_types", []) or [])
    text = response.strip()
    outcome = str(state.candidates.get("outcome") or "").strip()

    if outcome in allowed_literals and text != outcome:
        return ValidationResult(
            False,
            "Strict final-answer contract requires exactly '{}' with no extra text.".format(outcome),
        )
    if text in allowed_literals:
        return ValidationResult(True, "Strict literal final-answer contract is satisfied.")

    if "record_id" in allowed_types or "id" in allowed_types:
        if _is_only_salesforce_ids(text):
            return ValidationResult(True, "Strict record-id final-answer contract is satisfied.")
        return ValidationResult(
            False,
            "Strict final-answer contract allows only record IDs or allowed literals; response contains extra text.",
        )

    return ValidationResult(True, "Strict final-answer contract has no deterministic shape rule.")


def _is_only_salesforce_ids(text: str) -> bool:
    parts = [part.strip() for part in text.split(",")]
    if not parts or any(not part for part in parts):
        return False
    return all(re.fullmatch(r"[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?", part) for part in parts)


def verify_completion_state(state: ExecutionState) -> ValidationResult:
    status = state.completion_state.status
    if status not in ("needs_action", "needs_verification", "ready_to_respond"):
        return ValidationResult(False, "Unknown completion status: {}".format(status))
    if status == "ready_to_respond" and not state.completion_state.ready:
        return ValidationResult(False, "ready_to_respond requires ready=True.")
    if status in ("needs_action", "needs_verification") and state.completion_state.ready:
        return ValidationResult(False, "{} requires ready=False.".format(status))
    return ValidationResult(True, "CompletionState uses the generic control statuses.")


def run_completion_verifiers(
    frame: InstanceFrame,
    state: ExecutionState,
    env_ir: EnvironmentIR,
    semantic_verifiers: Optional[List[SemanticVerifier]] = None,
) -> ValidationResult:
    suite_result = CompletionVerifierSuite(semantic_verifiers=semantic_verifiers).run(frame, state, env_ir)
    return ValidationResult(
        suite_result.valid,
        suite_result.reason,
        {
            "status": suite_result.status,
            "checks": [check.to_dict() for check in suite_result.checks],
        },
    )


def _semantic_completion_payload(
    verifier_id: str,
    frame: InstanceFrame,
    state: ExecutionState,
    env_ir: EnvironmentIR,
) -> Dict[str, Any]:
    claims = [claim.to_dict() for claim in state.derived.get("claims", [])][-30:]
    cited_ids = _collect_cited_evidence_ids(state.candidates, claims, state)
    cited_evidence = _cited_evidence_payload(state, cited_ids)
    return {
        "verifier_id": verifier_id,
        "instance_frame": frame.to_dict(),
        "execution_state": {
            "history": state.history[-8:],
            "resolved": state.resolved,
            "effects": [effect.to_dict() for effect in state.effects[-20:]],
            "claims": claims,
            "candidates": state.candidates,
            "recent_actions": {
                "planned": state.actions.get("planned", [])[-8:],
                "executed": state.actions.get("executed", [])[-8:],
                "failed": state.actions.get("failed", [])[-5:],
            },
            "evidence_inventory": [
                {
                    "evidence_id": evidence.evidence_id,
                    "source_tool": evidence.source_tool,
                    "source_object": evidence.source_object,
                    "record_id": evidence.record_id,
                    "subject_scope": evidence.subject_scope,
                }
                for evidence in state.collected.get("evidence", [])[-50:]
            ],
        },
        "cited_evidence_spans": cited_evidence,
        "environment_summary": {
            "metadata": env_ir.metadata,
            "object_count": len(env_ir.objects),
            "tool_count": len(env_ir.tool_schemas),
        },
        "candidate_outcome": state.candidates.get("outcome"),
        "candidate_response": state.candidates.get("response"),
        "instruction": (
            "Return whether the candidate response is ready to send. Compare "
            "the candidate response and candidate outcome against the "
            "InstanceFrame using the ExecutionState claims and cited evidence "
            "spans. Do not require raw observations beyond the cited evidence "
            "spans unless the claims fail to support the response."
        ),
    }


def _collect_cited_evidence_ids(
    candidates: Mapping[str, Any],
    claims: List[Dict[str, Any]],
    state: ExecutionState,
) -> List[str]:
    ids: List[str] = []
    for claim in claims:
        for evidence_id in claim.get("supporting_evidence_ids") or []:
            _append_unique_string(ids, evidence_id)
    for effect in state.effects:
        for evidence_id in effect.evidence_ids:
            _append_unique_string(ids, evidence_id)
    _collect_evidence_ids_from_value(candidates, ids)
    return ids


def _collect_evidence_ids_from_value(value: Any, out: List[str]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in ("supporting_evidence_ids", "evidence_ids", "cited_evidence_ids"):
                for evidence_id in item if isinstance(item, list) else [item]:
                    _append_unique_string(out, evidence_id)
            else:
                _collect_evidence_ids_from_value(item, out)
    elif isinstance(value, list):
        for item in value:
            _collect_evidence_ids_from_value(item, out)


def _append_unique_string(out: List[str], value: Any) -> None:
    text = str(value or "").strip()
    if text and text not in out:
        out.append(text)


def _cited_evidence_payload(state: ExecutionState, cited_ids: List[str]) -> List[Dict[str, Any]]:
    citation_claims: Dict[str, List[str]] = {}
    for claim in state.derived.get("claims", []):
        for evidence_id in claim.supporting_evidence_ids:
            citation_claims.setdefault(evidence_id, []).append(claim.claim_id)
    evidence_by_id = {
        evidence.evidence_id: evidence
        for evidence in state.collected.get("evidence", [])
    }
    payload = []
    for evidence_id in cited_ids[:12]:
        evidence = evidence_by_id.get(evidence_id)
        if evidence is None:
            continue
        excerpt, truncated = _excerpt(evidence.content, max_chars=3000)
        payload.append(
            {
                "evidence_id": evidence.evidence_id,
                "source_observation_id": evidence.source_observation_id,
                "source_tool": evidence.source_tool,
                "source_object": evidence.source_object,
                "record_id": evidence.record_id,
                "subject_scope": evidence.subject_scope,
                "provenance": evidence.provenance,
                "cited_by_claim_ids": citation_claims.get(evidence.evidence_id, []),
                "content_excerpt": excerpt,
                "content_excerpt_truncated": truncated,
            }
        )
    if len(cited_ids) > 12:
        payload.append({"omitted_cited_evidence_count": len(cited_ids) - 12})
    return payload


def _excerpt(value: Any, max_chars: int) -> Tuple[str, bool]:
    text = str(value)
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def _first_type_error(arguments: Mapping[str, Any], properties: Mapping[str, Any]) -> str:
    for key, value in arguments.items():
        prop = properties.get(key)
        if not isinstance(prop, Mapping):
            continue
        expected = prop.get("type")
        if expected == "string" and not isinstance(value, str):
            return "MCP argument '{}' must be a string.".format(key)
        if expected == "integer" and not isinstance(value, int):
            return "MCP argument '{}' must be an integer.".format(key)
        if expected == "boolean" and not isinstance(value, bool):
            return "MCP argument '{}' must be a boolean.".format(key)
        if expected == "object" and not isinstance(value, dict):
            return "MCP argument '{}' must be an object.".format(key)
        if expected == "array" and not isinstance(value, list):
            return "MCP argument '{}' must be an array.".format(key)
    return ""


def _has_any_evidence_claim_or_effect(state: ExecutionState) -> bool:
    return bool(state.collected.get("evidence") or state.derived.get("claims") or state.effects)
