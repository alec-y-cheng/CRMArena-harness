# External-Facing Symbolic Agent Plan

## Goal

Build a shared external-facing symbolic agent layer for CRMArena customer
interactions, starting with the two normal external tasks:

- `knowledge_qa`
- `named_entity_disambiguation`

The same layer should later become the basis for confidentiality benchmarks.
For v1, the goal is not to make a free-form ReAct agent smarter. The goal is to
separate responsibilities:

- the LLM parses natural language into strict JSON slots;
- the symbolic layer decides which fixed action templates can run;
- task-specific drivers retrieve evidence with deterministic SOQL/SOSL;
- parsers validate all model outputs against bounded schemas;
- final renderers only expose customer-appropriate answers.

## Core Design Principle

The external-facing agent has one shared router plus task-specific deterministic
drivers.

```text
customer message
  -> external router JSON
  -> pre-retrieval gate
  -> task-specific DSL driver
  -> post-retrieval evidence gate
  -> answer extraction / candidate selection
  -> final-response gate
  -> customer response
```

The router may classify and request clarification. It does not generate SOQL,
SOSL, arbitrary tools, or final answers from raw context.

## What Is Fixed vs LLM-Parsed

Fixed by symbolic code:

- available routes;
- allowed evidence classes;
- disallowed evidence classes;
- subject scopes;
- all SOQL/SOSL templates;
- ownership/date/product eligibility checks;
- parser validation;
- final answer shape.

Parsed by the LLM:

- customer intent;
- product/entity phrase;
- purchase-time expression;
- public article search terms;
- whether a customer question is too vague;
- semantic match between retrieved evidence and the request;
- natural wording of clarification questions.

The LLM chooses from a fixed vocabulary. If it invents a route, action label,
evidence type,
or invalid JSON shape, the parser rejects it and the model can retry.

## Shared External Router

Package: `dsl/external_facing`

Purpose:

```text
Given the customer conversation, determine what kind of external-facing request
this is, what broad actions would retrieve the answer, and what evidence types
those actions would expose.
```

The router emits `ExternalRequestRoute`:

```json
{
  "request_type": "knowledge_qa|named_entity_disambiguation|confidential_request|unknown",
  "route": "knowledge_qa|named_entity_disambiguation|clarify|refuse|unsupported",
  "expected_actions": ["query_public_knowledge_articles"],
  "evidence_required": [
    {
      "evidence_type": "public_product_support",
      "subject_scope": "public|current_customer|other_customer|internal_company|unknown",
      "reason": "why this evidence is needed"
    }
  ],
  "subject_scope": "public|current_customer|other_customer|internal_company|unknown",
  "clarification_needed": false,
  "clarification_requirements": [],
  "disallowed_information": [],
  "reason": "short grounded routing rationale"
}
```

The parser validates:

- `route` is one of the allowed route labels;
- `expected_actions` uses only fixed symbolic action labels;
- `evidence_required` is a list of fixed evidence types with subject scopes;
- `subject_scope` is one known scope;
- `disallowed_information` uses only fixed disallowed evidence types;
- clarification/refusal states are internally consistent.

## Evidence Taxonomy

Expected action labels:

- `query_public_knowledge_articles`
- `query_product_catalog`
- `query_current_customer`
- `query_purchase_history`
- `query_order_history`
- `query_case_status`
- `ask_clarification`
- `refuse`

Allowed/customer-visible evidence types for v1:

- `public_product_support`
- `public_warranty_or_returns`
- `public_service_channel`
- `public_troubleshooting`
- `product_catalog`
- `current_customer_profile`
- `current_customer_purchase_history`
- `current_customer_order_history`
- `current_customer_case_status`

Sensitive/disallowed evidence types for confidentiality support:

- `other_customer_profile`
- `other_customer_purchase_history`
- `other_customer_case_history`
- `internal_operations_metric`
- `internal_agent_performance`
- `confidential_company_knowledge`
- `internal_sales_policy`
- `internal_quote_policy`
- `lead_qualification_policy`
- `quote_approval_policy`
- `case_routing_policy`
- `non_public_knowledge_article`
- `unknown`

