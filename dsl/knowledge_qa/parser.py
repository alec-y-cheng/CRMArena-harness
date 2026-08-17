"""Parsers for knowledge_qa DSL outputs."""

import json
import re
from typing import Any, List

from dsl.external_facing.actions import (
    ALLOWED_EVIDENCE_TYPES,
    DISALLOWED_EVIDENCE_TYPES,
    SUBJECT_SCOPES,
)
from dsl.knowledge_qa.actions import (
    ANSWER_SPAN_RELEVANCE,
    QUESTION_TYPES,
    KnowledgeQAAnswer,
    KnowledgeQAAnswerSpan,
    KnowledgeQAArticleEvidence,
    KnowledgeQASearchPlan,
)


class KnowledgeQAParseError(ValueError):
    pass


def parse_knowledge_search_plan_json(text: str) -> KnowledgeQASearchPlan:
    """Parse strict search-plan JSON."""
    data = _loads_object(text)
    required = [
        "normalized_question",
        "search_terms",
        "product_terms",
        "clarification_needed",
        "clarification_requirements",
    ]
    _require_keys(data, required)
    return KnowledgeQASearchPlan(
        normalized_question=_as_string(data["normalized_question"], "normalized_question"),
        search_terms=_string_list(data["search_terms"], "search_terms"),
        product_terms=_string_list(data["product_terms"], "product_terms"),
        clarification_needed=_as_bool(data["clarification_needed"], "clarification_needed"),
        clarification_requirements=_string_list(data["clarification_requirements"], "clarification_requirements"),
    )


def parse_knowledge_article_evidence_json(
    text: str,
    allowed_article_ids: List[str],
) -> List[KnowledgeQAArticleEvidence]:
    """Parse strict article-evidence classification JSON."""
    data = _loads_object(text)
    _require_keys(data, ["article_evidence"])
    value = data["article_evidence"]
    if not isinstance(value, list):
        raise KnowledgeQAParseError("article_evidence must be a list")
    allowed = set(allowed_article_ids)
    seen = set()
    out = []
    for index, item in enumerate(value):
        field = "article_evidence[{}]".format(index)
        if not isinstance(item, dict):
            raise KnowledgeQAParseError("{} must be an object".format(field))
        _require_keys(
            item,
            ["article_id", "evidence_type", "subject_scope", "safe_to_use", "reason"],
        )
        article_id = _as_string(item["article_id"], "{}.article_id".format(field))
        if article_id not in allowed:
            raise KnowledgeQAParseError(
                "{}.article_id was not retrieved: {}".format(field, article_id)
            )
        if article_id in seen:
            raise KnowledgeQAParseError(
                "article_evidence contains duplicate article id: {}".format(article_id)
            )
        seen.add(article_id)
        out.append(
            KnowledgeQAArticleEvidence(
                article_id=article_id,
                evidence_type=validate_article_evidence_type(item["evidence_type"]),
                subject_scope=validate_article_subject_scope(item["subject_scope"]),
                safe_to_use=_as_bool(item["safe_to_use"], "{}.safe_to_use".format(field)),
                reason=_as_string(item["reason"], "{}.reason".format(field)),
            )
        )
    return out


