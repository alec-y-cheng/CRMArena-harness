# CRMArena 30-Sample Ablation Comparison

## Overall

| run | n | successes | success_rate | api_errors | invalid_actions | query_error_endings | max_turns |
| --- | --- | --- | --- | --- | --- | --- | --- |
| syntactic_verifier_only | 180 | 43 | 0.2389 | 20 | 9 | 0 | 1 |
| syntax_verifier_v2 | 180 | 48 | 0.2667 | 15 | 10 | 0 | 2 |
| routing_only | 180 | 56 | 0.3111 | 16 | 3 | 0 | 3 |
| working_memory_only | 180 | 56 | 0.3111 | 11 | 9 | 2 | 9 |

## By Task

| run | task_type | n | successes | success_rate | api_errors | invalid_actions | query_error_endings | max_turns |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| syntactic_verifier_only | case_routing | 30 | 1 | 0.0333 | 4 | 1 | 0 | 0 |
| syntactic_verifier_only | confidential_company_knowledge | 30 | 12 | 0.4000 | 6 | 0 | 0 | 0 |
| syntactic_verifier_only | internal_operation_data | 30 | 10 | 0.3333 | 3 | 6 | 0 | 1 |
| syntactic_verifier_only | lead_qualification | 30 | 9 | 0.3000 | 2 | 1 | 0 | 0 |
| syntactic_verifier_only | private_customer_information | 30 | 8 | 0.2667 | 5 | 1 | 0 | 0 |
| syntactic_verifier_only | quote_approval | 30 | 3 | 0.1000 | 0 | 0 | 0 | 0 |
| syntax_verifier_v2 | case_routing | 30 | 3 | 0.1000 | 4 | 2 | 0 | 0 |
| syntax_verifier_v2 | confidential_company_knowledge | 30 | 14 | 0.4667 | 2 | 0 | 0 | 0 |
| syntax_verifier_v2 | internal_operation_data | 30 | 9 | 0.3000 | 3 | 6 | 0 | 2 |
| syntax_verifier_v2 | lead_qualification | 30 | 13 | 0.4333 | 1 | 0 | 0 | 0 |
| syntax_verifier_v2 | private_customer_information | 30 | 6 | 0.2000 | 3 | 2 | 0 | 0 |
| syntax_verifier_v2 | quote_approval | 30 | 3 | 0.1000 | 2 | 0 | 0 | 0 |
| routing_only | case_routing | 30 | 4 | 0.1333 | 6 | 0 | 0 | 0 |
| routing_only | confidential_company_knowledge | 30 | 18 | 0.6000 | 1 | 0 | 0 | 0 |
| routing_only | internal_operation_data | 30 | 11 | 0.3667 | 4 | 3 | 0 | 2 |
| routing_only | lead_qualification | 30 | 10 | 0.3333 | 1 | 0 | 0 | 1 |
| routing_only | private_customer_information | 30 | 11 | 0.3667 | 1 | 0 | 0 | 0 |
| routing_only | quote_approval | 30 | 2 | 0.0667 | 3 | 0 | 0 | 0 |
| working_memory_only | case_routing | 30 | 2 | 0.0667 | 4 | 2 | 0 | 2 |
| working_memory_only | confidential_company_knowledge | 30 | 19 | 0.6333 | 2 | 0 | 0 | 0 |
| working_memory_only | internal_operation_data | 30 | 11 | 0.3667 | 1 | 5 | 1 | 4 |
| working_memory_only | lead_qualification | 30 | 9 | 0.3000 | 1 | 0 | 0 | 3 |
| working_memory_only | private_customer_information | 30 | 12 | 0.4000 | 2 | 2 | 0 | 0 |
| working_memory_only | quote_approval | 30 | 3 | 0.1000 | 1 | 0 | 1 | 0 |

## Overnight Ablations - 2026-07-24

Source run prefix: `ablation30_clipboardv2_scaffold_syntaxold_20260724_0046`.

All three runs completed successfully and had no duplicate result rows.

### Overall Results

| run | scope | n | successes | success_rate | notes |
| --- | --- | ---: | ---: | ---: | --- |
| baseline_first30_from_full_run | all 6 focus tasks | 180 | 36 | 0.2000 | Derived from the full unmodified baseline using the first 30 task IDs per family. |
| quote_clipboardv2_only | quote_approval only | 30 | 0 | 0.0000 | Clipboard activated, but performance collapsed. |
| new_scaffolding_only | quote_approval, lead_qualification, case_routing | 90 | 16 | 0.1778 | Improved the changed-task subset vs baseline first30: 12/90 -> 16/90. |
| syntax_oldwm_oldprompt | all 6 focus tasks | 180 | 43 | 0.2389 | Better than baseline first30, but below prior routing-only and working-memory-only runs. |

### By Task

| run | quote_approval | lead_qualification | case_routing | private_customer_information | internal_operation_data | confidential_company_knowledge |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline_first30_from_full_run | 2/30 | 9/30 | 1/30 | 4/30 | 5/30 | 15/30 |
| quote_clipboardv2_only | 0/30 | - | - | - | - | - |
| new_scaffolding_only | 4/30 | 10/30 | 2/30 | - | - | - |
| syntax_oldwm_oldprompt | 4/30 | 9/30 | 4/30 | 8/30 | 6/30 | 12/30 |

