# CRMArena Result Summary

Source: `results/b2b_multi-turn/react_openai_Qwen3.5-35B-A3B_ablation30_q35_859621_llama_859619_routing_only_noverifier_nowm`

## Overall

- Tasks: 180
- Successes: 56
- Success rate: 0.3111
- API errors: 16
- SOQL/SOSL query-error endings: 0
- Invalid-action endings: 3
- Verifier rejection events: 0
- Verifier unknown/allowed events: 0

## By Task

| task_type | n | successes | success_rate | submitted | max_turns | query_errors | invalid_actions | empty_content | api_errors | avg_reward | avg_em | avg_f1 | nonzero_rewards | avg_model_calls | avg_env_steps | avg_prompt_tokens | avg_completion_tokens | avg_total_tokens | verifier_failure_tasks | verifier_failure_events | verifier_unknown_tasks | verifier_unknown_events | top_end_reasons |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| case_routing | 30 | 4 | 0.1333 | 24 | 0 | 0 | 0 | 0 | 6 | 0.1333 |  |  | 4 | 20.7500 | 18.9583 | 607848.8333 | 6174.3750 | 614023.2083 | 0 | 0 | 0 | 0 | Submit action:24; Error: 'Subject':3; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):3 |
| confidential_company_knowledge | 30 | 18 | 0.6000 | 29 | 0 | 0 | 0 | 0 | 1 | 0.6000 |  |  | 18 | 10.4828 | 10.1034 | 92113.8276 | 3322.6207 | 95436.4483 | 0 | 0 | 0 | 0 | Submit action:29; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):1 |
| internal_operation_data | 30 | 11 | 0.3667 | 21 | 2 | 0 | 3 | 2 | 4 | 0.3667 |  |  | 11 | 17.7308 | 13.0769 | 501243.5000 | 8471.0000 | 509714.5000 | 0 | 0 | 0 | 0 | Submit action:21; Invalid action:3; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):2; Max turns reached:2 |
| lead_qualification | 30 | 10 | 0.3333 | 27 | 1 | 0 | 0 | 0 | 1 | 0.3333 |  |  | 10 | 11.2759 | 10.7931 | 308635.7586 | 4062.3103 | 312698.0690 | 0 | 0 | 0 | 0 | Submit action:27; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):1; Respond action:1; Max turns reached:1 |
| private_customer_information | 30 | 11 | 0.3667 | 29 | 0 | 0 | 0 | 0 | 1 | 0.3667 |  |  | 11 | 12.6207 | 12.1379 | 97750.9655 | 3782.4828 | 101533.4483 | 0 | 0 | 0 | 0 | Submit action:29; Error: 'AccountId':1 |
| quote_approval | 30 | 2 | 0.0667 | 27 | 0 | 0 | 0 | 0 | 3 | 0.0667 |  |  | 2 | 9.5556 | 8.7407 | 164600.9630 | 3326.0000 | 167926.9630 | 0 | 0 | 0 | 0 | Submit action:27; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):3 |

## Top API/Run Errors

- 10: Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195)
- 3: Error: 'Subject'
- 1: Error: 'TextBody'
- 1: Error: 'Name'
- 1: Error: 'AccountId'
