"""Mutable execution state for EWM trajectories."""

from typing import Any, Dict, List, Optional

from .base import Serializable
from .frame import InstanceFrame


class Observation(Serializable):
    def __init__(
        self,
        observation_id: str,
        source: str,
        payload: Any,
        action_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.observation_id = observation_id
        self.source = source
        self.payload = payload
        self.action_id = action_id
        self.metadata = metadata or {}


class EvidenceItem(Serializable):
    def __init__(
        self,
        evidence_id: str,
        source_observation_id: str,
        content: Any,
        provenance: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.evidence_id = evidence_id
        self.source_observation_id = source_observation_id
        self.content = content
        self.provenance = provenance or {}
        self.metadata = metadata or {}


class Claim(Serializable):
    def __init__(
        self,
        claim_id: str,
        claim_text: str,
        status: str = "unknown",
        value: Any = None,
        supporting_evidence_ids: Optional[List[str]] = None,
        confidence: Optional[float] = None,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.claim_id = claim_id
        self.claim_text = claim_text
        self.status = status
        self.value = value
        self.supporting_evidence_ids = supporting_evidence_ids or []
        self.confidence = confidence
        self.reason = reason
        self.metadata = metadata or {}


class CompletionState(Serializable):
    """Generic loop-control result.

    `status` is descriptive. Runtime control should primarily rely on `ready`,
    validated `next_action`, and verifier results.
    """

    def __init__(
        self,
        ready: bool = False,
        status: str = "running",
        needed: Optional[List[Dict[str, Any]]] = None,
        next_action: Optional[Dict[str, Any]] = None,
        verifier_summary: Optional[Dict[str, Any]] = None,
        reason: str = "",
    ) -> None:
        self.ready = ready
        self.status = status
        self.needed = needed or []
        self.next_action = next_action
        self.verifier_summary = verifier_summary or {}
        self.reason = reason


class ExecutionState(Serializable):
    """Mutable wrapper around frame, observations, evidence, and verifier state."""

    def __init__(self, frame: Optional[InstanceFrame] = None) -> None:
        self.frame = frame or InstanceFrame()
        self.history: List[Dict[str, Any]] = []
        self.collected: Dict[str, List[Any]] = {
            "observations": [],
            "evidence": [],
        }
        self.resolved: Dict[str, Any] = {
            "entities": [],
            "facts": [],
            "unresolved": [],
        }
        self.derived: Dict[str, List[Any]] = {
            "claims": [],
            "summaries": [],
        }
        self.actions: Dict[str, List[Any]] = {
            "planned": [],
            "executed": [],
            "failed": [],
        }
        self.verifier_results: List[Dict[str, Any]] = []
        self.candidates: Dict[str, Any] = {
            "outcome": None,
            "response": None,
        }
        self.completion_state = CompletionState()
        self.metrics: Dict[str, Any] = {
            "model_calls": 0,
            "env_calls": 0,
            "errors": [],
        }

    def add_observation(self, observation: Observation) -> None:
        self.collected["observations"].append(observation)

    def add_evidence(self, evidence: EvidenceItem) -> None:
        self.collected["evidence"].append(evidence)

    def add_claim(self, claim: Claim) -> None:
        self.derived["claims"].append(claim)

