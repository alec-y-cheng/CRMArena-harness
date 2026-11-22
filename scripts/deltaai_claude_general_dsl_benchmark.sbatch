#!/usr/bin/env bash
#SBATCH --job-name=claude-general-dsl
#SBATCH --output=/work/hdd/bgtb/acheng11/CRMArena/logs/claude-bench-results/slurm/%x_%j.out
#SBATCH --error=/work/hdd/bgtb/acheng11/CRMArena/logs/claude-bench-results/slurm/%x_%j.err
#SBATCH --time=07:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gpus-per-node=1
##SBATCH --gpu-bind=verbose,closest
#SBATCH --account=bgtb-dtai-gh

set -euo pipefail

# Usage:
#   sbatch scripts/deltaai_claude_general_dsl_benchmark.sbatch
#       Smoke test: 2 examples per task category.
#
#   sbatch scripts/deltaai_claude_general_dsl_benchmark.sbatch smoke my_smoke_tag
#       Smoke test with an explicit tag.
#
#   sbatch scripts/deltaai_claude_general_dsl_benchmark.sbatch full my_full_tag
#       Full benchmark with an explicit tag.
#
# Env overrides:
#   BENCH_MODE=smoke|full
#   RUN_TAG=<tag>
#   MAX_TASKS_PER_CATEGORY=<n>    # 0 means all examples.
#   AGENT_STRATEGY=general_dsl|react
#   CLAUDE_CLI_MODEL=default      # default means do not pass --model.
#   AGENT_REASONING_MODE=default  # default means do not pass --effort.

REPO_DIR="${REPO_DIR:-/work/hdd/bgtb/acheng11/CRMArena}"
MODEL_CONFIG_FILE="${MODEL_CONFIG_FILE:-/work/hdd/bgtb/acheng11/.model-configs.txt}"

ARG_MODE="${1:-}"
ARG_TAG="${2:-}"
if [[ -n "$ARG_MODE" && "$ARG_MODE" != "smoke" && "$ARG_MODE" != "full" ]]; then
  ARG_TAG="$ARG_MODE"
  ARG_MODE=""
fi

BENCH_MODE="${BENCH_MODE:-${ARG_MODE:-smoke}}"
if [[ "$BENCH_MODE" != "smoke" && "$BENCH_MODE" != "full" ]]; then
  echo "ERROR: BENCH_MODE must be smoke or full, got: $BENCH_MODE" >&2
  exit 2
fi

if [[ "$BENCH_MODE" == "full" ]]; then
  DEFAULT_MAX_TASKS=0
else
  DEFAULT_MAX_TASKS=2
fi
MAX_TASKS_PER_CATEGORY="${MAX_TASKS_PER_CATEGORY:-$DEFAULT_MAX_TASKS}"

BENCH_STRATEGY="${AGENT_STRATEGY:-general_dsl}"
if [[ "$BENCH_STRATEGY" != "general_dsl" && "$BENCH_STRATEGY" != "react" ]]; then
  echo "ERROR: AGENT_STRATEGY must be general_dsl or react, got: $BENCH_STRATEGY" >&2
  exit 2
fi

if [[ -n "${RUN_TAG:-}" ]]; then
  BENCH_TAG="$RUN_TAG"
elif [[ -n "$ARG_TAG" ]]; then
  BENCH_TAG="$ARG_TAG"
else
  BENCH_TAG="claude_${BENCH_STRATEGY}_${BENCH_MODE}_${MAX_TASKS_PER_CATEGORY}each_$(date +%Y%m%d_%H%M)"
fi

RESULT_ROOT="${RESULT_ROOT:-$REPO_DIR/results/claude-bench-results/$BENCH_TAG}"
LOG_ROOT="${LOG_ROOT:-$REPO_DIR/logs/claude-bench-results/$BENCH_TAG}"
SLURM_LOG_ROOT="$REPO_DIR/logs/claude-bench-results/slurm"
mkdir -p "$RESULT_ROOT" "$LOG_ROOT" "$SLURM_LOG_ROOT"

cd "$REPO_DIR"

module purge >/dev/null 2>&1 || true
module load gcc-native
module load cudatoolkit/25.5_12.9
module load python/miniforge3_pytorch/2.10.0

source "${CRMARENA_VENV:-$REPO_DIR/.venv-crm-modern}/bin/activate"