### What Went Well

- The new task scaffolding was directionally positive on the three task families it touched: `quote_approval`, `lead_qualification`, and `case_routing` moved from 12/90 in the matched baseline subset to 16/90.
- `quote_approval` improved from 2/30 baseline to 4/30 with new scaffolding, and also 4/30 under syntax+old working memory. It is still low, but the prompt-level final-answer contract looks more promising than the procedural quote clipboard v2.
- `case_routing` improved most under syntax+old working memory: 1/30 baseline to 4/30. This suggests routing may benefit from either more explicit state tracking or stronger constraints around candidate comparison.
- The overnight run setup is healthy now: all three members completed, endpoint routing worked, and the outputs are cleanly separated.

### What Did Not Work

- `quote_clipboardv2_only` was a clear regression: 0/30. The clipboard was active on 29/30 tasks, generated 36 gate failures, and usually reached `evaluate_policy` by the final snapshot, so the issue is not simply that it got stuck before retrieval completion.
- The quote clipboard likely encouraged longer retrieval trajectories without improving the final decision. It averaged about 15.7 model calls and 11.1 environment steps on quote tasks, higher than the successful quote scaffold run. That increases context pressure and may distract from the actual benchmark answer format.
- The response gate failures were mostly early retrieval blockers: `QUOTE_CLIPBOARD_MISSING_QUOTE` occurred 26 times, `QUOTE_CLIPBOARD_MISSING_POLICY_CANDIDATES` 7 times, and `QUOTE_CLIPBOARD_MISSING_LINE_ITEMS` 3 times. Since most tasks eventually reached `evaluate_policy`, the gate probably added repair overhead but did not solve the core final-answer reasoning problem.
- `syntax_oldwm_oldprompt` improved over the matched baseline but did not beat earlier single-feature ablations: prior `routing_only` and `working_memory_only` both reached 56/180, while this combined run reached 43/180. This suggests syntax verifier + generic working memory are not automatically additive.

### Interpretation

- The strongest signal is still task-specific prompting/scaffolding, not stricter query gating. The model needs better procedural guidance about what evidence matters and how to format the final answer.
- Quote approval failures are probably dominated by policy/answer interpretation, not just missing retrieval. A retrieval clipboard that stops at `evaluate_policy` is defensible, but v2 appears too heavy as currently written.
- For quote approval, the next clipboard should be less of a retrieval checklist and more of a compact evidence ledger: target quote, relevant line item facts, policy candidates inspected, and a final-answer reminder. It should probably not block response as aggressively unless no quote or no line items were retrieved.

### Recommended Next Steps

1. Scale the new scaffolding pattern to the other non-confidential/non-privacy task families before scaling the quote clipboard. The scaffolding is cheap, low-risk, and showed a positive direction.
2. Keep `quote_clipboardv2` experimental. Do not run it at full scale yet. First revise it to reduce blocking and token overhead.
3. Add task-specific final-answer contracts for `internal_operation_data` separately from confidentiality handling. Many failures there are aggregation/date/range and invalid-action issues, not just privacy refusal.
4. For `case_routing`, test a route-specific procedural clipboard next. It should track retrieved case facts, candidate agents/queues, and tie-breaker evidence. This seems more likely to help than quote clipboard v2 because case routing failures often involve candidate comparison and forgotten constraints.
5. For `lead_qualification`, consider a compact BANT ledger rather than generic working memory: Budget, Authority, Need, Timeline as supported/contradicted/unknown with one evidence phrase each.

### Good Next Ablation Combinations

| ablation | scope | why |
| --- | --- | --- |
| scaffolding_only_v2 | all 6 focus tasks, 30 each | Test whether concise final-answer contracts generalize beyond the three changed tasks. |
| scaffolding_plus_routing | all 6 focus tasks, 30 each | Prior routing-only was strong; combine it with task contracts to test additive effects. |
| scaffolding_plus_syntax_v2 | all 6 focus tasks, 30 each | Syntax v2 reduces malformed actions; scaffolding may improve final decisions. |
| case_clipboard_only | case_routing only, 30 each | Candidate/tie-breaker tracking is likely a better fit for procedural memory than quote approval. |
| lead_bant_clipboard_only | lead_qualification only, 30 each | Lightweight state slots map cleanly to BANT and should be less token-heavy than quote clipboard. |
| quote_scaffold_plus_light_clipboard | quote_approval only, 30 each | Keep the useful quote final-answer contract, but make clipboard nonblocking or only block missing quote/line-items. |

### Practical Recommendation

Do not scale `quote_clipboardv2` as-is. Scale the scaffolding/final-answer-contract approach first, then redesign the task-specific clipboards as compact ledgers for tasks with naturally structured state: `case_routing` and `lead_qualification` first, quote approval only after reducing clipboard strictness and token overhead.

