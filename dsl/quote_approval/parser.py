"""Parsers and validators for quote approval DSL outputs."""

import json
import re
from typing import Any, Dict, List, Mapping, Optional

from dsl.quote_approval.actions import (
    ArticleExtraction,
    ArticlePolicyJudgment,
    DiscountPolicyStructure,
    DiscountPolicyTier,
    KNOWLEDGE_ID_PATTERN,
    PolicySearchIntent,
)
from dsl.quote_approval.prompts import QUOTE_POLICY_DIMENSIONS


ARTICLE_JUDGMENT_STATUSES = ("violated", "not_violated", "unknown")
DISCOUNT_POLICY_TYPES = ("volume_discount", "discount_approval", "not_discount_policy", "unknown")
DISCOUNT_POLICY_BASES = ("quote_total", "total_quantity", "line_quantity", "unknown")
DISCOUNT_POLICY_APPLICATIONS = ("expected", "maximum", "minimum", "unknown")
DISCOUNT_POLICY_SCOPES = ("quote", "line_item", "product", "unknown")
DISCOUNT_POLICY_CONFIDENCES = ("high", "medium", "low", "unknown")
COMPARISON_OPERATORS = (">", ">=", "=", "<", "<=")


class QuoteApprovalParseError(ValueError):
    pass


def parse_policy_search_plan_json(text: str) -> List[PolicySearchIntent]:
    """Parse strict policy-search planning JSON into validated search intents."""

    payload = _load_json_object(text, "policy search plan")
    searches = payload.get("searches")
    if not isinstance(searches, list):
        raise QuoteApprovalParseError("searches must be a list")

    parsed = []
    for index, raw_search in enumerate(searches):
        if not isinstance(raw_search, Mapping):
            raise QuoteApprovalParseError("searches[{}] must be an object".format(index))
        dimension = _enum(
            raw_search.get("dimension"),
            "searches[{}].dimension".format(index),
            QUOTE_POLICY_DIMENSIONS,
        )
        terms = _string_list(raw_search.get("terms"), "searches[{}].terms".format(index))
        if not terms:
            raise QuoteApprovalParseError("searches[{}].terms cannot be empty".format(index))
        reason = _optional_string(raw_search.get("reason"), "searches[{}].reason".format(index))
        parsed.append(PolicySearchIntent(dimension, terms, reason))
    return parsed


def parse_article_json(
    text: str,
    allowed_article_ids: Optional[Any] = None,
) -> ArticleExtraction:
    """Parse strict article extraction JSON into a validated ArticleExtraction."""

    allowed = set(allowed_article_ids or [])
    payload = _load_json_object(text, "article extraction")
    selected = _optional_article_id(payload.get("selected_article_id"), "selected_article_id")
    if selected and allowed and selected not in allowed:
        raise QuoteApprovalParseError("selected_article_id was not in candidate articles")

    raw_judgments = payload.get("judgments", [])
    if not isinstance(raw_judgments, list):
        raise QuoteApprovalParseError("judgments must be a list")
    judgments = []
    for index, raw_judgment in enumerate(raw_judgments):
        if not isinstance(raw_judgment, Mapping):
            raise QuoteApprovalParseError("judgments[{}] must be an object".format(index))
        article_id = _required_article_id(
            raw_judgment.get("article_id"),
            "judgments[{}].article_id".format(index),
        )
        if allowed and article_id not in allowed:
            raise QuoteApprovalParseError(
                "judgments[{}].article_id was not in candidate articles".format(index)
            )
        dimension = _enum(
            raw_judgment.get("dimension"),
            "judgments[{}].dimension".format(index),
            QUOTE_POLICY_DIMENSIONS,
        )
        status = _enum(
            raw_judgment.get("status"),
            "judgments[{}].status".format(index),
            ARTICLE_JUDGMENT_STATUSES,
        )
        rule_summary = _optional_string(
            raw_judgment.get("rule_summary"),
            "judgments[{}].rule_summary".format(index),
        )
        evidence = _optional_string(
            raw_judgment.get("evidence"),
            "judgments[{}].evidence".format(index),
        )
        judgments.append(
            ArticlePolicyJudgment(article_id, dimension, status, rule_summary, evidence)
        )

    additional_searches = []
    raw_additional = payload.get("additional_searches", [])
    if raw_additional in (None, ""):
        raw_additional = []
    if not isinstance(raw_additional, list):
        raise QuoteApprovalParseError("additional_searches must be a list")
    for index, raw_search in enumerate(raw_additional):
        if not isinstance(raw_search, Mapping):
            raise QuoteApprovalParseError(
                "additional_searches[{}] must be an object".format(index)
            )
        dimension = _enum(
            raw_search.get("dimension"),
            "additional_searches[{}].dimension".format(index),
            QUOTE_POLICY_DIMENSIONS,
        )
        terms = _string_list(
            raw_search.get("terms"),
            "additional_searches[{}].terms".format(index),
        )
        if not terms:
            continue
        reason = _optional_string(
            raw_search.get("reason"),
            "additional_searches[{}].reason".format(index),
        )
        additional_searches.append(PolicySearchIntent(dimension, terms, reason))

    return ArticleExtraction(
        selected_article_id=selected,
        judgments=judgments,
        additional_searches=additional_searches,
    )


