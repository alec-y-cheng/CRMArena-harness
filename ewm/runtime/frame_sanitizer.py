"""Sanitizers for LLM-compiled workflow frames."""

from typing import Any, List


_PROTOCOL_CONSTRAINT_MARKERS = (
    "react",
    "<thought",
    "</thought",
    "<execute",
    "</execute",
    "<respond",
    "</respond",
    "thought followed",
    "action command",
    "exactly one thought",
    "exactly one action",
    "do not generate system observation",
    "system observation",
    "instanceframe",
    "compile only",
    "do not solve",
    "json object",
    "return exactly one json",
)


def drop_protocol_constraints(constraints: List[Any]) -> List[Any]:
    cleaned = []
    for item in constraints:
        text = str(item or "")
        lowered = text.lower()
        if any(marker in lowered for marker in _PROTOCOL_CONSTRAINT_MARKERS):
            continue
        cleaned.append(item)
    return cleaned