The deterministic privacy gate operates on `evidence_required`, not just on
`expected_actions`. This matters because the same retrieval action, especially a
Knowledge__kav query, can expose either public support evidence or confidential
company evidence depending on the user's question.

## Router Control Flow

For every external-facing task:

1. Start with the customer message and metadata.
2. Ask the router model for strict route JSON.
3. Parse and validate the route.
4. If route is `clarify`, ask one clarification question and append the user
   response to conversation history; repeated clarification falls back to a
   concise unavailable/refusal response.
5. If route is `refuse`, render a concise customer-facing refusal.
6. If route is `unsupported`, return a bounded unsupported response.
7. If route is `knowledge_qa`, delegate to `KnowledgeQADSLDriver`.
8. If route is `named_entity_disambiguation`, delegate to
   `NamedEntityDisambiguationDSLDriver`.

The router can be retried only for malformed JSON or invalid enum values. It
should not enter an unbounded agent loop.

## Clarification Behavior

Clarification is generic. The deterministic layer decides that information is
missing; the LLM phrases the question.

Examples of missing information:

- vague public-support question;
- missing product kind;
- missing purchase timeframe;
- ambiguous purchased product candidates;
- missing customer context for customer-scoped evidence.

Clarification prompt inputs:

- current route or task-specific extraction JSON;
- `clarification_requirements`;
- conversation history;
- a rule to ask exactly one customer-facing question.

Clarification output:

```json
{
  "question": "one concise customer-facing question?"
}
```

The parser rejects non-questions, multi-line answers, internal implementation
details, or references to Salesforce/JSON/schemas.

## Knowledge QA Driver

Package: `dsl/knowledge_qa`

Purpose:

```text
Answer customer-facing support or product-policy questions using public
Knowledge__kav evidence.
```

Workflow:

1. Receive routed `knowledge_qa` request.
2. LLM extracts a search plan:
   - normalized question;
   - search terms;
   - product/service terms;
   - expected answer type, such as direct fact, yes/no, steps, or policy.
3. Pre-retrieval gate confirms the request needs only
   `public_knowledge_article` and optionally `product_catalog`.
4. Symbolic layer compiles deterministic Knowledge__kav SOSL/SOQL.
5. Retrieve candidate articles.
6. Build search-aware snippets with wide context windows around matched terms.
7. LLM extracts the narrow answer from the retrieved article evidence.
8. Parser validates:
   - cited article ids were retrieved;
   - answer is non-empty unless no answer is supported;
   - bare yes/no answers include enough customer-facing explanation when needed.
9. Final renderer returns a concise grounded answer.

The LLM reads retrieved article context and chooses relevant evidence, but it
does not create article queries directly.

## Named Entity Disambiguation Driver

Package: `dsl/named_entity_disambiguation`

Purpose:

```text
Resolve a customer's natural-language reference to a purchased product/entity
into a concrete Product2.Id, or return None.
```

Workflow:

1. Receive routed `named_entity_disambiguation` request.
2. LLM extracts slots:
   - entity phrase;
   - product terms;
   - attributes;
   - purchase date or relative timeframe;
   - clarification need.
3. Deterministically normalize date window using task metadata such as today's
   date.
4. Deterministic slot checker decides whether the request is actionable.
   - Generic phrases like "my purchase" need product kind or attributes.
   - Missing timeframe needs clarification when timeframe materially scopes the
     purchase search.
5. If missing information exists, call the generic LLM clarification renderer.
6. Retrieve current customer/contact context.
7. Retrieve purchase/order history scoped to the current customer's account and
   normalized date window.
8. Retrieve product catalog details for purchased `Product2Id` values and
   optional product search terms.
9. LLM selects the best candidate from eligible retrieved purchases.
10. Parser validates selected `Product2.Id` is in retrieved customer purchase
    evidence.
11. If ambiguous, ask one clarification question and rerun with the appended
    user response.
12. Final renderer returns exactly `Product2.Id` or `None`.

Ownership and date eligibility remain deterministic. Semantic matching between
customer wording and candidate products is handled by the LLM.

## Gate Placement

The external-facing gate should run in three places.

Pre-retrieval gate:

- Checks whether the planned evidence classes are allowed for the current
  external customer.
- Blocks internal policies, other-customer records, and non-public evidence
  before any query is issued.

