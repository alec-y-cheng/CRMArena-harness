"""Actions and state helpers for the knowledge_qa symbolic layer."""

import html
import json
import re
from typing import Any, Dict, List, Optional

from dsl.external_facing.actions import (
    ALLOWED_EVIDENCE_TYPES,
    DISALLOWED_EVIDENCE_TYPES,
    SUBJECT_SCOPES,
)


KNOWLEDGE_FIELDS = ("Id", "Title", "Summary", "FAQ_Answer__c")
QUESTION_TYPES = (
    "yes_no",
    "number",
    "single_option",
    "short_list",
    "procedure",
    "reason",
    "description",
)
ANSWER_SPAN_RELEVANCE = (
    "direct",
    "supporting_context",
    "related_but_unasked",
    "contradicts",
)


class KnowledgeQASearchPlan:
    """Structured search plan for public knowledge article retrieval."""

    def __init__(
        self,
        normalized_question: str = "",
        search_terms: Optional[List[str]] = None,
        product_terms: Optional[List[str]] = None,
        clarification_needed: bool = False,
        clarification_requirements: Optional[List[str]] = None,
    ):
        self.normalized_question = normalized_question
        self.search_terms = search_terms or []
        self.product_terms = product_terms or []
        self.clarification_needed = clarification_needed
        self.clarification_requirements = clarification_requirements or []

    def as_dict(self) -> Dict[str, Any]:
        return {
            "normalized_question": self.normalized_question,
            "search_terms": list(self.search_terms),
            "product_terms": list(self.product_terms),
            "clarification_needed": self.clarification_needed,
            "clarification_requirements": list(self.clarification_requirements),
        }


class KnowledgeQAAnswer:
    """Grounded answer extracted from retrieved public knowledge articles."""

    def __init__(
        self,
        question_type: str = "description",
        asked_focus: str = "",
        candidate_answer_spans: Optional[List["KnowledgeQAAnswerSpan"]] = None,
        answer: str = "",
        selected_article_ids: Optional[List[str]] = None,
        evidence: str = "",
        confidence: str = "unknown",
    ):
        self.question_type = question_type
        self.asked_focus = asked_focus
        self.candidate_answer_spans = candidate_answer_spans or []
        self.answer = answer
        self.selected_article_ids = selected_article_ids or []
        self.evidence = evidence
        self.confidence = confidence

    def as_dict(self) -> Dict[str, Any]:
        return {
            "question_type": self.question_type,
            "asked_focus": self.asked_focus,
            "candidate_answer_spans": [
                span.as_dict() for span in self.candidate_answer_spans
            ],
            "answer": self.answer,
            "selected_article_ids": list(self.selected_article_ids),
            "evidence": self.evidence,
            "confidence": self.confidence,
        }


class KnowledgeQAAnswerSpan:
    """One candidate article span considered for the final customer answer."""

    def __init__(
        self,
        span: str = "",
        relevance: str = "related_but_unasked",
        include: bool = False,
        article_id: str = "",
        reason: str = "",
    ):
        self.span = span
        self.relevance = relevance
        self.include = include
        self.article_id = article_id
        self.reason = reason

    def as_dict(self) -> Dict[str, Any]:
        return {
            "span": self.span,
            "relevance": self.relevance,
            "include": self.include,
            "article_id": self.article_id,
            "reason": self.reason,
        }


class KnowledgeQAArticleEvidence:
    """Evidence classification for one retrieved Knowledge__kav article."""

    def __init__(
        self,
        article_id: str = "",
        evidence_type: str = "unknown",
        subject_scope: str = "unknown",
        safe_to_use: bool = False,
        reason: str = "",
    ):
        self.article_id = article_id
        self.evidence_type = evidence_type
        self.subject_scope = subject_scope
        self.safe_to_use = safe_to_use
        self.reason = reason

    def as_dict(self) -> Dict[str, Any]:
        return {
            "article_id": self.article_id,
            "evidence_type": self.evidence_type,
            "subject_scope": self.subject_scope,
            "safe_to_use": self.safe_to_use,
            "reason": self.reason,
        }


class KnowledgeQAState:
    """Runtime state for the knowledge QA workflow."""

    def __init__(self):
        self.search_plan: Optional[KnowledgeQASearchPlan] = None
        self.knowledge_articles: List[Dict[str, Any]] = []
        self.article_evidence: List[KnowledgeQAArticleEvidence] = []
        self.answer: Optional[KnowledgeQAAnswer] = None
        self.final_response: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "search_plan": self.search_plan.as_dict() if self.search_plan else None,
            "knowledge_articles": [dict(article) for article in self.knowledge_articles],
            "article_evidence": [evidence.as_dict() for evidence in self.article_evidence],
            "answer": self.answer.as_dict() if self.answer else None,
            "final_response": self.final_response,
        }


