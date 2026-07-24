import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional


CONFIDENTIALITY_TASKS = {
    "private_customer_information",
    "internal_operation_data",
    "confidential_company_knowledge",
}

SUPPORTED_TASK_FAMILIES = {
    "quote_approval",
    "lead_qualification",
    "case_routing",
    "conversion_rate_comprehension",
    "confidentiality",
    "general",
}


@dataclass(frozen=True)
class RoutingResult:
    task_family: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    mode: str = "deterministic"
    scaffold_used: str = "general"
    oracle_task_label: Optional[str] = None
    route_changed: bool = False

    def as_dict(self) -> dict:
        return {
            "task_family": self.task_family,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "mode": self.mode,
            "scaffold_used": self.scaffold_used,
            "oracle_task_label": self.oracle_task_label,
            "route_changed": self.route_changed,
        }


@dataclass(frozen=True)
class _Rule:
    family: str
    patterns: tuple[str, ...]
    confidence: float


RULES = (
    _Rule(
        "quote_approval",
        (
            r"\bquote\b",
            r"\bapproval\b",
            r"\bapprove\b",
            r"\bdiscount\b",
            r"\bquote line item\b",
            r"\bquote approval\b",
        ),
        0.93,
    ),
    _Rule(
        "lead_qualification",
        (
            r"\blead\b",
            r"\bqualification\b",
            r"\bqualify\b",
            r"\bbant\b",
            r"\bbudget\b",
            r"\bauthority\b",
            r"\btimeline\b",
        ),
        0.9,
    ),
    _Rule(
        "case_routing",
        (
            r"\bcase\b",
            r"\brout(?:e|ing)\b",
            r"\bassign(?:ed|ment)?\b",
            r"\bagent\b",
            r"\bmost suitable\b",
            r"\bsuitable agent\b",
        ),
        0.88,
    ),
    _Rule(
        "conversion_rate_comprehension",
        (
            r"\bconversion rate\b",
            r"\bconverted\b",
            r"\bleads? converted\b",
            r"\bconversion\b",
        ),
        0.88,
    ),
    _Rule(
        "confidentiality",
        (
            r"\bprivate\b",
            r"\bpersonal information\b",
            r"\bconfidential\b",
            r"\binternal operation",
            r"\binternal data\b",
            r"\bnot public\b",
            r"\bprivacy\b",
            r"\bcustomer information\b",
        ),
        0.86,
    ),
)

CONFIDENTIALITY_PRIORITY_PATTERNS = (
    r"\b(private|personal|confidential|privacy|internal)\b",
    r"\b(handle time|transfer counts?|average|total sales|sales amount|top-selling|performance|workload)\b",
    r"\b(highest|lowest|quickest|fastest|largest|poorest|best|top-performing)\b.*\b(agent|sales|conversion|closure|closing|handle|transfer)\b",
    r"\b(agent|case|opportunit(?:y|ies)|lead)s?\b.*\b(highest|lowest|quickest|fastest|largest|poorest|average|total|increase)\b",
    r"\b(past|last|over the last|in the past)\s+\d+\s+(weeks?|months?|quarters?|years?)\b",
    r"\b(q[1-4]|spring|summer|fall|autumn|winter)\s+(?:of\s+)?\d{4}\b",
    r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}\b",
    r"\bconversion rate\b.*\b(agent|lead|quarter|month|spring|summer|fall|winter|year)\b",
    r"\binstallation timeline\b",
    r"\bdiscount\b.{0,40}\b(?:percentage|tier|offered|apply|applies|spending|purchases?)\b",
    r"\bpurchase amount\b",
    r"\border(?:ed|s)?\s+\d+\s+units?\b",
)

TASK_SHAPE_PATTERNS = {
    "quote_approval": (
        r"\bquot(?:e|ation)\b",
        r"\b(company|approval|price|pricing|cost|configuration|setup).{0,50}\b(?:polic(?:y|ies)|guidelines?|rules?|regulations?)\b|\b(?:polic(?:y|ies)|guidelines?|rules?|regulations?).{0,50}\b(price|pricing|cost|configuration|setup)\b",
        r"\bknowledge article\b|\bviolat(?:e|es|ion)|\bbreach(?:es|ing)?\b|\bconflict(?:s|ing)?\b",
        r"\breturn only\b",
    ),
    "lead_qualification": (
        r"\bthis lead\b|\bthe lead\b",
        r"\bqualified\b|\bqualification\b|\bqualify\b",
        r"\bbudget\b.*\bauthority\b.*\bneed\b.*\btimeline\b|\bbant\b",
        r"\breturn only\b",
    ),
    "case_routing": (
        r"\bcase routing policy\b",
        r"\bgiven case\b|##\s*given case\b",
        r"\bmost suitable agent\b|\breturn only the id of the agent\b",
    ),
}


