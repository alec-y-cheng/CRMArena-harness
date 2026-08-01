# AGENTS.md

## Project Context

This workspace is for research and engineering on **CRMArena-Pro** on an HPC cluster.

The broader goal is to improve CRM agent performance through lightweight orchestration and harnessing, including:

- task routing and task-specific prompts;
- deterministic action and SOQL/SOSL validation;
- compact procedural or evidence clipboards;
- task-specific scaffolds for quote approval, lead qualification, case routing, and confidentiality;
- final-answer formatting and readiness checks;
- later integration of a world model for candidate-action simulation and ranking.

Prioritize changes that are measurable, modular, and easy to ablate against the original CRMArena baseline.

## Working Style

Work incrementally. Prefer small, testable changes over large rewrites.

Before making broad architectural changes:

1. inspect the relevant code path;
2. explain the proposed change;
3. make the smallest useful implementation;
4. run focused tests;
5. summarize what changed and why.

Do not proceed substantially beyond the requested scope without asking first. If you disagree with the requested approach or see a better alternative, explain the concern and consult me before changing direction.

## Command Execution

Do not wait indefinitely on long-running commands, benchmark jobs, model serving, package builds, or cluster jobs.

For long commands:

- provide the exact command for me to run;
- explain what output or log file to inspect;
- explain how to tell whether it succeeded;
- provide follow-up commands for checking status or debugging failures.

For short commands and focused tests, run them directly when practical.

Do not launch expensive benchmark, training, serving, or batch jobs unless explicitly requested.

## Script Changes

When editing a script:

- preserve existing behavior unless the requested change requires otherwise;
- avoid unrelated cleanup or refactoring;
- explain each important change and the reasoning behind it;
- identify assumptions and likely failure modes;
- add focused tests or validation when practical.

At the end, provide the exact commands I should run, including:

- syntax or compile checks;
- unit tests;
- a small smoke test;
- the larger benchmark or batch command, when relevant.

Use commands appropriate to the current workspace and HPC cluster. Do not assume paths, environments, accounts, partitions, or module names from another cluster.

## CRMArena-Specific Guidelines

Keep these layers conceptually separate:

- **Task router:** chooses the appropriate task scaffold from visible context.
- **Prompt scaffold:** guides reasoning for a task family.
- **Clipboard:** summarizes retrieved evidence or procedural state for the next model call.
- **Action verifier:** checks whether an action is mechanically executable.
- **Task-specific verifier:** checks narrow policy, confidentiality, workflow, readiness, or answer-contract conditions.
- **World model:** predicts likely future observations or state transitions for candidate actions.

Do not mix task-answer logic into the syntactic verifier.

When verifier confidence is low, prefer logging and allowing the action over making an overconfident rejection.

Preserve CRMArena's required ReAct output format unless explicitly changing the parser:

```text
<thought>one concise thought</thought>
<execute>valid SOQL or SOSL query</execute>
```

or:

```text
<thought>one concise thought</thought>
<respond>message to the user</respond>
```

Do not append rejected internal repair attempts to persistent trajectory history unless explicitly requested. Keep temporary repair context separate and log rejected attempts for analysis.

## Evaluation Discipline

For every intervention, define:

- the intended failure mode;
- the baseline;
- the ablation condition;
- direct metrics;
- downstream task-success metrics;
- added model calls, environment calls, latency, and token cost.

Do not claim that a component improves task reasoning merely because it reduces malformed actions.

Prefer replay tests and small focused evaluations before full benchmark runs.

## Communication

Always summarize:

- files changed;
- behavior changed;
- reasoning behind the change;
- tests run;
- tests not run;
- commands I should run next;
- remaining risks or uncertainties.

Be direct about incomplete results, uncertain assumptions, and failures.
