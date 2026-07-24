# Quote Approval Procedural Clipboard Plan

## Summary

Implement an orchestrator-owned procedural clipboard for `quote_approval` tasks only.

The clipboard should track retrieval progress for quote approval evidence. The model may read the rendered clipboard in temporary prompt context, but it must never edit clipboard state directly. State updates must come only from accepted actions, parsed query facts, Salesforce execution status, and returned observations.

This is not a semantic quote-approval judge. It should help the agent retrieve necessary evidence before answering, then stop at `evaluate_policy`.

## Pushback and Constraints

- Do not use the model's `<thought>` as state. Thoughts can be wrong or self-serving; only accepted actions and environment observations should update state.
- Do not have the clipboard decide approval, rejection, or policy correctness. That would become task reasoning and risks benchmark-specific leakage.
- The response gate should only block premature `<respond>` when required evidence has not been retrieved. Once quote, line items, candidate policies, and at least one detailed policy have been retrieved, the gate should return `UNKNOWN`/allow rather than claiming the final answer is valid.
- Empty query results should not count as retrieval. A successful Salesforce call with zero records is useful evidence, but it should not satisfy `quote_retrieved`, `line_items_retrieved`, or `policy_inspected`.
- Keep this feature behind a CLI flag so baseline, scaffold-only, verifier-only, and quote-clipboard runs remain separable.

## Key Changes

### State Model

Add a quote-specific clipboard state under the task clipboard package, such as `crm_sandbox/agents/clipboards/quote.py`.

```python
@dataclass
class QuoteClipboard:
    stage: str = "retrieve_quote"
    next_goal: str = "Retrieve the target quote."

    quote_retrieved: bool = False
    quote_id: str | None = None
    quote_fields: dict = field(default_factory=dict)

    line_items_retrieved: bool = False
    line_item_count: int = 0
    line_items: list[dict] = field(default_factory=list)

    candidate_policies: dict[str, dict] = field(default_factory=dict)
    inspected_policy_ids: set[str] = field(default_factory=set)

    failed_queries: list[str] = field(default_factory=list)
```

Also add a controller class, for example `QuoteApprovalClipboard`, with:

- `reset(query, routing_result=None)`
- `record_env_step(action, observation, info)`
- `record_verifier_failure(action, error_code)`
- `render()`
- `as_dict()`
- `response_gate(action) -> VerificationResult`

The interface should mirror the existing `WorkingMemory` enough that `ChatAgent` can use either or both without special-case clutter.

### Query and Observation Facts

Use lightweight deterministic extraction rather than a full SOQL evaluator.

Extract `QueryFacts` from accepted `execute` content:

- query type: SOQL/SOSL/unknown;
- referenced objects;
- selected fields when cheap to extract;
- whether the query targets `Quote`;
- whether it targets quote line items, such as `QuoteLineItem`;
- whether it searches knowledge/policy objects;
- whether it retrieves detailed policy content versus only title/id metadata.

Parse `ObservationFacts` from Salesforce output:

- whether execution failed via `info["end_reason"]`;
- whether records were returned;
- record count;
- object-ish record fields;
- returned ids and names/titles where present.

Implementation can use `ast.literal_eval`/JSON parsing for observation strings, with a safe fallback to compact text. Do not call an LLM or Salesforce again during parsing.

### State Update Rules

Update the clipboard after each accepted `execute` action:

- Failed query: append normalized query to `failed_queries`; do not update retrieval booleans.
- Empty successful result: keep retrieval booleans false; update `next_goal` to refine the query.
- Successful `Quote` result: set `quote_retrieved=True`, store `quote_id` when present, and store compact `quote_fields`.
- Successful `QuoteLineItem` result: set `line_items_retrieved=True`, set `line_item_count`, and store compact line items.
- Successful knowledge/policy search: add returned candidate policies keyed by id when available, otherwise by stable title/name fallback.
- Detailed query for one policy: mark that policy as inspected only if returned fields include substantive content/body/answer/details, not just id/title/url metadata.

After every state update, call deterministic stage selection.

### Stage Selection and Rendering

Use deterministic stages:

