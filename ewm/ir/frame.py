"""Instance-level task frame inferred from the current request."""

from typing import Any, Dict, List, Optional

from .base import Serializable, ensure_dict, object_list, string_list


class EvidenceRequirement(Serializable):
    def __init__(
        self,
        description: str,
        requirement_id: Optional[str] = None,
        evidence_type: Optional[str] = None,
        source: Optional[str] = None,
        subject: Optional[str] = None,
        required: bool = True,
        constraints: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.requirement_id = requirement_id or ""
        self.description = description
        self.evidence_type = evidence_type or ""
        self.source = source
        self.subject = subject or ""
        self.required = bool(required)
        self.constraints = string_list(constraints)
        self.metadata = ensure_dict(metadata)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceRequirement":
        return cls(
            description=str(data.get("description") or data.get("goal") or ""),
            requirement_id=str(data.get("requirement_id") or data.get("id") or ""),
            evidence_type=str(data.get("evidence_type") or data.get("type") or ""),
            source=data.get("source"),
            subject=data.get("subject"),
            required=bool(data.get("required", True)),
            constraints=string_list(data.get("constraints")),
            metadata=ensure_dict(data.get("metadata")),
        )


class OutcomeContract(Serializable):
    def __init__(
        self,
        description: str = "",
        success_criteria: Optional[List[str]] = None,
        required_claims: Optional[List[str]] = None,
        requires_verification: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.description = description
        self.success_criteria = string_list(success_criteria)
        self.required_claims = string_list(required_claims)
        self.requires_verification = bool(requires_verification)
        self.metadata = ensure_dict(metadata)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OutcomeContract":
        return cls(
            description=str(data.get("description") or ""),
            success_criteria=string_list(data.get("success_criteria")),
            required_claims=string_list(data.get("required_claims")),
            requires_verification=bool(data.get("requires_verification", True)),
            metadata=ensure_dict(data.get("metadata")),
        )


class ResponseContract(Serializable):
    def __init__(
        self,
        description: str = "",
        format_hint: Optional[str] = None,
        constraints: Optional[List[str]] = None,
        allowed_audience: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.description = description
        self.format_hint = format_hint
        self.constraints = string_list(constraints)
        self.allowed_audience = allowed_audience or ""
        self.metadata = ensure_dict(metadata)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResponseContract":
        return cls(
            description=str(data.get("description") or ""),
            format_hint=data.get("format_hint"),
            constraints=string_list(data.get("constraints")),
            allowed_audience=data.get("allowed_audience"),
            metadata=ensure_dict(data.get("metadata")),
        )


class FinalAnswerContract(Serializable):
    def __init__(
        self,
        exact_instruction: str = "",
        strict: bool = False,
        allowed_answer_types: Optional[List[str]] = None,
        allowed_literals: Optional[List[str]] = None,
        separator: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.exact_instruction = exact_instruction
        self.strict = bool(strict)
        self.allowed_answer_types = string_list(allowed_answer_types)
        self.allowed_literals = string_list(allowed_literals)
        self.separator = separator or ""
        self.metadata = ensure_dict(metadata)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FinalAnswerContract":
        return cls(
            exact_instruction=str(data.get("exact_instruction") or data.get("instruction") or ""),
            strict=bool(data.get("strict", False)),
            allowed_answer_types=string_list(data.get("allowed_answer_types")),
            allowed_literals=string_list(data.get("allowed_literals")),
            separator=data.get("separator"),
            metadata=ensure_dict(data.get("metadata")),
        )


class InstanceFrame(Serializable):
    """Current best interpretation of the user-visible request."""

    def __init__(
        self,
        frame_id: str = "",
        goal: str = "",
        request_summary: str = "",
        actor: Optional[Dict[str, Any]] = None,
        entities_or_references: Optional[List[Dict[str, Any]]] = None,
        constraints: Optional[List[Any]] = None,
        evidence_requirements: Optional[List[EvidenceRequirement]] = None,
        outcome_contract: Optional[OutcomeContract] = None,
        response_contract: Optional[ResponseContract] = None,
        final_answer_contract: Optional[FinalAnswerContract] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.frame_id = frame_id
        self.goal = goal
        self.request_summary = request_summary
        self.actor = ensure_dict(actor)
        self.entities_or_references = object_list(entities_or_references)
        self.constraints = _normalize_constraints(constraints)
        self.evidence_requirements = [
            item if isinstance(item, EvidenceRequirement) else EvidenceRequirement.from_dict(ensure_dict(item))
            for item in (evidence_requirements or [])
        ]
        self.outcome_contract = (
            outcome_contract
            if isinstance(outcome_contract, OutcomeContract)
            else OutcomeContract.from_dict(ensure_dict(outcome_contract))
        )
        self.response_contract = (
            response_contract
            if isinstance(response_contract, ResponseContract)
            else ResponseContract.from_dict(ensure_dict(response_contract))
        )
        self.final_answer_contract = (
            final_answer_contract
            if isinstance(final_answer_contract, FinalAnswerContract)
            else FinalAnswerContract.from_dict(ensure_dict(final_answer_contract))
        )
        self.metadata = ensure_dict(metadata)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InstanceFrame":
        outcome = data.get("outcome_contract")
        response = data.get("response_contract")
        final_answer = data.get("final_answer_contract")
        return cls(
            frame_id=str(data.get("frame_id") or data.get("id") or ""),
            goal=str(data.get("goal") or ""),
            request_summary=str(data.get("request_summary") or data.get("summary") or ""),
            actor=ensure_dict(data.get("actor")),
            entities_or_references=object_list(data.get("entities_or_references") or data.get("entities")),
            constraints=data.get("constraints"),
            evidence_requirements=[
                EvidenceRequirement.from_dict(ensure_dict(item))
                for item in (data.get("evidence_requirements") or [])
            ],
            outcome_contract=OutcomeContract.from_dict(ensure_dict(outcome)) if outcome is not None else None,
            response_contract=ResponseContract.from_dict(ensure_dict(response)) if response is not None else None,
            final_answer_contract=(
                FinalAnswerContract.from_dict(ensure_dict(final_answer)) if final_answer is not None else None
            ),
            metadata=ensure_dict(data.get("metadata")),
        )

    def add_evidence_requirement(self, requirement: EvidenceRequirement) -> None:
        self.evidence_requirements.append(requirement)


def _normalize_constraints(value: Any) -> List[Any]:
    out: List[Any] = []
    if value is None:
        return out
    items = value if isinstance(value, list) else [value]
    for item in items:
        if isinstance(item, dict):
            out.append(dict(item))
        else:
            text = str(item or "").strip()
            if text:
                out.append(text)
    return out


def infer_instance_frame(messages: List[Dict[str, Any]], env_summary: Dict[str, Any]) -> InstanceFrame:
    """Infer an InstanceFrame from messages and environment context.

    Phase 1 intentionally leaves semantic inference unimplemented. The runtime
    will later call a bounded LLM extractor here and validate the returned
    structured frame.
    """

    raise NotImplementedError("InstanceFrame inference is implemented in a later phase.")