def parse_knowledge_answer_json(text: str, allowed_article_ids: List[str]) -> KnowledgeQAAnswer:
    """Parse strict grounded-answer JSON and validate selected article ids."""
    data = _loads_object(text)
    _require_keys(
        data,
        [
            "question_type",
            "asked_focus",
            "candidate_answer_spans",
            "answer",
            "selected_article_ids",
            "evidence",
            "confidence",
        ],
    )
    question_type = validate_question_type(data["question_type"])
    allowed = set(allowed_article_ids)
    candidate_answer_spans = _answer_spans(
        data["candidate_answer_spans"],
        allowed_article_ids=allowed,
    )
    selected_article_ids = _string_list(data["selected_article_ids"], "selected_article_ids")
    unknown = [article_id for article_id in selected_article_ids if article_id not in allowed]
    if unknown:
        raise KnowledgeQAParseError(
            "selected_article_ids contains ids that were not retrieved: {}".format(
                ", ".join(unknown)
            )
        )
    answer = _as_string(data["answer"], "answer")
    included_direct = [
        span for span in candidate_answer_spans if span.include and span.relevance == "direct"
    ]
    if included_direct and _is_none_answer(answer):
        raise KnowledgeQAParseError(
            "answer cannot be None when candidate_answer_spans include direct evidence"
        )
    if _is_none_answer(answer) and selected_article_ids:
        raise KnowledgeQAParseError("selected_article_ids must be empty when answer is None")
    if answer and not _is_none_answer(answer):
        if not included_direct:
            raise KnowledgeQAParseError(
                "non-None answer requires at least one included direct candidate span"
            )
        if question_type == "yes_no" and _is_bare_yes_no(answer) and _direct_spans_have_context(included_direct):
            raise KnowledgeQAParseError(
                "yes_no answer must include the shortest supporting reason or condition"
            )
        if allowed and not selected_article_ids:
            raise KnowledgeQAParseError(
                "selected_article_ids cannot be empty when answer is supported by retrieved articles"
            )
        direct_article_ids = set(
            span.article_id for span in included_direct if span.article_id
        )
        missing_direct_ids = [
            article_id
            for article_id in sorted(direct_article_ids)
            if article_id not in selected_article_ids
        ]
        if missing_direct_ids:
            raise KnowledgeQAParseError(
                "selected_article_ids must include direct span article ids: {}".format(
                    ", ".join(missing_direct_ids)
                )
            )
    return KnowledgeQAAnswer(
        question_type=question_type,
        asked_focus=_as_string(data["asked_focus"], "asked_focus"),
        candidate_answer_spans=candidate_answer_spans,
        answer=answer,
        selected_article_ids=selected_article_ids,
        evidence=_as_string(data["evidence"], "evidence"),
        confidence=validate_confidence(data["confidence"]),
    )


