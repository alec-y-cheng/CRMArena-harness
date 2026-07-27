# CRMArena Result Summary

Source: `results/b2b_multi-turn/react_openai_Qwen3.5-35B-A3B_ablation30_ablation30_clipboardv2_scaffold_syntaxold_20260724_0046_syntax_oldwm_oldprompt_syntactic_verifier_wm`

## Overall

- Tasks: 180
- Successes: 43
- Success rate: 0.2389
- API errors: 13
- SOQL/SOSL query-error endings: 0
- Invalid-action endings: 10
- Verifier rejection events: 230
- Verifier unknown/allowed events: 5

## By Task

| task_type | n | successes | success_rate | submitted | max_turns | query_errors | invalid_actions | empty_content | api_errors | avg_reward | avg_em | avg_f1 | nonzero_rewards | avg_model_calls | avg_env_steps | avg_prompt_tokens | avg_completion_tokens | avg_total_tokens | verifier_failure_tasks | verifier_failure_events | verifier_unknown_tasks | verifier_unknown_events | top_end_reasons |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| case_routing | 30 | 4 | 0.1333 | 21 | 5 | 0 | 2 | 2 | 2 | 0.1333 |  |  | 4 | 22.4286 | 16.9643 | 510801.7500 | 8028.0357 | 518829.7857 | 23 | 75 | 1 | 1 | Submit action:21; Max turns reached:5; Invalid action:2; Error: 'Subject':1 |
| confidential_company_knowledge | 30 | 12 | 0.4000 | 25 | 0 | 0 | 1 | 1 | 4 | 0.4000 |  |  | 12 | 10.0385 | 8.3846 | 216043.4231 | 3671.9231 | 219715.3462 | 10 | 19 | 0 | 0 | Submit action:25; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):3; Error: 'Name':1; Invalid action:1 |
| internal_operation_data | 30 | 6 | 0.2000 | 18 | 4 | 0 | 5 | 1 | 3 | 0.2000 |  |  | 6 | 19.0000 | 11.1111 | 280079.7037 | 9497.2593 | 289576.9630 | 24 | 74 | 3 | 4 | Submit action:18; Invalid action:5; Max turns reached:4; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):3 |
| lead_qualification | 30 | 9 | 0.3000 | 26 | 3 | 0 | 1 | 0 | 0 | 0.3000 |  |  | 9 | 11.7667 | 10.3333 | 161065.3333 | 4609.4667 | 165674.8000 | 12 | 22 | 0 | 0 | Submit action:26; Max turns reached:3; Invalid action:1 |
| private_customer_information | 30 | 8 | 0.2667 | 26 | 0 | 0 | 1 | 0 | 3 | 0.2667 |  |  | 8 | 11.7407 | 9.9630 | 95141.4444 | 3813.4074 | 98954.8519 | 12 | 29 | 0 | 0 | Submit action:26; Error: 'AccountId':1; Error: 'Name':1; Invalid action:1 |
| quote_approval | 30 | 4 | 0.1333 | 28 | 1 | 0 | 0 | 0 | 1 | 0.1333 |  |  | 4 | 11.0345 | 9.7241 | 367183.9310 | 4636.4828 | 371820.4138 | 9 | 11 | 0 | 0 | Submit action:28; Max turns reached:1; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):1 |

## Top API/Run Errors

- 9: Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195)
- 2: Error: 'Name'
- 1: Error: 'Subject'
- 1: Error: 'AccountId'
