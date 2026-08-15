"""Shared environment I/O helpers for general-runtime drivers."""

import ast
from collections.abc import Mapping as ABCMapping
from typing import Any, Dict, List, Mapping

from dsl.external_facing.harness import ExternalFacingDSLRunResult
from dsl.general_runtime.state import ExecutionState


def init_runtime_info(task_family: str, workflow_id: str, metadata: Any) -> Dict[str, Any]:
    return {
        "dsl_enabled": True,
        "dsl_task_family": task_family,
        "general_runtime_enabled": True,
        "workflow_id": workflow_id,
        "symbolic_state_snapshots": [],
        "retrieved_objects": {},
        "query_errors": [],
        "model_calls": 0,
        "env_steps": 0,
        "metadata": metadata,
        "answer_turns": [],
        "external_gate_decisions": [],
    }


def runtime_handles(state: ExecutionState):
    return state.runtime_data["env"], state.runtime_data["messages"], state.runtime_data["info"]


def execute_env(env, query: str, messages: List[Dict[str, str]], info: Dict[str, Any], symbolic_action: str) -> List[Mapping[str, Any]]:
    action = {"name": "execute", "content": query}
    messages.append({"role": "assistant", "content": "<execute>{}</execute>".format(query)})
    observation, _reward, _done, step_info = env.step(action)
    info["env_steps"] += 1
    messages.append({"role": "user", "content": "Salesforce instance output: {}".format(observation)})
    if step_info.get("end_reason", {}).get("message") == "SOQL/SOSL query error":
        info["query_errors"].append(
            {
                "symbolic_action": symbolic_action,
                "query": query,
                "error": step_info["end_reason"].get("content"),
            }
        )
        records = []
    else:
        records = parse_records(observation)
    info["retrieved_objects"][symbolic_action] = {
        "query": query,
        "record_count": len(records),
        "records": records,
    }
    return records


def respond_env(env, messages: List[Dict[str, str]], info: Dict[str, Any], answer: str) -> ExternalFacingDSLRunResult:
    action = {"name": "respond", "content": answer}
    messages.append({"role": "assistant", "content": "<respond>{}</respond>".format(answer)})
    observation, reward, done, step_info = env.step(action)
    info["env_steps"] += 1
    info["end_reason"] = step_info.get("end_reason", {})
    info["agent_actions"] = step_info.get("agent_actions", [])
    copy_resolution_timing(info, step_info)
    messages.append({"role": "user", "content": observation})
    return ExternalFacingDSLRunResult(reward=reward, done=done, messages=messages, info=info)


def copy_resolution_timing(info: Dict[str, Any], step_info: Mapping[str, Any]) -> None:
    for key in ("time_to_resolution_seconds", "interaction_start_time", "interaction_end_time"):
        if key in step_info:
            info[key] = step_info[key]


def snapshot_state(info: Dict[str, Any], event: str, state: ExecutionState) -> None:
    info["symbolic_state_snapshots"].append({"event": event, "state": state.as_dict()})


def parse_records(observation: Any) -> List[Mapping[str, Any]]:
    if isinstance(observation, list):
        return observation
    if not isinstance(observation, str):
        return []
    try:
        parsed = ast.literal_eval(observation)
    except (SyntaxError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def dedupe_records(records: List[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    seen = set()
    out = []
    for record in records:
        record_id = record.get("Id") if isinstance(record, ABCMapping) else None
        key = record_id or repr(sorted(record.items())) if isinstance(record, ABCMapping) else repr(record)
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def unique_record_values(records: List[Mapping[str, Any]], field_name: str) -> List[str]:
    seen = set()
    out = []
    for record in records:
        value = record.get(field_name) if isinstance(record, ABCMapping) else None
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def conversation_from_messages(messages: List[Dict[str, str]]) -> str:
    chunks = []
    for message in messages:
        if message.get("role") != "user":
            continue
        content = (message.get("content") or "").strip()
        if not content or content.startswith("Salesforce instance output:"):
            continue
        chunks.append(content)
    return "\n".join(chunks)


def can_ask_user(env) -> bool:
    return hasattr(env, "user")
