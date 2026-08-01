"""Actions and state helpers for named_entity_disambiguation."""

import calendar
import json
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


PRODUCT_FIELDS = ("Id", "Name", "Description")
CONTACT_FIELDS = ("Id", "AccountId")
ORDER_ITEM_FIELDS = ("Id", "OrderId", "Product2Id", "Quantity", "UnitPrice")
PERIOD_UNITS = ("day", "week", "month", "quarter", "unknown")
GENERIC_ENTITY_PHRASES = (
    "",
    "it",
    "item",
    "product",
    "purchase",
    "transaction",
    "order",
    "thing",
)


class NEDExtraction:
    """Semantic slots for customer-facing entity disambiguation."""

    def __init__(
        self,
        entity_phrase: str = "",
        product_terms: Optional[List[str]] = None,
        date_expression: str = "",
        period: str = "unknown",
        interval_count: int = 0,
        exact_purchase_date: str = "",
        attributes: Optional[List[str]] = None,
        clarification_needed: bool = False,
        missing_information: Optional[List[str]] = None,
    ):
        self.entity_phrase = entity_phrase
        self.product_terms = product_terms or []
        self.date_expression = date_expression
        self.period = period
        self.interval_count = interval_count
        self.exact_purchase_date = exact_purchase_date
        self.attributes = attributes or []
        self.clarification_needed = clarification_needed
        self.missing_information = missing_information or []

    def as_dict(self) -> Dict[str, Any]:
        return {
            "entity_phrase": self.entity_phrase,
            "product_terms": list(self.product_terms),
            "date_expression": self.date_expression,
            "period": self.period,
            "interval_count": self.interval_count,
            "exact_purchase_date": self.exact_purchase_date,
            "attributes": list(self.attributes),
            "clarification_needed": self.clarification_needed,
            "missing_information": list(self.missing_information),
        }


class NEDCandidateSelection:
    """Selected product/entity candidate from retrieved customer purchase evidence."""

    def __init__(
        self,
        selected_product_id: Optional[str] = None,
        evidence: str = "",
        confidence: str = "unknown",
        ambiguous: bool = False,
        missing_information: Optional[List[str]] = None,
    ):
        self.selected_product_id = selected_product_id
        self.evidence = evidence
        self.confidence = confidence
        self.ambiguous = ambiguous
        self.missing_information = missing_information or []

    def as_dict(self) -> Dict[str, Any]:
        return {
            "selected_product_id": self.selected_product_id,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "ambiguous": self.ambiguous,
            "missing_information": list(self.missing_information),
        }


class NamedEntityDisambiguationState:
    """Runtime state for the NED workflow."""

    def __init__(self):
        self.customer_id: Optional[str] = None
        self.account_id: Optional[str] = None
        self.today: str = ""
        self.extraction: Optional[NEDExtraction] = None
        self.date_window: Optional[Tuple[str, str]] = None
        self.customer_records: List[Dict[str, Any]] = []
        self.purchase_records: List[Dict[str, Any]] = []
        self.product_candidates: List[Dict[str, Any]] = []
        self.selection: Optional[NEDCandidateSelection] = None
        self.final_product_id: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "account_id": self.account_id,
            "today": self.today,
            "extraction": self.extraction.as_dict() if self.extraction else None,
            "date_window": list(self.date_window) if self.date_window else None,
            "customer_records": [dict(record) for record in self.customer_records],
            "purchase_records": [dict(record) for record in self.purchase_records],
            "product_candidates": [dict(record) for record in self.product_candidates],
            "selection": self.selection.as_dict() if self.selection else None,
            "final_product_id": self.final_product_id,
        }


