# Tasks to Evaluate
| quote_approval      | lead_qualification | case_routing        | private_customer_inf| internal_ops_data  | confidential_co_know|
| ------------------- | ------------------ | ------------------- | ------------------- | ------------------ | ------------------- |
| Header              | Title              |
| Paragraph           | Text               |

# Scaffolding

Baseline prompt + configurable scaffold variants

# Verifier
Should verify and enforce that scaffolding concerns were implemented properly

Someone's verification method on reddit

After running AI agents in production for a while, the biggest failure mode wasn’t reasoning.

It was action.

Agents:

- confidently hallucinate state
- misuse tools
- skip preconditions
- and still “succeed” according to their own logs

We tried:

- tool schemas
- retries
- confidence thresholds
- prompt warnings
- sandboxing

None of that actually answers the question:

“Should this action be allowed to happen?”
So I built a small service called Factara that sits between the agent and its tools / side effects:

Agent output → extract claims → verify against provided evidence / policy → score coverage → return {allow | deny | needs_review}
No LLM in the critical path. Deterministic checks + audit artifacts.

It’s been useful for things like:

- refunds
- account changes
- contract decisions
- approvals
- workflow steps

## Orchestrators

### Workflow Harness Ideas
 - Prompt Chaining
    - Break down complex tasks into smaller decisions
 - Router
    - Specialized path based on routing decision
 - Parallelization
    - Parallelize tasks that do not depend on each other
 - Orchestrator
    - Delegates to workers, which cary out the specialized task
 - Evaluator-Optimizer
    - Generation leads to an evaluator, iterates until satisfied
 - Reflexion
    - Learn from previous failures and encorporate into revised strategy

### Task specific modules 
quote
- Identify the quote and associated line items.
- Retrieve the applicable approval policy.
- Enumerate every policy condition.
- Distinguish failed conditions from missing evidence.
- Do not approve unless every mandatory condition is checked.

AND THIS This is not    │
  mainly hallucination; it is policy comparison failure. Add a quote scaffold: retrieve  │
  quote line items, retrieve all candidate policy articles, evaluate each policy         │
  separately, return only the article ID that is actually violated.

lead qual
- Evaluate Budget, Authority, Need, and Timeline independently.
- Retrieve evidence from structured records and relevant discussions.
- Mark each factor confirmed, contradicted, or unknown.
- Ask for clarification or retrieve more evidence when a required factor is unknown.

case routing
- Identify the case issue and relevant product or service.
- Determine routing rules and available destinations.
- Verify the destination satisfies all routing constraints.
- Prefer the least risky valid route.

conversion rate
- Define the eligible population.
- Define the converted subset.
- Apply identical filters and date ranges to numerator and denominator.
- Retrieve both values explicitly.
- Compute and sanity-check the rate before responding.

conf
- Determine whether the requester is internal or external.
- Classify the requested information.
- Retrieve only the minimum evidence needed to decide authorization.
- Refuse before querying when the request is clearly unauthorized.

## General Plan

For your selected tasks, I would prioritize:

Action validity — Is the query syntactically and schema-valid?
Evidence completeness — Has the agent retrieved every required component?
Policy grounding — Is the decision justified by the correct article or rule?
Privacy control — Is the requester authorized, and is the query minimally scoped?
Loop control — Is the agent repeating queries, stopping too early, or continuing unnecessarily?
Final-answer validation — Does the answer match the required ID/list/format?
    Procedural Scaffolding with a checklist

Current task history
↓
Compact evidence/belief state
↓
Task-family completion checklist
↓
Generate candidate next actions
↓
Syntactic/schema/privacy verifier
↓
Optional world-model simulation and scoring
↓
Commit one real action
↓
Update evidence state from real observation

### Microplanning (Clipboard adaptation)
Goal:
Determine whether quote 0Q0... violates policy.

Known:
Quote amount and overall discount retrieved.

Missing:
Line-item discounts and matching approval article.

Next action:
Retrieve line items for this quote.


## Changes
quote clipboard: evidence based, not retrieval deterministic, less context
try new scaffolding on other tasks