def extract_knowledge_search_plan_prompt(task_query: str, conversation_text: str) -> str:
    """Build prompt for extracting question/search terms."""
    return """\
Extract a compact public-knowledge search plan for the customer's latest
question.

The search plan will be used only to compile deterministic SOSL searches over
public Knowledge__kav articles. Do not invent article content and do not write
SQL or SOSL.

Search-term guidance:
- Prefer terms that are likely to appear in article title, summary, or body.
- Include product/service names when present.
- Include the core concept being asked about.
- Use 1 to 4 search_terms. Each term should be a concise query phrase, not a
  full sentence.
- Mark clarification_needed only when the customer question is too vague to
  search meaningfully.

Original task query:
{task_query}

Conversation so far:
{conversation_text}

Return JSON with exactly these keys:
{{
  "normalized_question": "customer's latest answerable question",
  "search_terms": ["concise search phrase"],
  "product_terms": ["product or service names if any"],
  "clarification_needed": false,
  "clarification_requirements": []
}}
""".format(
        task_query=task_query.strip(),
        conversation_text=conversation_text.strip(),
    )


def query_public_knowledge_articles(search_terms: List[str]) -> Optional[str]:
    """Compile a deterministic Knowledge__kav search query."""
    term = sanitize_search_term(search_terms)
    if not term:
        return None
    return (
        "FIND {{{term}}} IN ALL FIELDS "
        "RETURNING Knowledge__kav({fields})"
    ).format(term=term, fields=", ".join(KNOWLEDGE_FIELDS))


def classify_knowledge_selected_evidence_prompt(
    search_plan: KnowledgeQASearchPlan,
    answer: KnowledgeQAAnswer,
    articles: List[Dict[str, Any]],
) -> str:
    """Build prompt for classifying only the evidence selected for the answer."""
    article_by_id = {article.get("Id"): article for article in articles if article.get("Id")}
    selected_items = []
    for span in answer.candidate_answer_spans:
        if not span.include or span.relevance != "direct":
            continue
        article = article_by_id.get(span.article_id, {})
        selected_items.append(
            {
                "article_id": span.article_id,
                "article_title": article.get("Title", ""),
                "article_summary": article.get("Summary", ""),
                "selected_span": span.span,
                "span_reason": span.reason,
            }
        )
    if not selected_items:
        for article_id in answer.selected_article_ids:
            article = article_by_id.get(article_id, {})
            selected_items.append(
                {
                    "article_id": article_id,
                    "article_title": article.get("Title", ""),
                    "article_summary": article.get("Summary", ""),
                    "selected_span": "",
                    "span_reason": "Selected article supports the proposed answer.",
                }
            )
    return """\
Classify only the evidence that would actually be disclosed in the final answer
to an external customer.

Use the fixed evidence taxonomy. Classify the selected span and proposed answer,
not the entire retrieved article and not unrelated retrieved content. Public
customer-facing documentation may be safe when the selected answer only exposes
information intended for external customers.

Be stricter here than the initial router: if the selected span or proposed
answer would expose non-public company knowledge, private customer data,
internal operating evidence, commercial decision rules, or competitive/strategic
evidence, classify it with the closest disallowed evidence type and set
safe_to_use=false. When sensitivity is unclear from the selected evidence, use a
disallowed or unknown-sensitive classification rather than approving it.

Allowed evidence types:
{allowed_evidence}

Disallowed evidence types:
{disallowed_evidence}

Subject scopes:
{subject_scopes}

Question:
{question}

Proposed final answer:
{answer}

Selected evidence:
{selected_evidence}

Return JSON with exactly these keys:
{{
  "article_evidence": [
    {{
      "article_id": "ka0...",
      "evidence_type": "fixed evidence type",
      "subject_scope": "public|current_customer|other_customer|internal_company|unknown",
      "safe_to_use": true,
      "reason": "short reason based on selected span and proposed answer"
    }}
  ]
}}
""".format(
        allowed_evidence=json.dumps(list(ALLOWED_EVIDENCE_TYPES)),
        disallowed_evidence=json.dumps(list(DISALLOWED_EVIDENCE_TYPES)),
        subject_scopes=json.dumps(list(SUBJECT_SCOPES)),
        question=search_plan.normalized_question.strip(),
        answer=(answer.answer or "").strip(),
        selected_evidence=json.dumps(selected_items, sort_keys=True),
    )