def extract_json_object(text: str) -> str:
    """Extract the largest JSON object from noisy model output."""
    cleaned = _strip_thinking(text or "")
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fenced:
        return fenced.group(1)

    start = cleaned.find("{")
    if start < 0:
        raise KnowledgeQAParseError("No JSON object found")

    depth = 0
    in_string = False
    escaped = False
    best = None
    for index in range(start, len(cleaned)):
        char = cleaned[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                best = cleaned[start : index + 1]
                break
            if depth < 0:
                break
    if not best:
        raise KnowledgeQAParseError("Unbalanced JSON object")
    return best


def validate_article_evidence_type(value: Any) -> str:
    """Validate fixed external evidence type labels for KQA article evidence."""
    if not isinstance(value, str):
        raise KnowledgeQAParseError("article evidence_type must be a string")
    normalized = value.strip()
    allowed = set(ALLOWED_EVIDENCE_TYPES + DISALLOWED_EVIDENCE_TYPES)
    if normalized not in allowed:
        raise KnowledgeQAParseError("Invalid article evidence_type: {}".format(value))
    return normalized


def validate_article_subject_scope(value: Any) -> str:
    """Validate fixed subject-scope labels for KQA article evidence."""
    if not isinstance(value, str):
        raise KnowledgeQAParseError("article subject_scope must be a string")
    normalized = value.strip()
    if normalized not in SUBJECT_SCOPES:
        raise KnowledgeQAParseError("Invalid article subject_scope: {}".format(value))
    return normalized


def validate_confidence(value: Any) -> str:
    """Validate answer confidence label."""
    if not isinstance(value, str):
        raise KnowledgeQAParseError("confidence must be a string")
    normalized = value.strip().lower()
    if normalized not in ("high", "medium", "low", "unknown"):
        raise KnowledgeQAParseError("Invalid confidence: {}".format(value))
    return normalized


def validate_question_type(value: Any) -> str:
    """Validate the normalized customer question type."""
    if not isinstance(value, str):
        raise KnowledgeQAParseError("question_type must be a string")
    normalized = value.strip().lower()
    if normalized not in QUESTION_TYPES:
        raise KnowledgeQAParseError("Invalid question_type: {}".format(value))
    return normalized


def validate_span_relevance(value: Any) -> str:
    """Validate candidate answer span relevance."""
    if not isinstance(value, str):
        raise KnowledgeQAParseError("candidate span relevance must be a string")
    normalized = value.strip().lower()
    if normalized not in ANSWER_SPAN_RELEVANCE:
        raise KnowledgeQAParseError("Invalid candidate span relevance: {}".format(value))
    return normalized


def _loads_object(text: str) -> dict:
    try:
        parsed = json.loads(extract_json_object(text))
    except json.JSONDecodeError as exc:
        raise KnowledgeQAParseError("Invalid JSON: {}".format(exc))
    if not isinstance(parsed, dict):
        raise KnowledgeQAParseError("Expected a JSON object")
    return parsed


def _require_keys(data: dict, keys: List[str]) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise KnowledgeQAParseError("Missing keys: {}".format(", ".join(missing)))


def _as_string(value: Any, field: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise KnowledgeQAParseError("{} must be a string".format(field))
    return value.strip()


def _as_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise KnowledgeQAParseError("{} must be a boolean".format(field))
    return value


def _string_list(value: Any, field: str) -> List[str]:
    if not isinstance(value, list):
        raise KnowledgeQAParseError("{} must be a list".format(field))
    out = []
    for item in value:
        if not isinstance(item, str):
            raise KnowledgeQAParseError("{} must contain only strings".format(field))
        cleaned = item.strip()
        if cleaned:
            out.append(cleaned)
    return out


def _answer_spans(value: Any, allowed_article_ids: set) -> List[KnowledgeQAAnswerSpan]:
    if not isinstance(value, list):
        raise KnowledgeQAParseError("candidate_answer_spans must be a list")
    if len(value) > 8:
        raise KnowledgeQAParseError("candidate_answer_spans must contain at most 8 spans")
    spans = []
    for index, item in enumerate(value):
        field = "candidate_answer_spans[{}]".format(index)
        if not isinstance(item, dict):
            raise KnowledgeQAParseError("{} must be an object".format(field))
        _require_keys(item, ["span", "relevance", "include", "article_id", "reason"])
        span_text = _as_string(item["span"], "{}.span".format(field))
        if not span_text:
            raise KnowledgeQAParseError("{}.span cannot be empty".format(field))
        relevance = validate_span_relevance(item["relevance"])
        include = _as_bool(item["include"], "{}.include".format(field))
        article_id = _as_string(item["article_id"], "{}.article_id".format(field))
        if article_id and article_id not in allowed_article_ids:
            raise KnowledgeQAParseError(
                "{}.article_id was not retrieved: {}".format(field, article_id)
            )
        if include and relevance != "direct":
            raise KnowledgeQAParseError(
                "{} cannot be included unless relevance is direct".format(field)
            )
        spans.append(
            KnowledgeQAAnswerSpan(
                span=span_text,
                relevance=relevance,
                include=include,
                article_id=article_id,
                reason=_as_string(item["reason"], "{}.reason".format(field)),
            )
        )
    return spans


def _is_none_answer(answer: str) -> bool:
    return not answer.strip() or answer.strip().lower() == "none"


def _is_bare_yes_no(answer: str) -> bool:
    return answer.strip().lower().rstrip(".") in ("yes", "no")


def _direct_spans_have_context(spans: List[KnowledgeQAAnswerSpan]) -> bool:
    for span in spans:
        words = re.findall(r"[A-Za-z0-9]+", span.span)
        if len(words) > 3:
            return True
    return False


def _strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