if [[ -f "$MODEL_CONFIG_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$MODEL_CONFIG_FILE"
  set +a
fi

export MODEL_CONFIG_FILE=/dev/null
export CLAUDE_CONFIG_DIR="${CLAUDE_CONFIG_DIR:-/work/hdd/bgtb/acheng11/.claude-bench}"
export CLAUDE_CLI_MODEL="${CLAUDE_CLI_MODEL:-default}"
export AGENT_REASONING_MODE="${AGENT_REASONING_MODE:-default}"
export USE_EXTERNAL_ROUTER_DSL="${USE_EXTERNAL_ROUTER_DSL:-true}"
export USE_INTERNAL_ROUTER_DSL="${USE_INTERNAL_ROUTER_DSL:-true}"
export CLI_MODEL_TIMEOUT_SECONDS="${CLI_MODEL_TIMEOUT_SECONDS:-900}"
export HF_HOME="${HF_HOME:-/work/hdd/bgtb/acheng11/qwen_agent_ft/cache/huggingface}"
export HF_DATASETS_CACHE="${HF_DATASETS_CACHE:-$HF_HOME/datasets}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"
export VECLIB_MAXIMUM_THREADS="${VECLIB_MAXIMUM_THREADS:-1}"
export TOKENIZERS_PARALLELISM="${TOKENIZERS_PARALLELISM:-false}"

JUDGE_PROVIDER="${JUDGE_PROVIDER:-openrouter}"
USER_PROVIDER="${USER_PROVIDER:-openrouter}"
JUDGE_MODEL="${JUDGE_MODEL:-openai/gpt-4o-2024-11-20}"
USER_MODEL="${USER_MODEL:-openai/gpt-4o-2024-11-20}"
JUDGE_BASE_URL="${JUDGE_BASE_URL:-}"
USER_BASE_URL="${USER_BASE_URL:-}"
JUDGE_API_KEY="${JUDGE_API_KEY:-${OPENROUTER_API_KEY:-}}"
USER_API_KEY="${USER_API_KEY:-${OPENROUTER_API_KEY:-$JUDGE_API_KEY}}"

if [[ "$JUDGE_PROVIDER" == "openrouter" && -z "$JUDGE_API_KEY" ]]; then
  echo "ERROR: OPENROUTER_API_KEY or JUDGE_API_KEY is required for the default GPT-4o user/judge." >&2
  exit 2
fi

echo "Claude CRMArena benchmark"
echo "  strategy=$BENCH_STRATEGY"
echo "  mode=$BENCH_MODE"
echo "  tag=$BENCH_TAG"
echo "  max_tasks_per_category=$MAX_TASKS_PER_CATEGORY"
echo "  result_root=$RESULT_ROOT"
echo "  log_root=$LOG_ROOT"
echo "  claude_config_dir=$CLAUDE_CONFIG_DIR"
echo "  claude_cli_model=$CLAUDE_CLI_MODEL"
echo "  agent_reasoning_mode=$AGENT_REASONING_MODE"
echo "  use_external_router_dsl=$USE_EXTERNAL_ROUTER_DSL"
echo "  use_internal_router_dsl=$USE_INTERNAL_ROUTER_DSL"
echo "  judge=$JUDGE_PROVIDER/$JUDGE_MODEL"
echo "  user=$USER_PROVIDER/$USER_MODEL"

run_task() {
  local org_type="$1"
  local task_category="$2"
  local task_label="${org_type}_${task_category}"
  local task_result_dir="$RESULT_ROOT/$task_label"
  local task_log_file="$LOG_ROOT/run_${task_label}_default.log"
  mkdir -p "$task_result_dir"

  echo "============================================================"
  echo "Running $task_label"
  echo "  result_dir=$task_result_dir"
  echo "  log_file=$task_log_file"
  echo "============================================================"

  python -u run_tasks.py \
    --model claude_cli \
    --task_category "$task_category" \
    --log_dir "$task_result_dir" \
    --agent_strategy "$BENCH_STRATEGY" \
    --interactive \
    --llm_provider claude_cli \
    --judge_model "$JUDGE_MODEL" \
    --judge_provider "$JUDGE_PROVIDER" \
    --judge_base_url "$JUDGE_BASE_URL" \
    --judge_api_key "$JUDGE_API_KEY" \
    --user_model "$USER_MODEL" \
    --user_provider "$USER_PROVIDER" \
    --user_base_url "$USER_BASE_URL" \
    --user_api_key "$USER_API_KEY" \
    --max_turns "${MAX_TURNS:-20}" \
    --max_user_turns "${MAX_USER_TURNS:-10}" \
    --max_tasks_per_category "$MAX_TASKS_PER_CATEGORY" \
    --agent_max_tokens "${AGENT_MAX_TOKENS:-2500}" \
    --max_dsl_retries "${MAX_DSL_RETRIES:-3}" \
    --routing_mode none \
    --scaffold_mode none \
    --reuse_results \
    --privacy_aware_prompt "${PRIVACY_AWARE_PROMPT:-true}" \
    --org_type "$org_type" > "$task_log_file" 2>&1
}

run_task b2b internal_operation_data
run_task b2b private_customer_information
run_task original named_entity_disambiguation
run_task original knowledge_qa
run_task b2b confidential_company_knowledge
run_task b2b wrong_stage_rectification
run_task b2b policy_violation_identification

echo "Done."
echo "Results: $RESULT_ROOT"
echo "Logs: $LOG_ROOT"