def extract_knowledge_answer_prompt(
    search_plan: KnowledgeQASearchPlan,
    articles: List[Dict[str, Any]],
) -> str:
    """Build prompt for grounded answer narrowing from retrieved articles."""
    snippet_terms = answer_snippet_terms(search_plan)
    compact_articles = [
        compact_article(article, snippet_terms=snippet_terms) for article in articles
    ]
    return """\
Narrow the retrieved public Knowledge__kav articles into the shortest grounded
reference answer to the customer's question.

You are not writing a full customer-service reply. The final answer should be a
minimal phrase, number, option, compact list, action, condition, or short
sentence. Do not restate the brand, product, user's situation, examples,
mechanisms, adjacent caveats, or extra policy details unless those words are
needed to answer the exact question.

Rules:
- First classify question_type as one of: yes_no, number, single_option,
  short_list, procedure, reason, description.
- Set asked_focus to the specific thing the customer is asking for.
- Identify 1 to 6 candidate_answer_spans from the articles. Mark a span
  direct only when it answers the exact asked_focus. Mark adjacent helpful
  details as supporting_context or related_but_unasked and set include=false.
- Candidate spans should be the smallest exact article phrase or sentence
  fragment that can support the answer. If a sentence contains the answer plus
  extra explanation, keep only the answer phrase when possible.
- Build answer only from spans marked include=true and relevance=direct.
- Mark include=true only for spans whose words should survive into the final
  answer. Prefer one included direct span unless the answer truly requires a
  short list of multiple items.
- If a direct answer exists, answer with the shortest exact phrase, number,
  option, action, condition, compact list, or short sentence that resolves the
  question. The answer should usually be under 20 words unless the customer asks
  for multiple steps or a longer explanation.
- For yes/no questions, preserve polarity and include the shortest supporting
  reason, deadline, condition, or exception when the direct evidence provides
  one. Avoid one-word answers when there is a useful condition in the article,
  but do not add extra conditions beyond the one needed for the yes/no answer.
- For which/what-option, fastest, best, primary, or most-specific questions,
  choose the single strongest option when the article supports one. A span is
  direct only if it ties the option to the exact criterion and object asked
  about. Do not infer the answer from weaker generic adjectives when another
  span mentions the asked object or criterion more specifically.
- For short_list questions, return compact nouns/features/options separated by
  commas. Do not turn each list item into an explanatory sentence.
- For procedure questions, return only the required action steps. Do not add
  preventative care, examples, or side conditions unless the question asks for
  them.
- For reason questions, return only the core reason. Do not add detailed
  mechanisms unless the question asks how the mechanism works.
- If the user asks for an essential, main, fastest, or specific item, do not
  list every related item.
- For when/deadline/eligibility questions, a condition-based answer is valid
  even when the article does not give a calendar date.
- If no retrieved article supports the answer, set answer to "None" and
  selected_article_ids to [], and do not mark any span include=true.
- selected_article_ids and span article_id values must contain only IDs from
  the retrieved articles. Use an empty article_id only for a span not tied to a
  specific article.
- Do not mention internal systems, query mechanics, or unavailable evidence.

Question:
{question}

Retrieved articles:
{articles}

Return JSON with exactly these keys:
{{
  "question_type": "yes_no|number|single_option|short_list|procedure|reason|description",
  "asked_focus": "specific thing being asked",
  "candidate_answer_spans": [
    {{
      "span": "exact candidate text from retrieved article",
      "relevance": "direct|supporting_context|related_but_unasked|contradicts",
      "include": true,
      "article_id": "ka0...",
      "reason": "why this span is or is not part of the answer"
    }}
  ],
  "answer": "concise answer or None",
  "selected_article_ids": ["ka0..."],
  "evidence": "short grounded evidence summary",
  "confidence": "high|medium|low|unknown"
}}
""".format(
        question=search_plan.normalized_question.strip(),
        articles=json.dumps(compact_articles, sort_keys=True),
    )


def render_knowledge_answer_response(answer: KnowledgeQAAnswer) -> str:
    """Render the final customer-facing knowledge QA response."""
    text = (answer.answer or "").strip()
    if text and text.lower() != "none":
        return text
    direct_spans = [
        span.span.strip()
        for span in answer.candidate_answer_spans
        if span.include and span.relevance == "direct" and span.span.strip()
    ]
    if direct_spans:
        return "; ".join(direct_spans[:3])
    return "None"


def respond_to_user(clarification_requirements: List[str]) -> str:
    """Render one clarification question for missing knowledge QA information."""
    missing = ", ".join(item for item in clarification_requirements if item)
    if missing:
        return "Could you clarify {} so I can find the right public article?".format(missing)
    return "Could you clarify what product or topic you want information about?"


