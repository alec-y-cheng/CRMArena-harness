"""Shared external-facing router, evidence, and privacy-gate contracts."""

import json
from typing import Any, Dict, List, Optional


EXPECTED_ACTIONS = (
    "query_public_knowledge_articles",
    "query_product_catalog",
    "query_current_customer",
    "query_purchase_history",
    "query_order_history",
    "query_case_status",
    "ask_clarification",
    "refuse",
)

ALLOWED_EVIDENCE_TYPES = (
    "public_product_support",
    "public_warranty_or_returns",
    "public_service_channel",
    "public_troubleshooting",
    "product_catalog",
    "current_customer_profile",
    "current_customer_purchase_history",
    "current_customer_order_history",
    "current_customer_case_status",
)

DISALLOWED_EVIDENCE_TYPES = (
    "other_customer_profile",
    "other_customer_purchase_history",
    "other_customer_case_history",
    "internal_operations_metric",
    "internal_agent_performance",
    "confidential_company_knowledge",
    "internal_sales_policy",
    "internal_quote_policy",
    "lead_qualification_policy",
    "quote_approval_policy",
    "case_routing_policy",
    "non_public_knowledge_article",
    "unknown",
)

ALLOWED_EVIDENCE_CLASSES = (
    "public_knowledge_article",
    "own_customer_profile",
    "own_purchase_history",
    "own_order_history",
    "own_case_status",
) + ALLOWED_EVIDENCE_TYPES
DISALLOWED_EVIDENCE_CLASSES = DISALLOWED_EVIDENCE_TYPES

EXTERNAL_ROUTES = (
    "knowledge_qa",
    "named_entity_disambiguation",
    "clarify",
    "refuse",
    "unsupported",
)

SUBJECT_SCOPES = (
    "public",
    "current_customer",
    "other_customer",
    "internal_company",
    "unknown",
)

DIRECT_REFERENCE_MISSING_TERMS = (
    "customer_identifier",
    "customer identifier",
    "customer id",
    "contact id",
    "contact identifier",
    "order_reference",
    "order reference",
    "order id",
    "order number",
    "reference number",
    "reference code",
    "transaction id",
    "transaction reference",
)


class ExternalRequestRoute:
    """Router output for external-facing requests."""

    def __init__(
        self,
        request_type: str = "unknown",
        route: str = "unsupported",
        expected_actions: Optional[List[str]] = None,
        evidence_required: Optional[List[Dict[str, Any]]] = None,
        subject_scope: str = "unknown",
        clarification_needed: bool = False,
        missing_information: Optional[List[str]] = None,
        disallowed_information: Optional[List[str]] = None,
        reason: str = "",
    ):
        self.request_type = request_type
        self.route = route
        self.expected_actions = expected_actions or []
        self.evidence_required = evidence_required or []
        self.subject_scope = subject_scope
        self.clarification_needed = clarification_needed
        self.missing_information = missing_information or []
        self.disallowed_information = disallowed_information or []
        self.reason = reason

    def as_dict(self) -> Dict[str, Any]:
        return {
            "request_type": self.request_type,
            "route": self.route,
            "expected_actions": list(self.expected_actions),
            "evidence_required": [dict(item) for item in self.evidence_required],
            "subject_scope": self.subject_scope,
            "clarification_needed": self.clarification_needed,
            "missing_information": list(self.missing_information),
            "disallowed_information": list(self.disallowed_information),
            "reason": self.reason,
        }


class GateDecision:
    """Privacy/safety gate decision for intended retrieval or final response."""

    def __init__(
        self,
        allowed: bool,
        reason: str = "",
        blocked_information: Optional[List[str]] = None,
    ):
        self.allowed = allowed
        self.reason = reason
        self.blocked_information = blocked_information or []

    def as_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "blocked_information": list(self.blocked_information),
        }