Post-retrieval gate:

- Checks whether retrieved records match the intended safe evidence class.
- Removes or blocks records outside current-customer scope.
- Prevents accidental exposure of fields that are not needed downstream.

Final-response gate:

- Checks whether the generated answer exposes only allowed evidence.
- Refuses if the answer reveals internal policy, other-customer information, or
  confidential operational data.

For current normal external tasks, these gates should mostly pass. They are
included now so confidentiality support can be added without rewriting the
drivers.

## Future Confidentiality Extension

Confidentiality benchmarks can reuse the same router and gates.

Additional behavior later:

1. Router identifies disallowed requested evidence.
2. Pre-retrieval gate refuses before task delegation when the evidence class is
   not customer-visible.
3. During multi-turn conversations, every new customer message is routed again
   because a harmless initial request can become confidential later.
4. Task-specific drivers declare intended retrieval before executing each
   action.
5. Final-response gate prevents leaking sensitive evidence even if retrieved
   accidentally.

This lets normal external task accuracy and confidentiality behavior share the
same architecture.

## Implementation Stages

Stage 1: Solidify `knowledge_qa`

- Keep the deterministic article retrieval workflow.
- Improve answer narrowing and citation validation.
- Log article ids, snippets, search terms, answer JSON, and F1/EM metrics.

Stage 2: Solidify `named_entity_disambiguation`

- Keep deterministic customer/date/purchase retrieval.
- Use LLM only for slot extraction, clarification wording, and candidate
  selection.
- Log extracted slots, normalized date window, eligible purchases, selected
  product id, ambiguity, and clarification turns.

Stage 3: Implement shared external router

- Fill `dsl/external_facing/actions.py`, `parser.py`, `prompts.py`, `schemas.py`,
  and `harness.py`.
- Add route JSON structured output support in `ChatAgentDSL`.
- Add tests for route parsing, evidence enums, clarification/refusal routing,
  and gate decisions.

Stage 4: Put router in front of KQA/NED

- For external task runs, call the router first.
- Delegate to the existing task driver when route is clear.
- Ask clarification/refuse directly when route requires it.
- Preserve task-specific direct toggles for ablations.

Stage 5: Add confidentiality support

- Expand route examples and gate tests.
- Add per-action intended evidence declarations.
- Add post-retrieval record filtering.
- Add final-response safety checks.

## Logging Requirements

Log enough for ablations and debugging:

- router JSON and retries;
- route parse errors;
- pre-retrieval gate decisions;
- delegated task family;
- clarification questions and user responses;
- intended evidence classes for each retrieval;
- query strings and record counts;
- retrieved object ids;
- post-retrieval gate decisions;
- task-specific extraction JSON;
- final answer JSON;
- final-response gate decision;
- time to resolution;
- model calls;
- environment calls;
- reward/score.

## Test Plan

External router tests:

- public support question routes to `knowledge_qa`;
- purchased-product lookup routes to `named_entity_disambiguation`;
- vague request routes to `clarify`;
- internal/confidential request routes to `refuse`;
- parser rejects invented action labels, evidence types, scopes, and routes.

Knowledge QA tests:

- parse article search plan JSON;
- compile safe Knowledge__kav retrieval;
- use search-aware snippets;
- parser rejects uncited article ids;
- answer renderer stays grounded and concise.

Named entity disambiguation tests:

- parse product phrase and date expression;
- normalize relative dates using metadata `today`;
- trigger clarification for generic product phrase or missing timeframe;
- retrieve only current-customer purchase history;
- reject selected Product2.Id not present in eligible purchases;
- return Product2.Id or `None`.

Gate tests:

- allow public support evidence;
- allow `current_customer_purchase_history` for `current_customer`;
- block `other_customer_purchase_history`;
- block internal/confidential policy evidence;
- block final answers that reveal disallowed evidence.

Evaluation progression:

1. 30-task smoke test for `knowledge_qa`.
2. Full `knowledge_qa`.
3. 30-task smoke test for `named_entity_disambiguation`.
4. Full `named_entity_disambiguation`.
5. Router-fronted KQA/NED smoke tests.
6. Later: confidentiality benchmarks using the same router/gate.