def route_task(
    query: str,
    metadata: Optional[Mapping] = None,
    oracle_task_label: Optional[str] = None,
    mode: str = "deterministic",
    min_confidence: float = 0.55,
) -> RoutingResult:
    if mode == "none":
        return RoutingResult(
            task_family="general",
            confidence=0.0,
            evidence=[],
            mode=mode,
            scaffold_used="general",
            oracle_task_label=oracle_task_label,
        )
    if mode != "deterministic":
        raise ValueError(f"Unsupported routing mode: {mode}")

    result = _deterministic_route(query=query, metadata=metadata, oracle_task_label=oracle_task_label)
    if result.confidence < min_confidence:
        return RoutingResult(
            task_family="confidentiality",
            confidence=result.confidence,
            evidence=result.evidence,
            mode=mode,
            scaffold_used="confidentiality",
            oracle_task_label=oracle_task_label,
            route_changed=result.task_family != "confidentiality",
        )
    return result


def expected_family_from_task_label(task_label: Optional[str]) -> str:
    return _family_from_task_label(task_label)


def _deterministic_route(
    query: str,
    metadata: Optional[Mapping],
    oracle_task_label: Optional[str],
) -> RoutingResult:
    visible_text = _visible_text(query, metadata)
    priority_confidentiality = _matched_patterns(visible_text, CONFIDENTIALITY_PRIORITY_PATTERNS)
    if priority_confidentiality:
        shaped_family = _task_shape_family(visible_text)
        if shaped_family is None:
            return RoutingResult(
                task_family="confidentiality",
                confidence=0.91,
                evidence=priority_confidentiality,
                mode="deterministic",
                scaffold_used="confidentiality",
                oracle_task_label=oracle_task_label,
            )

    shaped_family = _task_shape_family(visible_text)
    if shaped_family:
        evidence = _matched_patterns(visible_text, TASK_SHAPE_PATTERNS[shaped_family])
        return RoutingResult(
            task_family=shaped_family,
            confidence=0.96,
            evidence=evidence,
            mode="deterministic",
            scaffold_used=shaped_family,
            oracle_task_label=oracle_task_label,
        )

    best_family = "confidentiality"
    best_confidence = 0.0
    best_evidence: list[str] = []

    for rule in RULES:
        matches = _matched_patterns(visible_text, rule.patterns)
        if not matches:
            continue
        confidence = min(0.98, rule.confidence + 0.02 * (len(matches) - 1))
        if confidence > best_confidence:
            best_family = rule.family
            best_confidence = confidence
            best_evidence = matches

    if best_family in {"quote_approval", "lead_qualification", "case_routing"}:
        return RoutingResult(
            task_family="confidentiality",
            confidence=min(best_confidence, 0.54),
            evidence=best_evidence,
            mode="deterministic",
            scaffold_used="confidentiality",
            oracle_task_label=oracle_task_label,
            route_changed=True,
        )

    return RoutingResult(
        task_family=best_family,
        confidence=best_confidence,
        evidence=best_evidence,
        mode="deterministic",
        scaffold_used=best_family if best_family in SUPPORTED_TASK_FAMILIES else "general",
        oracle_task_label=oracle_task_label,
    )


def _task_shape_family(text: str) -> Optional[str]:
    for family, patterns in TASK_SHAPE_PATTERNS.items():
        if all(re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL) for pattern in patterns):
            return family
    return None


def _family_from_task_label(task_label: Optional[str]) -> str:
    if not task_label:
        return "general"
    if task_label in CONFIDENTIALITY_TASKS:
        return "confidentiality"
    if task_label in SUPPORTED_TASK_FAMILIES:
        return task_label
    return "general"


def _visible_text(query: str, metadata: Optional[Mapping]) -> str:
    parts = [query or ""]
    if isinstance(metadata, Mapping):
        for key in ("required", "optional"):
            value = metadata.get(key)
            if value:
                parts.append(str(value))
    elif metadata:
        parts.append(str(metadata))
    return "\n".join(parts).lower()


def _matched_patterns(text: str, patterns: Iterable[str]) -> list[str]:
    evidence = []
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            evidence.append(match.group(0))
    return evidence
