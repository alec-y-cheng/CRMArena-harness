# CRMArena Result Summary

Source: `results/b2b_multi-turn/react_openai_Qwen3.5-35B-A3B_base_full_unmodified_q35_859621_llama_859619_noverifier_nowm`

## Overall

- Tasks: 398
- Successes: 71
- Success rate: 0.1784
- API errors: 23
- SOQL/SOSL query-error endings: 1
- Invalid-action endings: 14
- Verifier rejection events: 0
- Verifier unknown/allowed events: 0

## By Task

| task_type | n | successes | success_rate | submitted | max_turns | query_errors | invalid_actions | empty_content | api_errors | avg_reward | avg_em | avg_f1 | nonzero_rewards | avg_model_calls | avg_env_steps | avg_prompt_tokens | avg_completion_tokens | avg_total_tokens | verifier_failure_tasks | verifier_failure_events | verifier_unknown_tasks | verifier_unknown_events | top_end_reasons |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| case_routing | 100 | 15 | 0.1500 | 83 | 3 | 0 | 2 | 2 | 12 | 0.1500 |  |  | 15 | 16.9659 | 15.8068 | 213496.8523 | 5345.3295 | 218842.1818 | 0 | 0 | 0 | 0 | Submit action:83; Error: 'Subject':5; Max turns reached:3; Invalid action:2 |
| internal_operation_data | 18 | 4 | 0.2222 | 12 | 0 | 0 | 5 | 4 | 1 | 0.2222 |  |  | 4 | 19.1176 | 12.7059 | 372051.0000 | 9670.1765 | 381721.1765 | 0 | 0 | 0 | 0 | Submit action:12; Invalid action:5; Error: 'Company':1 |
| lead_qualification | 100 | 25 | 0.2500 | 93 | 0 | 1 | 3 | 1 | 3 | 0.2500 |  |  | 25 | 12.5773 | 11.2268 | 168884.5670 | 4914.7113 | 173799.2784 | 0 | 0 | 0 | 0 | Submit action:93; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):3; Invalid action:3; SOQL/SOSL query error:1 |
| private_customer_information | 80 | 17 | 0.2125 | 76 | 0 | 0 | 2 | 1 | 2 | 0.2125 |  |  | 17 | 13.7692 | 12.0385 | 117047.3205 | 4564.5641 | 121611.8846 | 0 | 0 | 0 | 0 | Submit action:76; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):2; Invalid action:2 |
| quote_approval | 100 | 10 | 0.1000 | 93 | 0 | 0 | 2 | 0 | 5 | 0.1000 |  |  | 10 | 10.9474 | 9.5895 | 200641.9474 | 4425.7053 | 205067.6526 | 0 | 0 | 0 | 0 | Submit action:93; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):5; Invalid action:2 |

## Top API/Run Errors

- 11: Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195)
- 5: Error: 'Subject'
- 2: Error: 'Name'
- 2: Error: 'Description'
- 1: Error: 'Title'
- 1: Error: list index out of range
- 1: Error: 'Company'