def classify_external_request_prompt(task_query: str, conversation_text: str) -> str:
    """Build the router prompt for classifying external-facing requests."""
    return """\
Classify the customer's external-facing CRM request into one fixed route and a
coarse evidence plan.

You are not choosing concrete database queries. Identify both:
- expected_actions: the broad symbolic actions that would retrieve the answer.
- evidence_required: the kind of evidence that would be exposed by those
  actions.

The deterministic privacy gate blocks or allows the request from
evidence_required, not from the action names. For example, a knowledge-article
query can expose public support evidence or confidential company evidence; you
must classify the evidence itself.

Routes:
- knowledge_qa: customer asks a public support, product, policy, care, warranty,
  return, availability, or service-channel question answerable from public
  knowledge articles.
- named_entity_disambiguation: customer asks to identify, find, display, or
  resolve a specific product/entity from their own purchases or order history.
- clarify: the request is too vague to safely choose one route or lacks
  essential customer-provided information.
- refuse: the request requires private information about another customer or
  internal/confidential company evidence.
- unsupported: the request is outside the supported CRM external-facing tasks.

Expected action labels:
{expected_actions}

Allowed evidence types:
{allowed_evidence}

Disallowed evidence types:
{disallowed_evidence}

Subject scopes:
{subject_scopes}

Routing guidance:
- For public support questions, use route=knowledge_qa and public evidence
  types.
- For current-customer purchased product lookup, use
  route=named_entity_disambiguation and current-customer purchase/order
  evidence types.
- Use route=refuse when any required evidence item uses a disallowed evidence
  type or unauthorized subject scope.
- If the request names or implies someone other than the logged-in customer,
  classify the evidence under other-customer evidence types unless the
  conversation clearly establishes it is the current customer.
- For current-customer purchased product lookup, use
  route=named_entity_disambiguation if the customer gives enough product,
  purchase, or timeframe context to attempt scoped retrieval.
- Use clarify only when missing information prevents choosing a route or
  classifying the evidence safely.
- Do not invent action labels, evidence types, subject scopes, or routes.

Original task query:
{task_query}

Conversation so far:
{conversation_text}

Return JSON with exactly these keys:
{{
  "request_type": "knowledge_qa|named_entity_disambiguation|confidential_request|unknown",
  "route": "knowledge_qa|named_entity_disambiguation|clarify|refuse|unsupported",
  "expected_actions": ["fixed action label"],
  "evidence_required": [
    {{
      "evidence_type": "fixed evidence type",
      "subject_scope": "public|current_customer|other_customer|internal_company|unknown",
      "reason": "why this evidence is needed"
    }}
  ],
  "subject_scope": "public|current_customer|other_customer|internal_company|unknown",
  "clarification_needed": false,
  "missing_information": [],
  "disallowed_information": ["fixed evidence type"],
  "reason": "short route rationale"
}}
""".format(
        expected_actions=json.dumps(list(EXPECTED_ACTIONS)),
        allowed_evidence=json.dumps(list(ALLOWED_EVIDENCE_TYPES)),
        disallowed_evidence=json.dumps(list(DISALLOWED_EVIDENCE_TYPES)),
        subject_scopes=json.dumps(list(SUBJECT_SCOPES)),
        task_query=task_query.strip(),
        conversation_text=conversation_text.strip(),
    )


def evaluate_intended_retrieval(
    evidence_required: List[Dict[str, Any]],
    subject_scope: str,
) -> GateDecision:
    """Decide whether a planned retrieval is allowed for the external requester."""
    blocked = []
    unknown = []
    for item in evidence_required:
        if isinstance(item, dict):
            evidence_type = str(item.get("evidence_type") or "").strip()
            item_scope = str(item.get("subject_scope") or subject_scope or "").strip()
        else:
            evidence_type = str(item or "").strip()
            item_scope = str(subject_scope or "").strip()
        if evidence_type in DISALLOWED_EVIDENCE_CLASSES:
            blocked.append(evidence_type)
        elif evidence_type not in ALLOWED_EVIDENCE_CLASSES:
            unknown.append(evidence_type or "unknown")
        if item_scope in ("other_customer", "internal_company"):
            blocked.append("{}:{}".format(evidence_type or "unknown", item_scope))
        elif item_scope not in SUBJECT_SCOPES:
            unknown.append("{}:{}".format(evidence_type or "unknown", item_scope))
    if unknown:
        return GateDecision(
            allowed=False,
            reason="Unknown evidence types or scopes: {}".format(", ".join(sorted(set(unknown)))),
            blocked_information=sorted(set(unknown)),
        )
    if blocked:
        return GateDecision(
            allowed=False,
            reason="External customer request requires disallowed evidence.",
            blocked_information=sorted(set(blocked)),
        )
    if subject_scope in ("other_customer", "internal_company"):
        return GateDecision(
            allowed=False,
            reason="External customer is not authorized for subject scope: {}".format(
                subject_scope
            ),
            blocked_information=[
                _evidence_required_type(item) for item in evidence_required
            ],
        )
    if subject_scope not in SUBJECT_SCOPES:
        return GateDecision(
            allowed=False,
            reason="Unknown subject scope: {}".format(subject_scope),
            blocked_information=[
                _evidence_required_type(item) for item in evidence_required
            ],
        )
    return GateDecision(
        allowed=True,
        reason="Evidence types are allowed for route-level external access.",
    )


