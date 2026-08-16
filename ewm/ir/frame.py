"""Instance-level task frame inferred from the current request."""

from typing import Any, Dict, List, Optional

from .base import Serializable


class EvidenceRequirement(Serializable):
    def __init__(
        self,
        description: str,
        source: Optional[str] = None,
        constraints: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.description = description
        self.source = source
        self.constraints = constraints or []
        self.metadata = metadata or {}


class OutcomeContract(Serializable):
    def __init__(
        self,
        description: str = "",
        success_criteria: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.description = description
        self.success_criteria = success_criteria or []
        self.metadata = metadata or {}


class ResponseContract(Serializable):
    def __init__(
        self,
        description: str = "",
        format_hint: Optional[str] = None,
        constraints: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.description = description
        self.format_hint = format_hint
        self.constraints = constraints or []
        self.metadata = metadata or {}


class InstanceFrame(Serializable):
    """Current best interpretation of the user-visible request."""

    def __init__(
        self,
        goal: str = "",
        request_summary: str = "",
        actor: Optional[Dict[str, Any]] = None,
        entities_or_references: Optional[List[Dict[str, Any]]] = None,
        constraints: Optional[List[str]] = None,
        evidence_requirements: Optional[List[EvidenceRequirement]] = None,
        outcome_contract: Optional[OutcomeContract] = None,
        response_contract: Optional[ResponseContract] = None,
        missing_information: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.goal = goal
        self.request_summary = request_summary
        self.actor = actor or {}
        self.entities_or_references = entities_or_references or []
        self.constraints = constraints or []
        self.evidence_requirements = evidence_requirements or []
        self.outcome_contract = outcome_contract or OutcomeContract()
        self.response_contract = response_contract or ResponseContract()
        self.missing_information = missing_information or []
        self.metadata = metadata or {}


def infer_instance_frame(messages: List[Dict[str, Any]], env_summary: Dict[str, Any]) -> InstanceFrame:
    """Infer an InstanceFrame from messages and environment context.

    Phase 1 intentionally leaves semantic inference unimplemented. The runtime
    will later call a bounded LLM extractor here and validate the returned
    structured frame.
    """

    raise NotImplementedError("InstanceFrame inference is implemented in a later phase.")

