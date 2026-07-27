# CRMArena Result Summary

Source: `results/b2b_multi-turn/react_openai_Qwen3.5-35B-A3B_base_default_full_noverifier`

## Overall

- Tasks: 458
- Successes: 99
- Success rate: 0.2162
- API errors: 36
- SOQL/SOSL query-error endings: 1
- Invalid-action endings: 24
- Verifier rejection events: 0
- Verifier unknown/allowed events: 0

## By Task

| task_type | n | successes | success_rate | submitted | max_turns | query_errors | invalid_actions | empty_content | api_errors | avg_reward | avg_em | avg_f1 | nonzero_rewards | avg_model_calls | avg_env_steps | avg_prompt_tokens | avg_completion_tokens | avg_total_tokens | verifier_failure_tasks | verifier_failure_events | verifier_unknown_tasks | verifier_unknown_events | top_end_reasons |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| case_routing | 100 | 14 | 0.1400 | 82 | 5 | 1 | 3 | 2 | 9 | 0.1400 |  |  | 14 | 17.4945 | 15.8791 | 239625.2637 | 5517.0000 | 245142.2637 | 0 | 0 | 0 | 0 | Submit action:82; Max turns reached:5; Invalid action:3; Error: 'Subject':2 |
| confidential_company_knowledge | 30 | 13 | 0.4333 | 26 | 0 | 0 | 0 | 0 | 4 | 0.4333 |  |  | 13 | 12.4231 | 12.0385 | 133546.1154 | 3620.3462 | 137166.4615 | 0 | 0 | 0 | 0 | Submit action:26; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):3; Error: 'Id':1 |
| conversion_rate_comprehension | 18 | 0 | 0.0000 | 11 | 0 | 0 | 7 | 4 | 0 | 0.0000 |  |  | 0 | 21.7778 | 11.6111 | 702502.1111 | 13052.1667 | 715554.2778 | 0 | 0 | 0 | 0 | Submit action:11; Invalid action:7 |
| internal_operation_data | 30 | 6 | 0.2000 | 16 | 1 | 0 | 8 | 6 | 5 | 0.2000 |  |  | 6 | 18.7200 | 12.2000 | 456390.1600 | 9822.3600 | 466212.5200 | 0 | 0 | 0 | 0 | Submit action:16; Invalid action:8; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):3; Error: litellm.APIError: APIError: OpenAIException - Connection error.:2 |
| lead_qualification | 100 | 28 | 0.2800 | 94 | 2 | 0 | 0 | 0 | 4 | 0.2800 |  |  | 28 |  |  | 141475.3750 | 4039.3958 | 145514.7708 | 0 | 0 | 0 | 0 | Submit action:94; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):3; Max turns reached:2; Error: 'Name':1 |
| private_customer_information | 80 | 28 | 0.3500 | 71 | 0 | 0 | 6 | 1 | 3 | 0.3500 |  |  | 28 | 15.7662 | 13.2468 | 190899.0909 | 5598.6623 | 196497.7532 | 0 | 0 | 0 | 0 | Submit action:71; Invalid action:6; Error: 'Company':1; Error: 'AccountId':1 |
| quote_approval | 100 | 10 | 0.1000 | 89 | 0 | 0 | 0 | 0 | 11 | 0.1000 |  |  | 10 |  |  | 168844.3034 | 4124.3933 | 172968.6966 | 0 | 0 | 0 | 0 | Submit action:89; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):10; Error: list index out of range:1 |

## Top API/Run Errors

- 21: Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195)
- 4: Error: 'Name'
- 2: Error: 'Subject'
- 2: Error: litellm.APIError: APIError: OpenAIException - Connection error.
- 1: Error: 'Title'
- 1: Error: 'Description'
- 1: Error: 'OwnerId'
- 1: Error: 'Id'
- 1: Error: 'Company'
- 1: Error: 'AccountId'
