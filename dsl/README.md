# DSL strategies

`run_tasks.py --agent_strategy` selects the harness. Use `lead_dsl` for the older task-specific drivers and `general_dsl` for the shared workflow runtime used in the seven-task experiment. [Strategy selection](../run_tasks.py)

## `lead_dsl` — task-specific drivers

Each driver encodes its procedure in Python. For example, the lead qualification driver collects Salesforce evidence, asks the model to extract Budget, Authority, Need, and Timeline, then applies the qualification rules and formats the answer. The same strategy also dispatches to separate quote approval, case routing, knowledge QA, and named entity disambiguation drivers when enabled. It is a bespoke harness that is generated for a specific task, in conjunction with an orchestration harness to route to the appropriate task.


## `general_dsl` — shared workflow runtime

1. The router selects a supported workflow. With `USE_EXTERNAL_ROUTER_DSL=true`, the external router can refuse a restricted request before the first Salesforce query.
2. The driver loads a checked-in JSON `WorkflowSpec` defining the evidence, allowed actions, and answer format. This is generated from feeding an LLM the appendix of the paper as context, which contains examples, expected answer formats, and anticipated actions. The model fills an `InstanceFrame` with request details such as a record ID, search terms, or a date window.
3. Python runs the configured Salesforce actions and stores the results in `ExecutionState`. The model interprets the evidence. The driver applies external disclosure checks where relevant and formats the answer.

The seven-task experiment uses four specs (`knowledge_qa`, `named_entity_disambiguation`, `wrong_stage_rectification`, and `policy_violation_identification`) and the shared refusal path for the three confidentiality categories. Tasks outside this set fall back to the older agent. [Shared driver](general_runtime/driver.py) · [Workflow specs](general_runtime/workflow_specs/) · [Routing and fallback](../crm_sandbox/agents/chat_agent_general_runtime_dsl.py)

## Comparing the strategies

Use knowledge QA and named entity disambiguation for a direct comparison. Both have a bespoke driver and a shared-runtime spec. Set `USE_EXTERNAL_ROUTER_DSL=true` for both runs and use the same task IDs, agent model, simulated user, and judge. Compare task success, Salesforce reads, model calls, latency, and tokens. Lead qualification reaches the same bespoke driver under both strategy names.
