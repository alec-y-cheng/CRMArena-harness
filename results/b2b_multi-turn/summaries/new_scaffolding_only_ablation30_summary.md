# CRMArena Result Summary

Source: `results/b2b_multi-turn/react_openai_Qwen3.5-35B-A3B_ablation30_ablation30_clipboardv2_scaffold_syntaxold_20260724_0046_new_scaffolding_only_noverifier_nowm`

## Overall

- Tasks: 90
- Successes: 16
- Success rate: 0.1778
- API errors: 4
- SOQL/SOSL query-error endings: 0
- Invalid-action endings: 2
- Verifier rejection events: 0
- Verifier unknown/allowed events: 0

## By Task

| task_type | n | successes | success_rate | submitted | max_turns | query_errors | invalid_actions | empty_content | api_errors | avg_reward | avg_em | avg_f1 | nonzero_rewards | avg_model_calls | avg_env_steps | avg_prompt_tokens | avg_completion_tokens | avg_total_tokens | verifier_failure_tasks | verifier_failure_events | verifier_unknown_tasks | verifier_unknown_events | top_end_reasons |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| case_routing | 30 | 2 | 0.0667 | 25 | 0 | 0 | 1 | 0 | 4 | 0.0667 |  |  | 2 | 19.2308 | 18.1154 | 288133.2308 | 5679.3462 | 293812.5769 | 0 | 0 | 0 | 0 | Submit action:25; Error: 'Subject':4; Invalid action:1 |
| lead_qualification | 30 | 10 | 0.3333 | 26 | 3 | 0 | 1 | 0 | 0 | 0.3333 |  |  | 10 | 11.5000 | 10.6000 | 150838.5000 | 4311.1667 | 155149.6667 | 0 | 0 | 0 | 0 | Submit action:26; Max turns reached:3; Invalid action:1 |
| quote_approval | 30 | 4 | 0.1333 | 30 | 0 | 0 | 0 | 0 | 0 | 0.1333 |  |  | 4 | 12.8333 | 12.6000 | 295480.5333 | 3518.2333 | 298998.7667 | 0 | 0 | 0 | 0 | Submit action:30 |

## Top API/Run Errors

- 4: Error: 'Subject'
