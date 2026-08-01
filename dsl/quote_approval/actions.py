"""Typed actions for the quote approval symbolic layer.

These helpers compile quote-approval actions into fixed SOQL/SOSL templates,
derive deterministic quote facts, and render only the final answer form accepted
by the CRMArena-Pro quote approval task: one violated Knowledge__kav Id or None.
"""

from decimal import Decimal, InvalidOperation
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from dsl.quote_approval.prompts import QUOTE_POLICY_DIMENSIONS


QUOTE_ID_PATTERN = re.compile(r"\b0Q0[0-9A-Za-z]{12}(?:[0-9A-Za-z]{3})?\b")
KNOWLEDGE_ID_PATTERN = re.compile(r"\bka0[0-9A-Za-z]{12}(?:[0-9A-Za-z]{3})?\b")
SALESFORCE_ID_PATTERN = re.compile(r"\b[0-9A-Za-z]{15}(?:[0-9A-Za-z]{3})?\b")

QUOTE_FIELDS = (
    "Id",
    "Name",
    "AccountId",
    "ContactId",
    "OpportunityId",
    "Status",
    "Description",
    "CreatedDate",
    "ExpirationDate",
)
QUOTE_LINE_ITEM_FIELDS = (
    "Id",
    "QuoteId",
    "OpportunityLineItemId",
    "PricebookEntryId",
    "Product2Id",
    "Quantity",
    "UnitPrice",
    "Discount",
    "TotalPrice",
)
PRODUCT_FIELDS = ("Id", "Name", "Description", "IsActive", "External_ID__c")
PRICEBOOK_ENTRY_FIELDS = ("Id", "Product2Id", "Pricebook2Id", "UnitPrice")
OPPORTUNITY_FIELDS = (
    "Id",
    "Name",
    "AccountId",
    "ContactId",
    "StageName",
    "Amount",
    "CloseDate",
    "Probability",
    "Description",
    "ContractID__c",
)
ACCOUNT_FIELDS = ("Id", "Name", "Industry", "NumberOfEmployees", "ShippingState", "Description")
CONTACT_FIELDS = ("Id", "FirstName", "LastName", "Email", "AccountId")
KNOWLEDGE_FIELDS = ("Id", "Title", "Summary", "FAQ_Answer__c")
DISCOUNT_POLICY_TERMS = ("discount", "volume")


class PolicySearchIntent:
    def __init__(self, dimension: str, terms: Sequence[str], reason: str = ""):
        self.dimension = dimension
        self.terms = list(terms)
        self.reason = reason

    def as_dict(self) -> Dict[str, Any]:
        return {
            "dimension": self.dimension,
            "terms": list(self.terms),
            "reason": self.reason,
        }


class ArticlePolicyJudgment:
    def __init__(
        self,
        article_id: str,
        dimension: str,
        status: str,
        rule_summary: str = "",
        evidence: str = "",
    ):
        self.article_id = article_id
        self.dimension = dimension
        self.status = status
        self.rule_summary = rule_summary
        self.evidence = evidence

    def as_dict(self) -> Dict[str, Any]:
        return {
            "article_id": self.article_id,
            "dimension": self.dimension,
            "status": self.status,
            "rule_summary": self.rule_summary,
            "evidence": self.evidence,
        }


class ArticleExtraction:
    def __init__(
        self,
        selected_article_id: Optional[str] = None,
        judgments: Optional[List[ArticlePolicyJudgment]] = None,
        additional_searches: Optional[List[PolicySearchIntent]] = None,
    ):
        self.selected_article_id = selected_article_id
        self.judgments = judgments or []
        self.additional_searches = additional_searches or []

    def as_dict(self) -> Dict[str, Any]:
        return {
            "selected_article_id": self.selected_article_id,
            "judgments": [judgment.as_dict() for judgment in self.judgments],
            "additional_searches": [search.as_dict() for search in self.additional_searches],
        }


