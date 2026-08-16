"""Normalize MCP observations into EWM observations and evidence items."""

from typing import List

from ewm.ir.state import EvidenceItem, Observation

from .client import MCPCall, MCPObservation


def normalize_observation(call: MCPCall, observation: MCPObservation) -> List[EvidenceItem]:
    """Create coarse evidence items from an MCP observation.

    Later phases should specialize normalization by tool type while preserving
    this generic fallback.
    """

    obs_id = call.call_id or "obs_{}".format(call.name)
    if not observation.ok:
        return []
    return [
        EvidenceItem(
            evidence_id="ev_{}".format(obs_id),
            source_observation_id=obs_id,
            content=observation.payload,
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
    )

