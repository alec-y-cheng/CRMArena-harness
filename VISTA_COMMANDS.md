## Directory
cd /work/11669/aleccheng/vista/CRMArena

## Export OPEN_APIKey to VLLM
export OPENAI_API_KEY=dummy
export OPENAI_API_BASE=http://127.0.0.1:8001/v1
export OPENAI_BASE_URL=http://127.0.0.1:8001/v1

## Run Tasks
python -u run_tasks.py \
  --model openai/Qwen3.5-35B-A3B \
  --task_category all \
  --agent_eval_mode aided \
  --log_dir results/original/react_qwen35 \
  --agent_strategy react \
  --llm_provider openai \
  --reuse_results \
  --privacy_aware_prompt false \
  --org_type original