def extract_ned_slots_prompt(task_query: str, conversation_text: str, today: str) -> str:
    """Build prompt for entity phrase/date/product slot extraction."""
    return """\
Extract customer-facing product/entity lookup slots for named entity
disambiguation.

The symbolic layer will use these slots only to compile deterministic Salesforce
queries. Do not write SQL or SOSL.

Slot guidance:
- Use the most specific product/entity phrase and purchase-time expression from
  the conversation. If the customer only says generic words like "purchase",
  "item", or "order", mark clarification_needed=true and ask for the product
  kind or distinguishing attributes.
- entity_phrase is the customer's natural-language product/entity reference.
- product_terms should be concise Product2 search phrases. Prefer the product
  kind and distinctive modifiers the customer gave.
- date_expression is the exact purchase-time phrase from the conversation.
- If the date means N days/weeks/months/quarters before today, set period and
  interval_count. Examples: "one week ago" -> week/1; "last month" -> month/1;
  "fourteen days ago" -> day/14.
- If the customer gives an absolute purchase date, put it in exact_purchase_date
  as YYYY-MM-DD and set period to unknown.
- Mark clarification_needed only when the product/entity phrase or purchase
  time is missing enough that deterministic retrieval would be meaningless.

Today:
{today}

Original task query:
{task_query}

Conversation so far:
{conversation_text}

Return JSON with exactly these keys:
{{
  "entity_phrase": "customer's product/entity reference",
  "product_terms": ["concise product search phrase"],
  "date_expression": "purchase-time phrase",
  "period": "day|week|month|quarter|unknown",
  "interval_count": 1,
  "exact_purchase_date": "",
  "attributes": ["visible product attributes if any"],
  "clarification_needed": false,
  "missing_information": []
}}
""".format(
        today=today.strip(),
        task_query=task_query.strip(),
        conversation_text=conversation_text.strip(),
    )


def normalize_purchase_date_window(
    extraction: NEDExtraction,
    today: str,
) -> Optional[Tuple[str, str]]:
    """Convert extracted purchase date slots to an inclusive date window."""
    if extraction.exact_purchase_date:
        exact = _parse_date(extraction.exact_purchase_date)
        return (exact, exact) if exact else None

    today_date = _parse_date(today)
    if not today_date:
        return None
    if extraction.period not in ("day", "week", "month", "quarter"):
        return None
    if extraction.interval_count < 0:
        return None

    base = datetime.strptime(today_date, "%Y-%m-%d")
    if extraction.period == "day":
        target = base - timedelta(days=extraction.interval_count)
    elif extraction.period == "week":
        target = base - timedelta(weeks=extraction.interval_count)
    elif extraction.period == "month":
        target = _add_months(base, -extraction.interval_count)
    else:
        target = _add_months(base, -(3 * extraction.interval_count))
    date_text = target.strftime("%Y-%m-%d")
    return (date_text, date_text)


def query_current_customer(customer_id: str) -> Optional[str]:
    """Compile contact lookup query for the scoped current customer."""
    customer_id = sanitize_id(customer_id)
    if not customer_id:
        return None
    return "SELECT {fields} FROM Contact WHERE Id = '{customer_id}' LIMIT 1".format(
        fields=", ".join(CONTACT_FIELDS),
        customer_id=customer_id,
    )


def query_product_catalog(product_terms: List[str]) -> Optional[str]:
    """Compile Product2 SOSL search query from LLM-provided product terms."""
    term = sanitize_search_term(product_terms)
    if not term:
        return None
    return "FIND {{{term}}} IN ALL FIELDS RETURNING Product2({fields})".format(
        term=term,
        fields=", ".join(PRODUCT_FIELDS),
    )


def query_products_by_ids(product_ids: List[str]) -> Optional[str]:
    """Compile Product2 lookup for purchased product ids."""
    safe_product_ids = [sanitize_id(product_id) for product_id in product_ids]
    safe_product_ids = [product_id for product_id in safe_product_ids if product_id]
    if not safe_product_ids:
        return None
    quoted = ", ".join("'{}'".format(product_id) for product_id in sorted(set(safe_product_ids)))
    return "SELECT {fields} FROM Product2 WHERE Id IN ({ids})".format(
        fields=", ".join(PRODUCT_FIELDS),
        ids=quoted,
    )


def query_purchase_history(
    account_id: str,
    date_window: Optional[Tuple[str, str]],
    product_ids: Optional[List[str]] = None,
) -> Optional[str]:
    """Compile customer-scoped activated OrderItem purchase history query."""
    account_id = sanitize_id(account_id)
    if not account_id or not date_window:
        return None
    start_date, end_date = date_window
    conditions = [
        "OrderId IN (SELECT Id FROM Order WHERE AccountId = '{account_id}' AND Status = 'Activated' AND EffectiveDate >= {start_date} AND EffectiveDate <= {end_date})".format(
            account_id=account_id,
            start_date=start_date,
            end_date=end_date,
        )
    ]
    safe_product_ids = [sanitize_id(product_id) for product_id in (product_ids or [])]
    safe_product_ids = [product_id for product_id in safe_product_ids if product_id]
    if safe_product_ids:
        quoted = ", ".join("'{}'".format(product_id) for product_id in safe_product_ids)
        conditions.append("Product2Id IN ({})".format(quoted))
    return "SELECT {fields} FROM OrderItem WHERE {where}".format(
        fields=", ".join(ORDER_ITEM_FIELDS),
        where=" AND ".join(conditions),
    )


