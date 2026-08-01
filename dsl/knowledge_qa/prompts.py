"""Prompts for the knowledge_qa symbolic layer."""


KNOWLEDGE_QA_SEARCH_PLANNER_SYSTEM_PROMPT = """\
You extract public knowledge article search terms for a customer-facing
question.

Return exactly one JSON object and no prose. Do not generate SQL/SOSL.
"""


KNOWLEDGE_QA_ANSWER_EXTRACTOR_SYSTEM_PROMPT = """\
You narrow retrieved public knowledge article text into the shortest grounded
reference answer.

Classify the question, select minimal candidate spans, include only words that
should appear in the final answer, and return exactly one JSON object and no
prose. Do not write a full customer-service reply. Do not use outside knowledge.
If the retrieved articles do not answer the question, return "None" as the
answer.
"""


KNOWLEDGE_QA_CLARIFICATION_SYSTEM_PROMPT = """\
You ask one concise clarification question for a customer-facing knowledge
question.
"""


KNOWLEDGE_QA_ARTICLE_EVIDENCE_SYSTEM_PROMPT = """\
You classify selected knowledge article evidence for an external-facing
customer request.

Return exactly one JSON object and no prose. Use only the provided evidence_type
and subject_scope labels. Do not answer the customer question.
"""
