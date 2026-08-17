# Current EWM Runtime Plan

## Current Goal

Build a more generalizable Enterprise World Model (EWM) runtime for CRM Arena
tasks. The runtime should avoid task-family-specific deterministic workflows
where possible. Instead, it should expose a generic CRM/MCP action space,
maintain structured execution state, let the LLM perform semantic interpretation,
and use deterministic/LLM verifiers only at controlled boundaries.

The current focus is read-oriented CRM tasks, but the state and verifier design
should remain compatible with future write workflows.

## Current Architecture

- `ChatAgentEWM` is the benchmark-facing wrapper.
- `WorkflowDriver` is the generic loop:
  - initialize `InstanceFrame`;
  - compute reachable information from `EnvironmentIR`;
  - ask the LLM for a `WorkflowDecision`;
  - validate and execute backend MCP-style calls;
  - store raw `Observation`s and normalized `EvidenceItem`s;
  - let the LLM write durable `Claim`s;
  - run completion verifiers only when the LLM proposes `complete`;
  - render the verified candidate response.
- `EnvironmentIR` is built from the CRM Arena object schema for now.
- The MCP adapter currently exposes Salesforce read tools, with the intent that
  the same runtime can use a real enterprise MCP server later.

## InstanceFrame

`InstanceFrame` is the current interpretation of the user/system-visible task.
The LLM compiles it from the same benchmark prompt surface available to the
baseline agent.

Important fields:

- `goal`: what the current user is asking for.
- `request_summary`: concise description of the active request.
- `actor`: internal/external/unknown as inferred from prompt context.
- `entities_or_references`: visible IDs, names, products, cases, accounts, etc.
- `constraints`: explicit or inferable user/system constraints. We now ask the
  LLM to preserve exact prompt wording where possible instead of paraphrasing.
- `evidence_requirements`: what information is needed and whether it should come
  from the user, environment, or model reasoning.
- `outcome_contract`: what must be true before the task can be considered done.
- `response_contract`: user-facing response requirements.
- `final_answer_contract`: first-class final answer shape, if the prompt gives
  one. This is generic and is not hardcoded to a benchmark phrase.

## ExecutionState

`ExecutionState` is the mutable trajectory state. It contains:

- `history`: compact conversation history.
- `collected.observations`: raw backend/tool outputs for replay and audit.
- `collected.evidence`: normalized citable evidence items.
- `resolved`: entities, working facts, and unresolved issues.
- `derived.claims`: durable semantic memory. Claims should cite evidence IDs.
- `derived.summaries`: transient orientation notes, not durable evidence.
- `effects`: generic state/effect summaries for future write workflows.
- `actions`: planned, executed, and failed action summaries.
- `candidates`: proposed outcome/response when the model thinks it is complete.
- `completion_state`: ready/needs-action/needs-verification control state.
- `metrics`: model calls, env calls, errors, and context bookkeeping.

## Evidence And Summary Policy

Raw observations and evidence are retained internally, but not repeatedly shown
to the model.

Current model-facing behavior:

- New evidence is shown in a one-step inbox.
- If a retrieval batch is small, fresh evidence content is readable once.
- If a retrieval batch is too large, only headers/IDs are exposed; the LLM should
  query narrower terms or specific record IDs.
- Evidence IDs that have been shown are marked in
  `presented_evidence_item_ids`.
- Claims persist across turns and are the main semantic reference.
- Summaries are shown once, then marked via `presented_summary_count`; they
  should not become a second evidence store.
- Action history is compacted to what was tried, not raw prior LLM JSON.
- Verifier feedback is compacted before re-entering controller context.

## Recent Patches

- Added `final_answer_contract` to `InstanceFrame`.
- Prompt now asks the LLM to preserve exact wording for constraints and final
  answer rules where possible.
- Removed deterministic phrase scanning for `return only`; strictness must come
  from the compiled `final_answer_contract`.
- Removed hard claim text/reason truncation. The prompt still asks for concise,
  atomic claims.
- Made summaries transient one-step context.
- Compact model-facing action history to avoid replaying raw LLM decisions.
- Compact model-facing verifier feedback.
- Small fresh evidence batches expose enough content for claim extraction.
- Large fresh evidence batches expose headers/IDs only.

## Current Weak Points

- The frame compiler can still dilute exact final-answer instructions if the LLM
  does not populate `final_answer_contract` correctly.
- The completion verifier is intentionally generic. It can enforce structural
  contracts only when those contracts are explicitly represented in the frame.
- Claims can still become verbose if the model ignores prompt guidance.
- PVI remains challenging because it often needs case context, interaction
  evidence, and policy article interpretation while also obeying a strict final
  answer format.
- KQA often answers correctly but may be penalized by user follow-ups because
  the benchmark scores the final assistant response.

## Next Patches To Consider

1. Improve `final_answer_contract` compilation without hardcoded phrase scans.
   The LLM should preserve exact final-answer wording and set `strict=true` only
   when the prompt itself makes the answer shape strict.
2. Add a generic verifier check for `final_answer_contract.strict=true`.
   This already exists structurally, but should be tested against more frame
   examples.
3. Reduce persistent context further if needed:
   - keep claims durable;
   - keep summaries transient;
   - avoid feeding full verifier rationales back into the controller;
   - keep evidence inventory lightweight.
4. Run small Codex CLI smoke tests from the login node using the benchmark
   Codex account at `/work/hdd/bgtb/acheng11/.codex-bench`.
5. After smoke health looks acceptable, rerun selected KQA/PVI/CCK examples to
   check whether the new frame/summary/evidence policy reduces fallbacks and
   output-format failures.

## How To Run The Current Codex Login Smoke

See `resources/DELTA_COMMANDS.md`, section:

`Generic EWM Codex CLI Smoke Test On Login Node`

That command uses:

- `CODEX_HOME=/work/hdd/bgtb/acheng11/.codex-bench`
- `AGENT_PROVIDER=codex_cli`
- `AGENT_STRATEGY=ewm`
- OpenRouter GPT-4o for user and judge
- `MAX_TURNS=4`
- `MAX_USER_TURNS=4`
- `EWM_MAX_STEPS=10`