def select_ned_candidate_prompt(
    extraction: NEDExtraction,
    date_window: Optional[Tuple[str, str]],
    purchase_records: List[Dict[str, Any]],
    product_candidates: List[Dict[str, Any]],
) -> str:
    """Build prompt for selecting the best eligible Product2.Id."""
    return """\
Select the Product2.Id that best matches the customer's named-entity lookup.

Use only eligible current-customer purchase_records. Product catalog candidates
are supporting evidence for product names/descriptions, but ownership and date
eligibility come only from purchase_records.

Rules:
- Return a Product2.Id only if it appears in purchase_records.
- Prefer the purchased product whose catalog name/description best matches the
  entity_phrase, product_terms, and attributes.
- If no purchased product matches, return null.
- If multiple purchased products match equally and the customer has not given
  enough information to choose, set ambiguous=true and selected_product_id=null.
- Do not use outside knowledge or infer ownership from catalog records alone.

Extracted request:
{extraction}

Purchase date window:
{date_window}

Product catalog candidates:
{product_candidates}

Eligible purchase records:
{purchase_records}

Return JSON with exactly these keys:
{{
  "selected_product_id": "01t... or null",
  "evidence": "short explanation grounded in purchase and product records",
  "confidence": "high|medium|low|unknown",
  "ambiguous": false,
  "missing_information": []
}}
""".format(
        extraction=json.dumps(extraction.as_dict(), sort_keys=True),
        date_window=list(date_window) if date_window else None,
        product_candidates=json.dumps(product_candidates, sort_keys=True),
        purchase_records=json.dumps(purchase_records, sort_keys=True),
    )


def render_ned_clarification_prompt(
    extraction: NEDExtraction,
    missing_information: List[str],
    conversation_text: str,
) -> str:
    """Build prompt for one natural clarification question."""
    return """\
Write one concise customer-facing clarification question for a purchased-product
lookup.

The deterministic workflow cannot proceed until the missing information is
provided. Do not answer the customer's original request. Do not mention internal
systems, Salesforce, JSON, schemas, or deterministic checks.

Current extracted slots:
{extraction}

Missing information:
{missing_information}

Conversation so far:
{conversation_text}

Return JSON with exactly this key:
{{
  "question": "one concise clarification question"
}}
""".format(
        extraction=json.dumps(extraction.as_dict(), sort_keys=True),
        missing_information=json.dumps(missing_information),
        conversation_text=conversation_text.strip(),
    )


def render_ned_response(selection: NEDCandidateSelection) -> str:
    """Render exactly Product2.Id or None."""
    product_id = (selection.selected_product_id or "").strip()
    return product_id if product_id and product_id.lower() != "none" else "None"


def respond_to_user(missing_information: List[str]) -> str:
    """Render one clarification question for NED."""
    missing = ", ".join(item for item in missing_information if item)
    if missing:
        return "Could you clarify {} so I can find the exact purchased product?".format(missing)
    return "Could you clarify which product and purchase timeframe you mean?"


def sanitize_search_term(search_terms: Any) -> str:
    if isinstance(search_terms, str):
        raw = search_terms
    else:
        raw = " ".join(str(term) for term in search_terms if term)
    raw = raw.replace("{", " ").replace("}", " ")
    raw = re.sub(r"[^0-9A-Za-z\s]", " ", raw)
    raw = " ".join(raw.split())
    return raw[:180]


def sanitize_id(value: Any) -> str:
    text = str(value or "").strip()
    return text if re.match(r"^[A-Za-z0-9]{15,18}$", text) else ""


def product_search_terms_for_extraction(extraction: NEDExtraction) -> List[str]:
    terms = list(extraction.product_terms)
    if extraction.entity_phrase:
        terms.append(extraction.entity_phrase)
    return terms


def is_generic_entity_phrase(value: str) -> bool:
    normalized = sanitize_search_term(value).lower()
    return normalized in GENERIC_ENTITY_PHRASES


def _parse_date(value: str) -> Optional[str]:
    text = (value or "").strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return datetime.strptime(text, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _add_months(value: datetime, delta_months: int) -> datetime:
    month_index = value.month - 1 + delta_months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)
