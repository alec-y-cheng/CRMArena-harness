"""Mutable execution state for EWM trajectories."""

from typing import Any, Dict, List, Optional

from .base import Serializable, ensure_dict, object_list, string_list
from .frame import InstanceFrame


class Observation(Serializable):
    def __init__(
        self,
        observation_id: str,
        source: str,
        payload: Any,
        action_id: Optional[str] = None,
        ok: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.observation_id = observation_id
        self.source = source
        self.payload = payload
        self.action_id = action_id
        self.ok = bool(ok)
        self.metadata = ensure_dict(metadata)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Observation":
        return cls(
            observation_id=str(data.get("observation_id") or data.get("id") or ""),
            source=str(data.get("source") or ""),
            payload=data.get("payload"),
            action_id=data.get("action_id"),
            ok=bool(data.get("ok", True)),
            metadata=ensure_dict(data.get("metadata")),
        )


class EvidenceItem(Serializable):
    def __init__(
        self,
        evidence_id: str,
        source_observation_id: str,
        content: Any,
        source_tool: Optional[str] = None,
        source_object: Optional[str] = None,
        record_id: Optional[str] = None,
        subject_scope: str = "unknown",
        provenance: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.evidence_id = evidence_id
        self.source_observation_id = source_observation_id
        self.source_tool = source_tool or ""
        self.source_object = source_object or ""
        self.record_id = record_id or ""
        self.subject_scope = subject_scope or "unknown"
        self.content = content
        self.provenance = ensure_dict(provenance)
        self.metadata = ensure_dict(metadata)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceItem":
        return cls(
            evidence_id=str(data.get("evidence_id") or data.get("id") or ""),
            source_observation_id=str(data.get("source_observation_id") or ""),
            content=data.get("content") if "content" in data else data.get("payload"),
            source_tool=data.get("source_tool"),
            source_object=data.get("source_object"),
            record_id=data.get("record_id"),
            subject_scope=str(data.get("subject_scope") or "unknown"),
            provenance=ensure_dict(data.get("provenance")),
            metadata=ensure_dict(data.get("metadata")),
        )


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
        self.supporting_evidence_ids = string_list(supporting_evidence_ids)
        self.confidence = confidence
        self.reason = reason
        self.metadata = ensure_dict(metadata)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Claim":
        confidence = data.get("confidence")
        try:
            confidence_value = None if confidence is None else float(confidence)
        except (TypeError, ValueError):
            confidence_value = None
        return cls(
            claim_id=str(data.get("claim_id") or data.get("id") or ""),
            claim_text=str(data.get("claim_text") or data.get("text") or ""),
            status=str(data.get("status") or "unknown"),
            value=data.get("value"),
            supporting_evidence_ids=string_list(data.get("supporting_evidence_ids") or data.get("evidence_ids")),
            confidence=confidence_value,
            reason=str(data.get("reason") or ""),
            metadata=ensure_dict(data.get("metadata")),
        )


class Effect(Serializable):
    """Confirmed or attempted environment effect from workflow execution.

    Effects are intentionally generic so the same verifier contract can cover
    read-only workflows, write workflows, approvals, notifications, or future
    enterprise actions. Read actions may leave this empty; write-capable
    backends should populate it with confirmed mutation/effect summaries.
    """

    def __init__(
        self,
        effect_id: str,
        action_id: Optional[str] = None,
        operation: str = "",
        object_name: str = "",
        record_id: str = "",
        status: str = "",
        before: Any = None,
        after: Any = None,
        changes: Optional[Dict[str, Any]] = None,
        evidence_ids: Optional[List[str]] = None,
        observation_id: Optional[str] = None,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.effect_id = effect_id
        self.action_id = action_id or ""
        self.operation = operation
        self.object_name = object_name
        self.record_id = record_id
        self.status = status
        self.before = before
        self.after = after
        self.changes = ensure_dict(changes)
        self.evidence_ids = string_list(evidence_ids)
        self.observation_id = observation_id or ""
        self.reason = reason
        self.metadata = ensure_dict(metadata)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Effect":
        return cls(
            effect_id=str(data.get("effect_id") or data.get("id") or ""),
            action_id=data.get("action_id"),
            operation=str(data.get("operation") or ""),
            object_name=str(data.get("object_name") or data.get("object") or ""),
            record_id=str(data.get("record_id") or data.get("id_value") or ""),
            status=str(data.get("status") or ""),
            before=data.get("before"),
            after=data.get("after"),
            changes=ensure_dict(data.get("changes")),
            evidence_ids=string_list(data.get("evidence_ids") or data.get("supporting_evidence_ids")),
            observation_id=data.get("observation_id"),
            reason=str(data.get("reason") or ""),
            metadata=ensure_dict(data.get("metadata")),
        )


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
        self.needed = object_list(needed)
        self.next_action = ensure_dict(next_action) if next_action is not None else None
        self.verifier_summary = ensure_dict(verifier_summary)
        self.reason = reason

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompletionState":
        return cls(
            ready=bool(data.get("ready", False)),
            status=str(data.get("status") or "running"),
            needed=object_list(data.get("needed")),
            next_action=data.get("next_action"),
            verifier_summary=ensure_dict(data.get("verifier_summary")),
            reason=str(data.get("reason") or ""),
        )


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
        self.effects: List[Effect] = []
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

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionState":
        state = cls(frame=InstanceFrame.from_dict(ensure_dict(data.get("frame"))))
        state.history = object_list(data.get("history"))
        collected = ensure_dict(data.get("collected"))
        state.collected = {
            "observations": [
                item if isinstance(item, Observation) else Observation.from_dict(ensure_dict(item))
                for item in collected.get("observations", [])
            ],
            "evidence": [
                item if isinstance(item, EvidenceItem) else EvidenceItem.from_dict(ensure_dict(item))
                for item in collected.get("evidence", [])
            ],
        }
        state.resolved = ensure_dict(data.get("resolved")) or {"entities": [], "facts": [], "unresolved": []}
        derived = ensure_dict(data.get("derived"))
        state.derived = {
            "claims": [
                item if isinstance(item, Claim) else Claim.from_dict(ensure_dict(item))
                for item in derived.get("claims", [])
            ],
            "summaries": list(derived.get("summaries", [])),
        }
        state.effects = [
            item if isinstance(item, Effect) else Effect.from_dict(ensure_dict(item))
            for item in data.get("effects", [])
        ]
        state.actions = ensure_dict(data.get("actions")) or {"planned": [], "executed": [], "failed": []}
        state.verifier_results = object_list(data.get("verifier_results"))
        state.candidates = ensure_dict(data.get("candidates")) or {"outcome": None, "response": None}
        completion = data.get("completion_state")
        state.completion_state = (
            CompletionState.from_dict(ensure_dict(completion)) if completion is not None else CompletionState()
        )
        state.metrics = ensure_dict(data.get("metrics")) or {"model_calls": 0, "env_calls": 0, "errors": []}
        _ensure_state_shape(state)
        return state

    def add_observation(self, observation: Observation) -> None:
        self.collected["observations"].append(observation)

    def add_evidence(self, evidence: EvidenceItem) -> None:
        self.collected["evidence"].append(evidence)

    def add_claim(self, claim: Claim) -> None:
        self.derived["claims"].append(claim)

    def add_effect(self, effect: Effect) -> None:
        self.effects.append(effect)

    def upsert_claim(self, claim: Claim) -> None:
        """Replace a logical claim and move the latest version to the end.

        When the controller reuses a claim_id, it is proposing a revised
        interpretation of the same logical claim. The active state should not
        keep stale text around, so we remove older versions and append the new
        one. The append preserves recency ordering for compact prompts.
        """
        self.derived["claims"] = [
            existing
            for existing in self.derived["claims"]
            if existing.claim_id != claim.claim_id
        ]
        self.add_claim(claim)

    def update_frame(self, frame: InstanceFrame) -> None:
        self.frame = frame

    def evidence_ids(self) -> List[str]:
        return [item.evidence_id for item in self.collected["evidence"]]

    def claims_with_invalid_support(self) -> List[Claim]:
        valid_ids = set(self.evidence_ids())
        invalid = []
        for claim in self.derived["claims"]:
            if any(evidence_id not in valid_ids for evidence_id in claim.supporting_evidence_ids):
                invalid.append(claim)
        return invalid

    def effects_with_invalid_support(self) -> List[Effect]:
        valid_evidence_ids = set(self.evidence_ids())
        valid_observation_ids = {
            observation.observation_id
            for observation in self.collected["observations"]
        }
        invalid = []
        for effect in self.effects:
            has_bad_evidence = any(evidence_id not in valid_evidence_ids for evidence_id in effect.evidence_ids)
            has_bad_observation = bool(effect.observation_id and effect.observation_id not in valid_observation_ids)
            if has_bad_evidence or has_bad_observation:
                invalid.append(effect)
        return invalid

    def record_action_planned(self, action: Dict[str, Any]) -> None:
        self.actions["planned"].append(dict(action))

    def record_action_executed(self, action: Dict[str, Any]) -> None:
        self.actions["executed"].append(dict(action))

    def record_action_failed(self, action: Dict[str, Any], reason: str) -> None:
        item = dict(action)
        item["reason"] = reason
        self.actions["failed"].append(item)


def _ensure_state_shape(state: ExecutionState) -> None:
    for key in ("observations", "evidence"):
        state.collected.setdefault(key, [])
    for key in ("entities", "facts", "unresolved"):
        state.resolved.setdefault(key, [])
    for key in ("claims", "summaries"):
        state.derived.setdefault(key, [])
    if not hasattr(state, "effects") or state.effects is None:
        state.effects = []
    for key in ("planned", "executed", "failed"):
        state.actions.setdefault(key, [])
    state.candidates.setdefault("outcome", None)
    state.candidates.setdefault("response", None)
    state.metrics.setdefault("model_calls", 0)
    state.metrics.setdefault("env_calls", 0)
    state.metrics.setdefault("errors", [])