def _evidence_required_type(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("evidence_type") or "unknown")
    return str(item or "unknown")


def evaluate_retrieved_evidence(evidence_class: str, records: List[Dict[str, Any]]) -> GateDecision:
    """Gate retrieved records before passing them into extraction/final answer logic."""
    if evidence_class in DISALLOWED_EVIDENCE_CLASSES:
        return GateDecision(
            allowed=False,
            reason="Retrieved evidence class is disallowed for external users.",
            blocked_information=[evidence_class],
        )
    if evidence_class not in ALLOWED_EVIDENCE_CLASSES:
        return GateDecision(
            allowed=False,
            reason="Unknown retrieved evidence class: {}".format(evidence_class),
            blocked_information=[evidence_class],
        )
    return GateDecision(
        allowed=True,
        reason="Retrieved evidence class is allowed at the shared external-router level.",
    )


def evaluate_final_response(answer: str, evidence_classes: List[str]) -> GateDecision:
    """Gate the final customer-facing response before responding."""
    blocked = [
        label for label in evidence_classes if label in DISALLOWED_EVIDENCE_CLASSES
    ]
    if blocked:
        return GateDecision(
            allowed=False,
            reason="Final response depends on disallowed evidence.",
            blocked_information=blocked,
        )
    unknown = [
        label
        for label in evidence_classes
        if label not in ALLOWED_EVIDENCE_CLASSES and label not in DISALLOWED_EVIDENCE_CLASSES
    ]
    if unknown:
        return GateDecision(
            allowed=False,
            reason="Final response cites unknown evidence classes: {}".format(
                ", ".join(unknown)
            ),
            blocked_information=unknown,
        )
    return GateDecision(
        allowed=True,
        reason="Final response cites only allowed external evidence classes.",
    )


def respond_to_user(missing_information: List[str]) -> str:
    """Render a concise external-facing clarification question."""
    if _only_direct_reference_missing(missing_information):
        return (
            "Could you share the product type, item description, and when you "
            "purchased it so I can look for the right purchase?"
        )
    missing_values = _customer_facing_missing_information(missing_information)
    missing = ", ".join(item for item in missing_values if item)
    if missing:
        return "Could you clarify {} so I can help with the right request?".format(
            missing
        )
    return "Could you clarify what information you need help with?"


def should_fallback_to_ned_from_clarify(route: ExternalRequestRoute) -> bool:
    """Return true when clarification asks only for avoidable references."""
    if route.route != "clarify":
        return False
    if route.request_type == "named_entity_disambiguation":
        return True
    actions = set(route.expected_actions)
    ned_actions = {"query_purchase_history", "query_order_history", "query_product_catalog"}
    evidence_types = {
        str(item.get("evidence_type") or "") for item in route.evidence_required
    }
    ned_evidence = {
        "current_customer_purchase_history",
        "current_customer_order_history",
        "product_catalog",
    }
    return (
        bool(actions.intersection(ned_actions) or evidence_types.intersection(ned_evidence))
        and _only_direct_reference_missing(
        route.missing_information
        )
    )


def _customer_facing_missing_information(missing_information: List[str]) -> List[str]:
    """Drop internal/reference identifiers from clarification text."""
    cleaned = []
    for item in missing_information:
        text = str(item or "").strip()
        if not text or _is_direct_reference_missing(text):
            continue
        cleaned.append(text)
    return cleaned


def _only_direct_reference_missing(missing_information: List[str]) -> bool:
    values = [str(item or "").strip() for item in missing_information if str(item or "").strip()]
    return bool(values) and all(_is_direct_reference_missing(value) for value in values)


def _is_direct_reference_missing(value: str) -> bool:
    normalized = value.replace("_", " ").replace("-", " ").lower()
    normalized = " ".join(normalized.split())
    return any(
        term.replace("_", " ") in normalized
        for term in DIRECT_REFERENCE_MISSING_TERMS
    )


def render_refusal(reason: str) -> str:
    """Render a concise customer-facing refusal."""
    return (
        "I can't help with that request because it would require sharing private "
        "or confidential information."
    )


def render_unavailable_response() -> str:
    """Render a concise response when safe clarification is exhausted."""
    return (
        "I can't provide that information based on the details available. "
        "I would need a safe, customer-scoped request before I can continue."
    )