```python
if not quote_retrieved:
    retrieve_quote
elif not line_items_retrieved:
    retrieve_line_items
elif not candidate_policies:
    retrieve_candidate_policies
elif not inspected_policy_ids:
    inspect_candidate_policies
else:
    evaluate_policy
```

Render the clipboard into temporary context only, following the same principle as `WorkingMemory._messages_with_working_memory`.

Example render:

```text
# Quote approval clipboard

Stage: inspect_candidate_policies
Next goal: Inspect the contents of plausible policies.

Retrieved:
- Quote: yes
- Quote line items: yes
- Candidate policies: 3
- Policies inspected: 1

Important:
- This clipboard tracks retrieval only.
- Do not claim an uninspected policy was evaluated.
```

Keep the render short, roughly 700-1000 characters by default.

### Response Gate

Add a deterministic pre-execution gate for `respond` actions when quote clipboard is enabled.

Reject premature `respond` with targeted feedback if:

- quote was not retrieved;
- quote line items were not retrieved;
- no candidate policies were found;
- no candidate policy was inspected in detail.

Once all retrieval prerequisites are satisfied, return an allowed/unknown result. Do not approve semantic answer quality.

Integrate this gate inside the existing verifier retry loop after the action parser and before `env.step(action)`. If syntactic verifier is also enabled, both gates should run before execution:

```text
model output
-> parser
-> syntactic verifier when enabled
-> quote clipboard response gate when enabled
-> env.step(action)
```

Rejected response-gate attempts should be added only to the local retry context, just like syntactic verifier repairs, so failed attempts do not bloat persistent history after an accepted action.

### CLI and Logging

Add a CLI flag to `run_tasks.py` and wrapper support in `run_tasks_crmarena_pro.sh`:

- `--use_quote_clipboard`
- env var: `USE_QUOTE_CLIPBOARD=true|false`

Enable it only for `quote_approval` tasks. If the flag is on for other tasks, initialize no quote clipboard and log that it was inactive.

Log snapshots under:

```python
agent_info["quote_clipboard_enabled"] = bool(...)
agent_info["quote_clipboard_active"] = task_family == "quote_approval"
agent_info["quote_clipboard_snapshots"].append(
    {
        "turn": current_turn,
        "event": "reset|accepted_execute|respond_gate_failure|verifier_failure",
        "stage": state.stage,
        "state": asdict(state),
        "rendered": render_quote_clipboard(state),
    }
)
```

Also log response-gate failures separately:

```python
agent_info["quote_clipboard_gate_failures"].append(
    {
        "outer_turn": current_turn,
        "attempt": verifier_attempt + 1,
        "error_code": "...",
        "feedback": "...",
        "raw_output": stripped_content,
        "parsed_action": action,
    }
)
```

## Tests

Add unit tests for the quote clipboard object:

- successful quote query updates quote state;
- failed query does not update quote state and records `failed_queries`;
- empty successful query does not mark retrieval complete;
- quote line item query updates line item state and count;
- policy search adds candidate policies;
- title/id-only policy retrieval does not count as detailed inspection;
- detailed policy retrieval marks policy inspected;
- stage transitions occur in the expected order;
- render output includes stage, next goal, and retrieval counts;
- response gate blocks premature `<respond>` at each missing retrieval step;
- response gate allows/returns unknown after all retrieval prerequisites are complete.

Add integration-style tests around `ChatAgent` if practical:

- quote clipboard block is injected only in temporary model-call context;
- rejected gate attempts are not appended to persistent `self.messages` after an accepted action;
- non-quote tasks do not activate quote clipboard even when the flag is enabled.

Run at minimum:

```bash
cd /work/11669/aleccheng/vista/CRMArena
source .venv/bin/activate
PYTHONPATH=. python -m unittest crm_sandbox.orchestration.tests.test_router
PYTHONPATH=. python -m unittest discover crm_sandbox/agents/tests
```

## Acceptance Criteria

- Existing baseline behavior is unchanged when `--use_quote_clipboard` is absent.
- Quote approval runs with the flag show `quote_clipboard_snapshots` in result JSON.
- The model sees concise retrieval state and next goal before each call.
- The clipboard is updated only from accepted actions and observations.
- The response gate prevents premature final answers without deciding semantic quote compliance.
- Persistent trajectory context includes only accepted assistant actions and real observations, not rejected gate-retry attempts.
