# CRMArena Result Summary

Source: `results/b2b_multi-turn/react_openai_Qwen3.5-35B-A3B_ablation30_ablation30_clipboardv2_scaffold_syntaxold_20260724_0046_quote_clipboardv2_only_noverifier_nowm_clipboardv2`

## Overall

- Tasks: 30
- Successes: 0
- Success rate: 0.0000
- API errors: 1
- SOQL/SOSL query-error endings: 0
- Invalid-action endings: 3
- Verifier rejection events: 0
- Verifier unknown/allowed events: 0

## By Task

| task_type | n | successes | success_rate | submitted | max_turns | query_errors | invalid_actions | empty_content | api_errors | avg_reward | avg_em | avg_f1 | nonzero_rewards | avg_model_calls | avg_env_steps | avg_prompt_tokens | avg_completion_tokens | avg_total_tokens | verifier_failure_tasks | verifier_failure_events | verifier_unknown_tasks | verifier_unknown_events | top_end_reasons |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| quote_approval | 30 | 0 | 0.0000 | 24 | 1 | 0 | 3 | 0 | 1 | 0.0000 |  |  | 0 | 15.7241 | 11.0690 | 337825.9310 | 8012.7931 | 345838.7241 | 0 | 0 | 0 | 0 | Submit action:24; Invalid action:3; Max turns reached:1; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):1 |

## Top API/Run Errors

- 1: Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195)