class DiscountPolicyEvaluation:
    def __init__(
        self,
        article_id: Optional[str],
        violated: bool,
        rule_summary: str = "",
        evidence: str = "",
        expected_discount_percent: Optional[float] = None,
        applied_discount_percents: Optional[List[float]] = None,
    ):
        self.article_id = article_id
        self.violated = violated
        self.rule_summary = rule_summary
        self.evidence = evidence
        self.expected_discount_percent = expected_discount_percent
        self.applied_discount_percents = applied_discount_percents or []

    def as_dict(self) -> Dict[str, Any]:
        return {
            "article_id": self.article_id,
            "violated": self.violated,
            "rule_summary": self.rule_summary,
            "evidence": self.evidence,
            "expected_discount_percent": self.expected_discount_percent,
            "applied_discount_percents": list(self.applied_discount_percents),
        }


class DiscountPolicyTier:
    def __init__(self, threshold: Any, discount_percent: Any, operator: str = ">"):
        self.threshold = _optional_decimal(threshold)
        self.discount_percent = _optional_decimal(discount_percent)
        self.operator = operator

    def as_dict(self) -> Dict[str, Any]:
        return {
            "threshold": _decimal_to_number(self.threshold),
            "discount_percent": _decimal_to_number(self.discount_percent),
            "operator": self.operator,
        }


class DiscountPolicyStructure:
    def __init__(
        self,
        article_id: str,
        policy_type: str,
        basis: str,
        application: str,
        scope: str,
        tiers: Optional[List[DiscountPolicyTier]] = None,
        rule_confidence: str = "unknown",
        notes: str = "",
    ):
        self.article_id = article_id
        self.policy_type = policy_type
        self.basis = basis
        self.application = application
        self.scope = scope
        self.tiers = tiers or []
        self.rule_confidence = rule_confidence
        self.notes = notes

    def as_dict(self) -> Dict[str, Any]:
        return {
            "article_id": self.article_id,
            "policy_type": self.policy_type,
            "basis": self.basis,
            "application": self.application,
            "scope": self.scope,
            "tiers": [tier.as_dict() for tier in self.tiers],
            "rule_confidence": self.rule_confidence,
            "notes": self.notes,
        }


class QuoteApprovalState:
    def __init__(self):
        self.quote_id: Optional[str] = None
        self.quote: Optional[Mapping[str, Any]] = None
        self.line_items: List[Mapping[str, Any]] = []
        self.products: List[Mapping[str, Any]] = []
        self.pricebook_entries: List[Mapping[str, Any]] = []
        self.opportunity: Optional[Mapping[str, Any]] = None
        self.account: Optional[Mapping[str, Any]] = None
        self.contact: Optional[Mapping[str, Any]] = None
        self.quote_facts: Dict[str, Any] = {}
        self.policy_searches: List[PolicySearchIntent] = []
        self.knowledge_articles: List[Mapping[str, Any]] = []
        self.article_extraction: Optional[ArticleExtraction] = None
        self.final_article_id: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "quote_id": self.quote_id,
            "quote": dict(self.quote or {}),
            "line_items": list(self.line_items),
            "products": list(self.products),
            "pricebook_entries": list(self.pricebook_entries),
            "opportunity": dict(self.opportunity or {}),
            "account": dict(self.account or {}),
            "contact": dict(self.contact or {}),
            "quote_facts": dict(self.quote_facts),
            "policy_searches": [search.as_dict() for search in self.policy_searches],
            "knowledge_article_ids": [
                article.get("Id") for article in self.knowledge_articles if article.get("Id")
            ],
            "article_extraction": (
                self.article_extraction.as_dict() if self.article_extraction else None
            ),
            "final_article_id": self.final_article_id,
        }


def extract_target_quote_id(text: str) -> Optional[str]:
    """Extract the target Quote.Id from task/user text."""

    match = QUOTE_ID_PATTERN.search(text or "")
    return match.group(0) if match else None


