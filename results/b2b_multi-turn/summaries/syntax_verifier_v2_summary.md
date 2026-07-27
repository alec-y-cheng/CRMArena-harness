# CRMArena Result Summary

Source: `results/b2b_multi-turn/react_openai_Qwen3.5-35B-A3B_syntax_verifier_v2_syntactic_verifier_nowm`

## Overall

- Tasks: 180
- Successes: 48
- Success rate: 0.2667
- API errors: 15
- SOQL/SOSL query-error endings: 0
- Invalid-action endings: 10
- Verifier rejection events: 201
- Verifier unknown/allowed events: 8

## By Task

| task_type | n | successes | success_rate | submitted | max_turns | query_errors | invalid_actions | empty_content | api_errors | avg_reward | avg_em | avg_f1 | nonzero_rewards | avg_model_calls | avg_env_steps | avg_prompt_tokens | avg_completion_tokens | avg_total_tokens | verifier_failure_tasks | verifier_failure_events | verifier_unknown_tasks | verifier_unknown_events | top_end_reasons |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| case_routing | 30 | 3 | 0.1000 | 24 | 0 | 0 | 2 | 1 | 4 | 0.1000 |  |  | 3 | 17.3462 | 13.0385 | 207501.7692 | 6350.1538 | 213851.9231 | 21 | 59 | 0 | 0 | Submit action:24; Invalid action:2; Error: 'Subject':1; Error: 'OwnerId':1 |
| confidential_company_knowledge | 30 | 14 | 0.4667 | 28 | 0 | 0 | 0 | 0 | 2 | 0.4667 |  |  | 14 | 12.0000 | 10.0714 | 173991.5714 | 4291.4286 | 178283.0000 | 14 | 24 | 0 | 0 | Submit action:28; Error: 'Name':1; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):1 |
| internal_operation_data | 30 | 9 | 0.3000 | 17 | 2 | 0 | 6 | 5 | 3 | 0.3000 |  |  | 9 | 19.7778 | 11.6667 | 488208.7778 | 9007.0000 | 497215.7778 | 25 | 75 | 5 | 8 | Submit action:17; Invalid action:6; Max turns reached:2; INVALID_SOQL_GRAMMAR:2 |
| lead_qualification | 30 | 13 | 0.4333 | 29 | 0 | 0 | 0 | 0 | 1 | 0.4333 |  |  | 13 | 9.5517 | 8.4483 | 121437.4828 | 3609.4483 | 125046.9310 | 14 | 23 | 0 | 0 | Submit action:29; Error: 'Body':1 |
| private_customer_information | 30 | 6 | 0.2000 | 25 | 0 | 0 | 2 | 0 | 3 | 0.2000 |  |  | 6 | 11.8148 | 8.9630 | 103979.4815 | 4777.5926 | 108757.0741 | 10 | 13 | 0 | 0 | Submit action:25; Error: 'AccountId':3; Invalid action:2 |
| quote_approval | 30 | 3 | 0.1000 | 28 | 0 | 0 | 0 | 0 | 2 | 0.1000 |  |  | 3 | 9.9286 | 8.8929 | 220630.6786 | 3825.6429 | 224456.3214 | 5 | 7 | 0 | 0 | Submit action:28; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):2 |

## Top API/Run Errors

- 6: Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195)
- 3: Error: 'AccountId'
- 1: Error: 'Subject'
- 1: Error: 'OwnerId'
- 1: Error: 'Title'
- 1: Error: 'Name'
- 1: Error: list index out of range
- 1: Error: 'Body'
