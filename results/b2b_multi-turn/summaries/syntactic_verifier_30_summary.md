# CRMArena Result Summary

Source: `CRMArena/results/b2b_multi-turn/react_openai_Qwen3.5-35B-A3B_ablation30_q35_858267_llama_858420_syntactic_verifier_only_syntactic_verifier_nowm/results_openai`

## Overall

- Tasks: 180
- Successes: 43
- Success rate: 0.2389
- API errors: 20
- SOQL/SOSL query-error endings: 0
- Invalid-action endings: 9
- Verifier rejection events: 242

## By Task

| task_type | n | successes | success_rate | submitted | max_turns | query_errors | invalid_actions | empty_content | api_errors | avg_reward | avg_em | avg_f1 | nonzero_rewards | avg_model_calls | avg_env_steps | avg_prompt_tokens | avg_completion_tokens | avg_total_tokens | verifier_failure_tasks | verifier_failure_events | top_end_reasons |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| case_routing | 30 | 1 | 0.0333 | 25 | 0 | 0 | 1 | 1 | 4 | 0.0333 |  |  | 1 | 16.8077 | 13.1154 | 172475.3462 | 5364.8846 | 177840.2308 | 25 | 70 | Submit action:25; Error: 'Subject':2; Error: 'Title':1; Error: 'Description':1 |
| confidential_company_knowledge | 30 | 12 | 0.4000 | 24 | 0 | 0 | 0 | 0 | 6 | 0.4000 |  |  | 12 | 12.2500 | 10.5000 | 145811.5000 | 3992.0417 | 149803.5417 | 11 | 17 | Submit action:24; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):3; Error: 'Name':1; Error: 'LastName':1 |
| internal_operation_data | 30 | 10 | 0.3333 | 20 | 1 | 0 | 6 | 5 | 3 | 0.3333 |  |  | 10 | 19.7037 | 11.1852 | 518505.4074 | 9756.1481 | 528261.5556 | 24 | 78 | Submit action:20; Invalid action:6; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):2; Error: 'Subject':1 |
| lead_qualification | 30 | 9 | 0.3000 | 27 | 0 | 0 | 1 | 0 | 2 | 0.3000 |  |  | 9 | 11.6786 | 9.3571 | 230875.1786 | 4726.5714 | 235601.7500 | 18 | 30 | Submit action:27; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):1; Error: 'Name':1; Invalid action:1 |
| private_customer_information | 30 | 8 | 0.2667 | 24 | 0 | 0 | 1 | 0 | 5 | 0.2667 |  |  | 8 | 13.4800 | 10.7200 | 122284.5200 | 4530.4800 | 126815.0000 | 12 | 30 | Submit action:24; Error: 'AccountId':2; Error: 'Name':1; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):1 |
| quote_approval | 30 | 3 | 0.1000 | 30 | 0 | 0 | 0 | 0 | 0 | 0.1000 |  |  | 3 | 10.9000 | 9.3000 | 241919.6667 | 4244.5333 | 246164.2000 | 15 | 17 | Submit action:30 |

## Top API/Run Errors

- 7: Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195)
- 4: Error: 'Subject'
- 3: Error: 'Name'
- 2: Error: 'AccountId'
- 1: Error: 'Title'
- 1: Error: 'Description'
- 1: Error: 'LastName'
- 1: Error: 'Company'