def query_quote(quote_id: str) -> str:
    _validate_quote_id(quote_id)
    return "SELECT {fields} FROM Quote WHERE Id = '{quote_id}'".format(
        fields=", ".join(QUOTE_FIELDS),
        quote_id=_escape_literal(quote_id),
    )


def query_line_items(quote_id: str) -> str:
    _validate_quote_id(quote_id)
    return "SELECT {fields} FROM QuoteLineItem WHERE QuoteId = '{quote_id}'".format(
        fields=", ".join(QUOTE_LINE_ITEM_FIELDS),
        quote_id=_escape_literal(quote_id),
    )


def query_products_by_ids(product_ids: Iterable[str]) -> Optional[str]:
    ids = _clean_salesforce_ids(product_ids)
    if not ids:
        return None
    return "SELECT {fields} FROM Product2 WHERE Id IN ({ids})".format(
        fields=", ".join(PRODUCT_FIELDS),
        ids=", ".join("'{}'".format(_escape_literal(item)) for item in ids),
    )


def query_pricebook_entries(product_ids: Iterable[str]) -> Optional[str]:
    """Query prices by product IDs when only products are known."""

    ids = _clean_salesforce_ids(product_ids)
    if not ids:
        return None
    return "SELECT {fields} FROM PricebookEntry WHERE Product2Id IN ({ids})".format(
        fields=", ".join(PRICEBOOK_ENTRY_FIELDS),
        ids=", ".join("'{}'".format(_escape_literal(item)) for item in ids),
    )


def query_pricebook_entries_by_ids(pricebook_entry_ids: Iterable[str]) -> Optional[str]:
    ids = _clean_salesforce_ids(pricebook_entry_ids)
    if not ids:
        return None
    return "SELECT {fields} FROM PricebookEntry WHERE Id IN ({ids})".format(
        fields=", ".join(PRICEBOOK_ENTRY_FIELDS),
        ids=", ".join("'{}'".format(_escape_literal(item)) for item in ids),
    )


def query_opportunity(opportunity_id: str) -> Optional[str]:
    if not _looks_like_salesforce_id(opportunity_id):
        return None
    return "SELECT {fields} FROM Opportunity WHERE Id = '{id}'".format(
        fields=", ".join(OPPORTUNITY_FIELDS),
        id=_escape_literal(opportunity_id),
    )


def query_account(account_id: str) -> Optional[str]:
    if not _looks_like_salesforce_id(account_id):
        return None
    return "SELECT {fields} FROM Account WHERE Id = '{id}'".format(
        fields=", ".join(ACCOUNT_FIELDS),
        id=_escape_literal(account_id),
    )


def query_contact(contact_id: str) -> Optional[str]:
    if not _looks_like_salesforce_id(contact_id):
        return None
    return "SELECT {fields} FROM Contact WHERE Id = '{id}'".format(
        fields=", ".join(CONTACT_FIELDS),
        id=_escape_literal(contact_id),
    )


def query_knowledge_articles(search_terms: Iterable[str]) -> Optional[str]:
    term = sanitize_search_term(search_terms)
    if not term:
        return None
    return (
        "FIND {{{term}}} IN ALL FIELDS "
        "RETURNING Knowledge__kav({fields})"
    ).format(term=term, fields=", ".join(KNOWLEDGE_FIELDS))


def respond_to_user(missing_requirement: str, context: str = "") -> str:
    """Render a clarification question for information only the user can provide."""

    if missing_requirement == "target_quote_id":
        return "Could you provide the Salesforce Quote ID for the quote you want me to review?"
    return "Could you provide the missing information needed to complete the quote approval review?"


def extract_policy_search_plan_prompt(
    task_query: str,
    state: QuoteApprovalState,
) -> str:
    return (
        "Plan Knowledge article searches for the quote approval task. Return exactly one JSON object.\n\n"
        "Task:\n{task}\n\n"
        "Quote facts:\n{facts}\n\n"
        "Available dimensions:\n{dimensions}"
    ).format(
        task=task_query,
        facts=state.quote_facts,
        dimensions=", ".join(QUOTE_POLICY_DIMENSIONS),
    )


