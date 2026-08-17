"""Normalize MCP observations into EWM observations and evidence items."""

import re
from typing import Any, Dict, List, Optional

from ewm.ir.state import EvidenceItem, Observation

from .client import MCPCall, MCPObservation


def normalize_observation(call: MCPCall, observation: MCPObservation) -> List[EvidenceItem]:
    """Create provenance-bearing evidence items from an MCP observation.

    The normalizer is tool-aware but not task-aware. It does not decide which
    evidence matters; it only turns returned records/schema/user context into
    citable units the runtime can later select or verify.
    """

    obs_id = call.call_id or "obs_{}".format(call.name)
    if not observation.ok:
        return []
    payload = observation.payload if isinstance(observation.payload, dict) else {}

    if call.name == "soqlQuery":
        source_object = _source_object_from_soql(call.arguments.get("query"))
        return _record_evidence_items(call, obs_id, payload.get("records", []), source_object)

    if call.name == "find":
        raw_records = _raw_search_records(observation)
        return _record_evidence_items(
            call,
            obs_id,
            payload.get("searchRecords", []),
            source_object=None,
            raw_records=raw_records,
        )

    if call.name == "getRelatedRecords":
        relationship = {}
        if isinstance(observation.raw, dict):
            relationship = observation.raw.get("relationship") or {}
        source_object = relationship.get("childSObject")
        metadata = {"relationship": relationship} if relationship else {}
        return _record_evidence_items(call, obs_id, payload.get("records", []), source_object, metadata=metadata)

    if call.name == "getObjectSchema":
        object_name = ""
        if payload.get("mode") == "detail":
            object_name = str((payload.get("object") or {}).get("name") or "")
        return [
            EvidenceItem(
                evidence_id="ev_{}_schema".format(obs_id),
                source_observation_id=obs_id,
                content=payload,
                source_tool=call.name,
                source_object=object_name,
                subject_scope="schema",
                provenance=_provenance(call),
                metadata={"evidence_kind": "schema"},
            )
        ]

    if call.name == "getUserInfo":
        user = payload.get("user", payload)
        return [
            EvidenceItem(
                evidence_id="ev_{}_user".format(obs_id),
                source_observation_id=obs_id,
                content=user,
                source_tool=call.name,
                source_object="User",
                record_id=str(user.get("Id") or "") if isinstance(user, dict) else "",
                subject_scope="authenticated_user",
                provenance=_provenance(call),
                metadata={"evidence_kind": "user_context"},
            )
        ]

    return [
        EvidenceItem(
            evidence_id="ev_{}".format(obs_id),
            source_observation_id=obs_id,
            content=observation.payload,
            source_tool=call.name,
            provenance={
                "tool": call.name,
                "arguments": call.arguments,
            },
        )
    ]


def to_observation(call: MCPCall, observation: MCPObservation) -> Observation:
    obs_id = call.call_id or "obs_{}".format(call.name)
    return Observation(
        observation_id=obs_id,
        source=call.name,
        payload=observation.raw,
        action_id=call.call_id,
        ok=observation.ok,
        metadata={"error": observation.error} if observation.error else {},
    )


def _record_evidence_items(
    call: MCPCall,
    obs_id: str,
    records: List[Dict[str, Any]],
    source_object: Optional[str],
    raw_records: Optional[List[Dict[str, Any]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> List[EvidenceItem]:
    items = []
    raw_records = raw_records or []
    for index, record in enumerate(records or []):
        raw_record = raw_records[index] if index < len(raw_records) else {}
        object_name = source_object or _object_type_from_raw_record(raw_record)
        record_id = str(record.get("Id") or raw_record.get("Id") or "")
        suffix = record_id or str(index + 1)
        items.append(
            EvidenceItem(
                evidence_id="ev_{}_{}".format(obs_id, suffix),
                source_observation_id=obs_id,
                content=record,
                source_tool=call.name,
                source_object=object_name or "",
                record_id=record_id,
                subject_scope=_subject_scope_for_tool(call.name),
                provenance=_provenance(call),
                metadata=dict(metadata or {}, evidence_kind="record"),
            )
        )
    return items


def _provenance(call: MCPCall) -> Dict[str, Any]:
    return {
        "tool": call.name,
        "arguments": dict(call.arguments),
        "call_id": call.call_id,
    }


def _source_object_from_soql(query: Any) -> str:
    match = re.search(r"\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)", str(query or ""), re.IGNORECASE)
    return match.group(1) if match else ""


def _raw_search_records(observation: MCPObservation) -> List[Dict[str, Any]]:
    if not isinstance(observation.raw, dict):
        return []
    raw = observation.raw.get("raw")
    if isinstance(raw, dict):
        records = raw.get("searchRecords")
        if isinstance(records, list):
            return records
    return []


def _object_type_from_raw_record(record: Dict[str, Any]) -> str:
    attributes = record.get("attributes")
    if isinstance(attributes, dict):
        return str(attributes.get("type") or "")
    return ""


def _subject_scope_for_tool(tool_name: str) -> str:
    if tool_name in ("getObjectSchema",):
        return "schema"
    if tool_name in ("getUserInfo",):
        return "authenticated_user"
    return "environment"