def sanitize_search_term(search_terms: Any) -> str:
    if isinstance(search_terms, str):
        raw = search_terms
    else:
        raw = " ".join(str(term) for term in search_terms if term)
    raw = raw.replace("{", " ").replace("}", " ")
    raw = re.sub(r"[^0-9A-Za-z\s]", " ", raw)
    raw = " ".join(raw.split())
    return raw[:180]


def answer_snippet_terms(search_plan: KnowledgeQASearchPlan) -> List[str]:
    """Build deterministic terms used for article snippet selection."""
    raw_terms = [search_plan.normalized_question]
    raw_terms.extend(search_plan.search_terms)
    raw_terms.extend(search_plan.product_terms)
    seen = set()
    out = []
    for term in raw_terms:
        cleaned = sanitize_search_term(term).lower()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    for term in list(out):
        for token in term.split():
            if _is_snippet_token(token) and token not in seen:
                seen.add(token)
                out.append(token)
    return out


def compact_article(
    article: Dict[str, Any],
    snippet_terms: Optional[List[str]] = None,
    max_content_chars: int = 4200,
    window_chars: int = 1000,
    max_windows: int = 4,
) -> Dict[str, Any]:
    """Return search-aware snippets from the full article text for extraction."""
    content = article.get("FAQ_Answer__c")
    if content is None:
        content = article.get("Content", "")
    content_text = _clean_article_text(str(content or ""))
    snippet_text = search_aware_article_snippet(
        content_text,
        snippet_terms=snippet_terms or [],
        max_content_chars=max_content_chars,
        window_chars=window_chars,
        max_windows=max_windows,
    )
    return {
        "Id": article.get("Id"),
        "Title": article.get("Title", ""),
        "Summary": article.get("Summary", ""),
        "FAQ_Answer__c": snippet_text,
    }


def search_aware_article_snippet(
    content_text: str,
    snippet_terms: List[str],
    max_content_chars: int = 4200,
    window_chars: int = 1000,
    max_windows: int = 4,
) -> str:
    """Extract wide windows around search/question terms from full article text."""
    if len(content_text) <= max_content_chars:
        return content_text
    matches = _term_match_positions(content_text, snippet_terms)
    if not matches:
        return _truncate_at_word(content_text, max_content_chars)

    windows = []
    for start, end, score in matches[: max_windows * 3]:
        windows.append(
            (
                max(0, start - window_chars),
                min(len(content_text), end + window_chars),
                score,
            )
        )
    merged = _merge_windows(windows)
    snippets = []
    total = 0
    for start, end in merged[:max_windows]:
        chunk = content_text[start:end].strip()
        if not chunk:
            continue
        if start > 0:
            chunk = "..." + chunk
        if end < len(content_text):
            chunk = chunk + "..."
        remaining = max_content_chars - total
        if remaining <= 0:
            break
        if len(chunk) > remaining:
            chunk = _truncate_at_word(chunk, remaining)
        snippets.append(chunk)
        total += len(chunk) + 2
    return "\n\n".join(snippets) if snippets else _truncate_at_word(content_text, max_content_chars)


def _clean_article_text(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _term_match_positions(content_text: str, snippet_terms: List[str]) -> List[tuple]:
    lowered = content_text.lower()
    matches = []
    seen = set()
    for term in snippet_terms:
        normalized = sanitize_search_term(term).lower()
        if not normalized:
            continue
        variants = [normalized]
        tokens = [token for token in normalized.split() if _is_snippet_token(token)]
        variants.extend(tokens)
        for variant in variants:
            if variant in seen:
                continue
            seen.add(variant)
            pattern = re.compile(r"\b{}\b".format(re.escape(variant)), re.IGNORECASE)
            score = max(1, len(variant.split()) * 4 + min(len(variant), 40) // 8)
            for match in pattern.finditer(lowered):
                matches.append((match.start(), match.end(), score))
    matches.sort(key=lambda item: (-item[2], item[0]))
    return matches


def _merge_windows(windows: List[tuple]) -> List[tuple]:
    if not windows:
        return []
    ordered = sorted((start, end) for start, end, _score in windows)
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def _truncate_at_word(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0].strip() + "..."


def _is_snippet_token(token: str) -> bool:
    return len(token) >= 4 and token not in {
        "what",
        "when",
        "where",
        "which",
        "with",
        "from",
        "that",
        "this",
        "they",
        "them",
        "your",
        "about",
        "should",
        "would",
        "could",
        "there",
        "their",
        "using",
        "does",
    }
