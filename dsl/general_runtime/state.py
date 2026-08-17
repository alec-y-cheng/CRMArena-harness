"""Shared state objects for the generic symbolic runtime."""

from typing import Any, Dict, List, Mapping, Optional


class WorkflowSpec:
    def __init__(self, data: Mapping[str, Any]):
        self.data = dict(data)
        self.workflow_id = str(self.data.get("workflow_id", ""))
        self.task_family = str(self.data.get("task_family", self.workflow_id))
        self.request_scope = str(self.data.get("request_scope", "unknown"))
        self.org_scope = str(self.data.get("org_scope", "unknown"))
        self.requirements = list(self.data.get("requirements", []))
        self.allowed_action_categories = dict(self.data.get("allowed_action_categories", {}))
        self.answer_contract = dict(self.data.get("answer_contract", {}))
        self.extraction_contract = dict(self.data.get("extraction_contract", {}))
        self.render_policy = dict(self.data.get("render_policy", {}))
        self.clarification_policy = dict(self.data.get("clarification_policy", {}))
        self.completion = dict(self.data.get("completion", {}))
        self.phases = dict(self.data.get("phases", {}))

    def allowed_actions(self) -> List[str]:
        out = []
        for actions in self.allowed_action_categories.values():
            for action in actions:
                if action not in out:
                    out.append(action)
        return out

    def allowed_evidence_types(self) -> List[str]:
        out = []
        for requirement in self.requirements:
            for evidence_type in requirement.get("required_evidence_types", []):
                if evidence_type not in out:
                    out.append(evidence_type)
        return out

    def requirement_names(self) -> List[str]:
        return [str(item.get("name", "")) for item in self.requirements]

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.data)


class InstanceFrame:
    def __init__(self, workflow_id: str = "", request_summary: str = "", target_entities: Optional[List[Dict[str, Any]]] = None, query_terms: Optional[List[str]] = None, product_terms: Optional[List[str]] = None, constraints: Optional[List[Dict[str, Any]]] = None, required_evidence_instances: Optional[List[Dict[str, Any]]] = None, clarification_requirements: Optional[List[str]] = None):
        self.workflow_id = workflow_id
        self.request_summary = request_summary
        self.target_entities = target_entities or []
        self.query_terms = query_terms or []
        self.product_terms = product_terms or []
        self.constraints = constraints or []
        self.required_evidence_instances = required_evidence_instances or []
        self.clarification_requirements = clarification_requirements or []

    def as_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "request_summary": self.request_summary,
            "target_entities": [dict(item) for item in self.target_entities],
            "query_terms": list(self.query_terms),
            "product_terms": list(self.product_terms),
            "constraints": [dict(item) for item in self.constraints],
            "required_evidence_instances": [dict(item) for item in self.required_evidence_instances],
            "clarification_requirements": list(self.clarification_requirements),
        }


class EvidenceItem:
    def __init__(self, evidence_id: str, evidence_type: str, source_object: str, record: Mapping[str, Any], subject_scope: str = "unknown"):
        self.evidence_id = evidence_id
        self.evidence_type = evidence_type
        self.source_object = source_object
        self.record = dict(record)
        self.subject_scope = subject_scope

    def as_dict(self) -> Dict[str, Any]:
        return {"evidence_id": self.evidence_id, "evidence_type": self.evidence_type, "source_object": self.source_object, "record": dict(self.record), "subject_scope": self.subject_scope}


class Claim:
    def __init__(self, requirement: str, status: str = "unknown", value: Any = None, evidence_ids: Optional[List[str]] = None, reason: str = ""):
        self.requirement = requirement
        self.status = status
        self.value = value
        self.evidence_ids = evidence_ids or []
        self.reason = reason

    def as_dict(self) -> Dict[str, Any]:
        return {"requirement": self.requirement, "status": self.status, "value": self.value, "evidence_ids": list(self.evidence_ids), "reason": self.reason}


class EnabledAction:
    def __init__(self, action: str, category: str, reason: str = "", required_args: Optional[List[str]] = None, optional_args: Optional[List[str]] = None):
        self.action = action
        self.category = category
        self.reason = reason
        self.required_args = required_args or []
        self.optional_args = optional_args or []

    def as_dict(self) -> Dict[str, Any]:
        return {"action": self.action, "category": self.category, "reason": self.reason, "required_args": list(self.required_args), "optional_args": list(self.optional_args)}


class ExecutionState:
    def __init__(self, workflow_spec: WorkflowSpec, conversation_history: Optional[List[Dict[str, Any]]] = None):
        self.workflow_id = workflow_spec.workflow_id
        self.workflow_spec = workflow_spec
        self.conversation_history = conversation_history or []
        self.instance_frame: Optional[InstanceFrame] = None
        self.current_phase = "initialize"
        self.completed_requirements: List[str] = []
        self.pending_requirements: List[str] = workflow_spec.requirement_names()
        self.planned_actions: List[Dict[str, Any]] = []
        self.executed_actions: List[Dict[str, Any]] = []
        self.retrieved_records: Dict[str, List[Dict[str, Any]]] = {}
        self.evidence_items: List[EvidenceItem] = []
        self.selected_evidence: List[Dict[str, Any]] = []
        self.claims: List[Claim] = []
        self.privacy_gate_decisions: List[Dict[str, Any]] = []
        self.answer_candidate: Optional[Dict[str, Any]] = None
        self.final_answer = ""
        self.completion_state = "running"
        self.model_calls = 0
        self.env_calls = 0
        self.query_errors: List[Dict[str, Any]] = []
        self.enabled_actions: List[EnabledAction] = []
        self.clarification_prompt = ""
        self.time_to_resolution_seconds: Optional[float] = None
        self.runtime_data: Dict[str, Any] = {}

    def as_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "current_phase": self.current_phase,
            "instance_frame": self.instance_frame.as_dict() if self.instance_frame else None,
            "completed_requirements": list(self.completed_requirements),
            "pending_requirements": list(self.pending_requirements),
            "planned_actions": [dict(item) for item in self.planned_actions],
            "executed_actions": [dict(item) for item in self.executed_actions],
            "retrieved_records": {key: [dict(item) for item in value] for key, value in self.retrieved_records.items()},
            "evidence_items": [item.as_dict() for item in self.evidence_items],
            "selected_evidence": [dict(item) for item in self.selected_evidence],
            "claims": [item.as_dict() for item in self.claims],
            "privacy_gate_decisions": [dict(item) for item in self.privacy_gate_decisions],
            "answer_candidate": dict(self.answer_candidate) if self.answer_candidate else None,
            "final_answer": self.final_answer,
            "completion_state": self.completion_state,
            "model_calls": self.model_calls,
            "env_calls": self.env_calls,
            "query_errors": [dict(item) for item in self.query_errors],
            "enabled_actions": [item.as_dict() for item in self.enabled_actions],
            "clarification_prompt": self.clarification_prompt,
            "time_to_resolution_seconds": self.time_to_resolution_seconds,
            "runtime_data": _serialize_runtime_data(self.runtime_data),
        }


def _serialize_runtime_data(value: Any) -> Any:
    private_runtime_keys = {"env", "messages", "info"}
    if hasattr(value, "as_dict"):
        return value.as_dict()
    if isinstance(value, dict):
        return {
            key: _serialize_runtime_data(item)
            for key, item in value.items()
            if key not in private_runtime_keys
        }
    if isinstance(value, list):
        return [_serialize_runtime_data(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return {"type": value.__class__.__name__, "repr": repr(value)}