def parse_discount_policy_structure_json(
    text: str,
    allowed_article_ids: Optional[Any] = None,
) -> DiscountPolicyStructure:
    payload = _load_json_object(text, "discount policy structure")
    allowed = set(allowed_article_ids or [])
    article_id = _required_article_id(payload.get("article_id"), "article_id")
    if allowed and article_id not in allowed:
        raise QuoteApprovalParseError("article_id was not in candidate articles")
    policy_type = _enum(payload.get("policy_type"), "policy_type", DISCOUNT_POLICY_TYPES)
    basis = _enum(payload.get("basis"), "basis", DISCOUNT_POLICY_BASES)
    application = _enum(
        payload.get("application"),
        "application",
        DISCOUNT_POLICY_APPLICATIONS,
    )
    scope = _enum(payload.get("scope"), "scope", DISCOUNT_POLICY_SCOPES)
    confidence = _enum(
        payload.get("rule_confidence"),
        "rule_confidence",
        DISCOUNT_POLICY_CONFIDENCES,
    )
    notes = _optional_string(payload.get("notes"), "notes")

    raw_tiers = payload.get("tiers", [])
    if raw_tiers in (None, ""):
        raw_tiers = []
    if not isinstance(raw_tiers, list):
        raise QuoteApprovalParseError("tiers must be a list")
    tiers = []
    for index, raw_tier in enumerate(raw_tiers):
        if not isinstance(raw_tier, Mapping):
            raise QuoteApprovalParseError("tiers[{}] must be an object".format(index))
        threshold = _number(raw_tier.get("threshold"), "tiers[{}].threshold".format(index))
        discount_percent = _number(
            raw_tier.get("discount_percent"),
            "tiers[{}].discount_percent".format(index),
        )
        operator = _enum(
            raw_tier.get("operator"),
            "tiers[{}].operator".format(index),
            COMPARISON_OPERATORS,
        )
        tiers.append(
            DiscountPolicyTier(
                threshold=threshold,
                discount_percent=discount_percent,
                operator=operator,
            )
        )

    return DiscountPolicyStructure(
        article_id=article_id,
        policy_type=policy_type,
        basis=basis,
        application=application,
        scope=scope,
        tiers=tiers,
        rule_confidence=confidence,
        notes=notes,
    )


def _load_json_object(text: str, label: str) -> Mapping[str, Any]:
    content = _extract_json_text(text or "")
    if not content:
        raise QuoteApprovalParseError("No JSON object found in {}".format(label))
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise QuoteApprovalParseError("Malformed {} JSON: {}".format(label, exc)) from exc
    if not isinstance(payload, Mapping):
        raise QuoteApprovalParseError("{} output must be a JSON object".format(label))
    return payload


def _extract_json_text(text: str) -> str:
    stripped = _strip_think_blocks(text).strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    decoder = json.JSONDecoder()
    candidates = []
    for match in re.finditer(r"\{", stripped):
        try:
            payload, end = decoder.raw_decode(stripped[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            candidates.append(stripped[match.start() : match.start() + end])
    if not candidates:
        return ""
    return max(candidates, key=len)


def _strip_think_blocks(text: str) -> str:
    return re.sub(r"<think\b[^>]*>.*?</think>", "", text or "", flags=re.IGNORECASE | re.DOTALL)


def _string_list(value: Any, field_name: str) -> List[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise QuoteApprovalParseError("{} must be a list".format(field_name))
    result = []
    for item in value:
        if not isinstance(item, str):
            raise QuoteApprovalParseError("{} items must be strings".format(field_name))
        cleaned = " ".join(item.split())
        if cleaned:
            result.append(cleaned)
    return result


def _optional_string(value: Any, field_name: str) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        raise QuoteApprovalParseError("{} must be a string".format(field_name))
    return " ".join(value.split())


def _enum(value: Any, field_name: str, allowed_values: Any) -> str:
    if not isinstance(value, str):
        raise QuoteApprovalParseError("{} must be a string".format(field_name))
    normalized = value.strip().lower()
    if normalized not in allowed_values:
        raise QuoteApprovalParseError("Invalid {}: {}".format(field_name, value))
    return normalized


def _number(value: Any, field_name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise QuoteApprovalParseError("{} must be a number".format(field_name))
    return float(value)


def _optional_article_id(value: Any, field_name: str) -> Optional[str]:
    if value in (None, ""):
        return None
    if isinstance(value, str) and value.strip().lower() == "none":
        return None
    return _required_article_id(value, field_name)


def _required_article_id(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not KNOWLEDGE_ID_PATTERN.fullmatch(value.strip()):
        raise QuoteApprovalParseError("Invalid {}: {}".format(field_name, value))
    return value.strip()