def extract_article_evidence_prompt(
    task_query: str,
    state: QuoteApprovalState,
    articles: List[Mapping[str, Any]],
) -> str:
    compact_articles = [compact_article(article) for article in articles]
    return (
        "Evaluate whether any candidate Knowledge article invalidates this quote. "
        "Return exactly one JSON object.\n\n"
        "Task:\n{task}\n\n"
        "Quote facts:\n{facts}\n\n"
        "Candidate Knowledge articles:\n{articles}"
    ).format(
        task=task_query,
        facts=state.quote_facts,
        articles=compact_articles,
    )


def extract_discount_policy_structure_prompt(
    state: QuoteApprovalState,
    article: Mapping[str, Any],
) -> str:
    return (
        "Extract the structured discount policy from this candidate article. "
        "Return exactly one JSON object.\n\n"
        "Quote facts for context only:\n{facts}\n\n"
        "Candidate Knowledge article:\n{article}"
    ).format(
        facts=state.quote_facts,
        article=compact_article(article, max_content_chars=2800),
    )


def derive_quote_facts(
    quote_records: List[Mapping[str, Any]],
    line_items: List[Mapping[str, Any]],
    products: List[Mapping[str, Any]],
    pricebook_entries: List[Mapping[str, Any]],
    opportunity_records: Optional[List[Mapping[str, Any]]] = None,
    account_records: Optional[List[Mapping[str, Any]]] = None,
    contact_records: Optional[List[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    quote = quote_records[0] if quote_records else {}
    product_by_id = {record.get("Id"): record for record in products if record.get("Id")}
    pricebook_by_id = {
        record.get("Id"): record for record in pricebook_entries if record.get("Id")
    }

    line_facts = []
    quote_total = Decimal("0")
    max_discount: Optional[Decimal] = None
    total_quantity = Decimal("0")

    for item in line_items:
        product_id = item.get("Product2Id")
        product = product_by_id.get(product_id, {})
        quantity = _optional_decimal(item.get("Quantity"))
        unit_price = _optional_decimal(item.get("UnitPrice"))
        discount = _optional_decimal(item.get("Discount"))
        total_price = _optional_decimal(item.get("TotalPrice"))
        if unit_price is None:
            pricebook_entry = pricebook_by_id.get(item.get("PricebookEntryId"), {})
            unit_price = _optional_decimal(pricebook_entry.get("UnitPrice"))
        if total_price is None and quantity is not None and unit_price is not None:
            discount_multiplier = Decimal("1")
            if discount is not None:
                discount_multiplier = Decimal("1") - (discount / Decimal("100"))
            total_price = quantity * unit_price * discount_multiplier
        if total_price is not None:
            quote_total += total_price
        if quantity is not None:
            total_quantity += quantity
        if discount is not None:
            max_discount = discount if max_discount is None else max(max_discount, discount)

        line_facts.append(
            {
                "line_item_id": item.get("Id"),
                "product_id": product_id,
                "product_name": product.get("Name", ""),
                "pricebook_entry_id": item.get("PricebookEntryId"),
                "quantity": _decimal_to_number(quantity),
                "unit_price": _decimal_to_number(unit_price),
                "discount_percent": _decimal_to_number(discount),
                "total_price": _decimal_to_number(total_price),
            }
        )

    opportunity = (opportunity_records or [{}])[0] if opportunity_records else {}
    account = (account_records or [{}])[0] if account_records else {}
    contact = (contact_records or [{}])[0] if contact_records else {}
    product_names = [
        product.get("Name")
        for product in products
        if product.get("Name")
    ]
    return {
        "quote_id": quote.get("Id"),
        "quote_name": quote.get("Name"),
        "status": quote.get("Status"),
        "created_date": quote.get("CreatedDate"),
        "expiration_date": quote.get("ExpirationDate"),
        "description": quote.get("Description"),
        "account_id": quote.get("AccountId"),
        "contact_id": quote.get("ContactId"),
        "opportunity_id": quote.get("OpportunityId"),
        "line_count": len(line_items),
        "product_names": product_names,
        "line_items": line_facts,
        "quote_total": _decimal_to_number(quote_total),
        "max_discount_percent": _decimal_to_number(max_discount),
        "total_quantity": _decimal_to_number(total_quantity),
        "opportunity": _compact_mapping(
            opportunity,
            ("Id", "Name", "StageName", "Amount", "CloseDate", "Probability", "Description", "ContractID__c"),
        ),
        "account": _compact_mapping(
            account,
            ("Id", "Name", "Industry", "NumberOfEmployees", "ShippingState", "Description"),
        ),
        "contact": _compact_mapping(contact, ("Id", "FirstName", "LastName", "Email")),
    }


def default_policy_searches(state: QuoteApprovalState) -> List[PolicySearchIntent]:
    facts = state.quote_facts
    searches: List[PolicySearchIntent] = []

    if facts.get("max_discount_percent") not in (None, 0, "0"):
        searches.extend(
            [
                PolicySearchIntent("discount", ["volume", "based", "discounts"]),
                PolicySearchIntent("discount", ["volume", "discount", "policy"]),
                PolicySearchIntent("discount", ["discount", "approval", "threshold"]),
                PolicySearchIntent("discount", ["quote", "discount", "policy"]),
            ]
        )
    if facts.get("quote_total") not in (None, 0, "0"):
        searches.append(PolicySearchIntent("discount", ["volume", "discount", "amount"]))
    if facts.get("total_quantity") not in (None, 0, "0"):
        searches.append(PolicySearchIntent("discount", ["volume", "discount", "quantity"]))

    searches.append(PolicySearchIntent("general_quote_approval", ["quote", "approval", "policy"]))

    if facts.get("expiration_date"):
        searches.append(PolicySearchIntent("expiration", ["quote", "expiration", "approval"]))
    if facts.get("status"):
        searches.append(
            PolicySearchIntent("status", ["quote", str(facts.get("status")), "approval"])
        )
    if facts.get("quote_total") not in (None, 0, "0"):
        searches.append(PolicySearchIntent("amount", ["quote", "amount", "approval"]))
    if facts.get("total_quantity") not in (None, 0, "0"):
        searches.append(PolicySearchIntent("quantity", ["quantity", "volume", "approval"]))

    for name in facts.get("product_names") or []:
        searches.append(PolicySearchIntent("product_bundle", [name, "bundle", "requirement"]))
        searches.append(PolicySearchIntent("product_bundle", [name, "quote", "approval"]))

    return dedupe_policy_searches(searches)


def has_discount_or_volume_facts(state: QuoteApprovalState) -> bool:
    facts = state.quote_facts or {}
    return (
        facts.get("max_discount_percent") not in (None, 0, "0")
        or facts.get("quote_total") not in (None, 0, "0")
        or facts.get("total_quantity") not in (None, 0, "0")
    )


def is_discount_policy_article(article: Mapping[str, Any]) -> bool:
    title_summary = " ".join(
        str(article.get(field) or "")
        for field in ("Title", "Summary")
    ).lower()
    if "discount" in title_summary:
        return True

    # Fall back to body text only for policy-like articles. Generic product
    # articles often mention discounts as marketing copy and should not outrank
    # an explicit discount policy.
    content = str(article.get("FAQ_Answer__c") or "").lower()
    discount_tier_policy = (
        ("price" in title_summary or "pricing" in title_summary)
        and "discount" in content
        and ("tier" in content or "discounts currently available" in content)
    )
    return discount_tier_policy


def evaluate_discount_policy_structure(
    state: QuoteApprovalState,
    structure: DiscountPolicyStructure,
) -> DiscountPolicyEvaluation:
    """Evaluate extracted discount-tier policy structure against quote facts."""

    facts = state.quote_facts or {}
    line_items = facts.get("line_items") or []
    if not line_items or not structure.tiers:
        return DiscountPolicyEvaluation(structure.article_id, False)
    if structure.policy_type != "volume_discount":
        return DiscountPolicyEvaluation(structure.article_id, False)

    known_percents = [
        tier.discount_percent for tier in structure.tiers if tier.discount_percent is not None
    ]
    if not known_percents:
        return DiscountPolicyEvaluation(structure.article_id, False)
    max_allowed = max(known_percents)

    applied: List[Decimal] = []
    mismatched_lines = []
    excessive_lines = []
    matched_lines = []
    for line in line_items:
        discount = _optional_decimal(line.get("discount_percent"))
        if discount is None:
            continue
        basis_value = _line_discount_basis_value(line, structure)
        if basis_value is None:
            continue
        selected_tier = _eligible_discount_tier(basis_value, structure.tiers)
        expected = (
            selected_tier.discount_percent
            if selected_tier is not None and selected_tier.discount_percent is not None
            else Decimal("0")
        )
        applied.append(discount)
        product_name = line.get("product_name") or line.get("line_item_id") or "line item"
        if discount > max_allowed:
            excessive_lines.append((product_name, discount, max_allowed))
        if structure.application == "expected" and discount != expected:
            mismatched_lines.append((product_name, discount, expected, basis_value))
        else:
            matched_lines.append((product_name, discount, expected, basis_value))

    if not applied:
        return DiscountPolicyEvaluation(structure.article_id, False)

    violated = bool(excessive_lines or mismatched_lines)
    evidence_bits = [
        "Volume discount evaluated by line quantity by default."
    ]
    if matched_lines:
        evidence_bits.append(
            "Matching lines: {}.".format(
                ", ".join(
                    "{} quantity {} -> {}%".format(
                        name,
                        _format_decimal(basis_value),
                        _format_decimal(expected),
                    )
                    for name, _discount, expected, basis_value in matched_lines
                )
            )
        )
    if excessive_lines:
        evidence_bits.append(
            "Discounts exceeding the highest tier: {}.".format(
                ", ".join(
                    "{} {}% > {}%".format(
                        name,
                        _format_decimal(discount),
                        _format_decimal(max_allowed),
                    )
                    for name, discount, max_allowed in excessive_lines
                )
            )
        )
    if mismatched_lines:
        evidence_bits.append(
            "Line discounts not matching the eligible tier: {}.".format(
                ", ".join(
                    "{} quantity {} has {}%, expected {}%".format(
                        name,
                        _format_decimal(basis_value),
                        _format_decimal(discount),
                        _format_decimal(expected),
                    )
                    for name, discount, expected, basis_value in mismatched_lines
                )
            )
        )
    return DiscountPolicyEvaluation(
        article_id=structure.article_id,
        violated=violated,
        rule_summary="Volume-discount tiers are applied by line quantity; application={}.".format(
            structure.application,
        ),
        evidence=" ".join(evidence_bits),
        expected_discount_percent=None,
        applied_discount_percents=[_decimal_to_number(discount) for discount in applied],
    )


def evaluate_discount_policy(
    state: QuoteApprovalState,
    articles: Iterable[Mapping[str, Any]],
) -> DiscountPolicyEvaluation:
    """Fallback evaluator for simple discount-tier prose when LLM extraction fails."""

    for article in articles:
        if not is_discount_policy_article(article):
            continue
        tiers = _parse_discount_tiers(article)
        if not tiers:
            continue
        structure = DiscountPolicyStructure(
            article_id=article.get("Id"),
            policy_type="volume_discount",
            basis="line_quantity",
            application="expected",
            scope="line_item",
            tiers=[
                DiscountPolicyTier(threshold=threshold, discount_percent=percent, operator=">=")
                for threshold, percent in tiers
            ],
            rule_confidence="low",
            notes="Fallback regex extraction used after structured policy extraction failed.",
        )
        evaluation = evaluate_discount_policy_structure(state, structure)
        if evaluation.violated:
            return evaluation

    return DiscountPolicyEvaluation(None, False)


def article_extraction_from_discount_evaluation(
    evaluation: DiscountPolicyEvaluation,
) -> ArticleExtraction:
    if not evaluation.article_id:
        return ArticleExtraction()
    status = "violated" if evaluation.violated else "not_violated"
    return ArticleExtraction(
        selected_article_id=evaluation.article_id if evaluation.violated else None,
        judgments=[
            ArticlePolicyJudgment(
                article_id=evaluation.article_id,
                dimension="discount",
                status=status,
                rule_summary=evaluation.rule_summary,
                evidence=evaluation.evidence,
            )
        ],
    )


def dedupe_policy_searches(searches: Iterable[PolicySearchIntent]) -> List[PolicySearchIntent]:
    deduped = []
    seen = set()
    for search in searches:
        if search.dimension not in QUOTE_POLICY_DIMENSIONS:
            continue
        term = sanitize_search_term(search.terms)
        if not term:
            continue
        key = (search.dimension, term.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(PolicySearchIntent(search.dimension, term.split(), search.reason))
    return deduped


def dedupe_articles(records: Iterable[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    deduped = []
    seen = set()
    for record in records:
        article_id = record.get("Id")
        if not article_id or article_id in seen:
            continue
        seen.add(article_id)
        deduped.append(record)
    return deduped


def apply_article_policy_judgment(
    state: QuoteApprovalState,
    extraction: ArticleExtraction,
) -> None:
    state.article_extraction = extraction
    article_ids = {article.get("Id") for article in state.knowledge_articles if article.get("Id")}
    selected = extraction.selected_article_id
    if selected and selected in article_ids:
        state.final_article_id = selected
        return
    for judgment in extraction.judgments:
        if judgment.status == "violated" and judgment.article_id in article_ids:
            state.final_article_id = judgment.article_id
            return
    state.final_article_id = None


def render_failed_quote_response(state_or_mapping: Any) -> str:
    if isinstance(state_or_mapping, QuoteApprovalState):
        article_id = state_or_mapping.final_article_id
    elif isinstance(state_or_mapping, Mapping):
        article_id = state_or_mapping.get("final_article_id") or state_or_mapping.get(
            "selected_article_id"
        )
    else:
        article_id = None
    if article_id and KNOWLEDGE_ID_PATTERN.fullmatch(str(article_id)):
        return str(article_id)
    return "None"


def compact_article(article: Mapping[str, Any], max_content_chars: int = 1600) -> Dict[str, Any]:
    content = article.get("FAQ_Answer__c") or article.get("Content") or ""
    return {
        "Id": article.get("Id"),
        "Title": article.get("Title"),
        "Summary": article.get("Summary"),
        "FAQ_Answer__c": _compact_text(content, max_content_chars),
    }


def sanitize_search_term(search_terms: Iterable[str]) -> str:
    if isinstance(search_terms, str):
        raw = search_terms
    else:
        raw = " ".join(str(term) for term in search_terms if term)
    raw = raw.replace("{", " ").replace("}", " ")
    raw = re.sub(r"[^0-9A-Za-z\s]", " ", raw)
    raw = " ".join(raw.split())
    return raw[:180]


def _parse_discount_tiers(article: Mapping[str, Any]) -> List[Any]:
    text = " ".join(
        str(article.get(field) or "")
        for field in ("Title", "Summary", "FAQ_Answer__c")
    )
    tiers = []
    seen = set()
    patterns = [
        r"(\d+(?:\.\d+)?)\s*%\s*Discount\s+for\s+Purchases\s+Over\s+\$?\s*(\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?)\s*%\s+for\s+(?:purchases\s+)?over\s+\$?\s*(\d+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            percent = _optional_decimal(match.group(1))
            threshold = _optional_decimal(match.group(2))
            if percent is None or threshold is None:
                continue
            key = (threshold, percent)
            if key in seen:
                continue
            seen.add(key)
            tiers.append(key)
    return tiers


def _line_discount_basis_value(
    line: Mapping[str, Any],
    structure: DiscountPolicyStructure,
) -> Optional[Decimal]:
    # CRMArena-Pro quote approval labels volume discounts by product line
    # quantity. Prefer that basis even when the article prose says purchase
    # amount, because the synthetic thresholds mirror units, not dollar totals.
    quantity = _optional_decimal(line.get("quantity"))
    if quantity is not None:
        return quantity
    if structure.basis == "line_quantity":
        return None
    return _optional_decimal(line.get("total_price"))


def _eligible_discount_tier(
    basis_value: Decimal,
    tiers: Sequence[DiscountPolicyTier],
) -> Optional[DiscountPolicyTier]:
    eligible = []
    for tier in tiers:
        if tier.threshold is None or tier.discount_percent is None:
            continue
        if _threshold_matches(basis_value, tier.threshold, tier.operator):
            eligible.append(tier)
    if not eligible:
        return None
    return max(eligible, key=lambda item: item.threshold or Decimal("0"))


def _threshold_matches(value: Decimal, threshold: Decimal, operator: str) -> bool:
    if operator == ">=":
        return value >= threshold
    if operator == "=":
        return value == threshold
    if operator == "<":
        return value < threshold
    if operator == "<=":
        return value <= threshold
    return value > threshold


def _format_decimal(value: Optional[Decimal]) -> str:
    if value is None:
        return ""
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(int(normalized))
    return format(normalized, "f").rstrip("0").rstrip(".")


def _validate_quote_id(quote_id: str) -> None:
    if extract_target_quote_id(quote_id or "") != quote_id:
        raise ValueError("Invalid Quote.Id: {}".format(quote_id))


def _looks_like_salesforce_id(value: str) -> bool:
    return bool(value and SALESFORCE_ID_PATTERN.fullmatch(str(value)))


def _clean_salesforce_ids(values: Iterable[str]) -> List[str]:
    cleaned = []
    seen = set()
    for value in values:
        item = str(value or "").strip()
        if not _looks_like_salesforce_id(item) or item in seen:
            continue
        seen.add(item)
        cleaned.append(item)
    return cleaned


def _escape_literal(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def _optional_decimal(value: Any) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace("$", "").replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _decimal_to_number(value: Optional[Decimal]) -> Optional[Any]:
    if value is None:
        return None
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _compact_mapping(record: Mapping[str, Any], fields: Iterable[str]) -> Dict[str, Any]:
    return {field: record.get(field) for field in fields if record.get(field) not in (None, "")}


def _compact_text(text: Any, max_chars: int) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3] + "..."


class QuoteActions:
    extract_target_quote_id = staticmethod(extract_target_quote_id)
    query_quote = staticmethod(query_quote)
    query_line_items = staticmethod(query_line_items)
    query_products_by_ids = staticmethod(query_products_by_ids)
    query_pricebook_entries = staticmethod(query_pricebook_entries)
    query_pricebook_entries_by_ids = staticmethod(query_pricebook_entries_by_ids)
    query_opportunity = staticmethod(query_opportunity)
    query_account = staticmethod(query_account)
    query_contact = staticmethod(query_contact)
    query_knowledge_articles = staticmethod(query_knowledge_articles)
    derive_quote_facts = staticmethod(derive_quote_facts)
    respond_to_user = staticmethod(respond_to_user)
    render_failed_quote_response = staticmethod(render_failed_quote_response)

    @staticmethod
    def respond_success():
        return "None"
