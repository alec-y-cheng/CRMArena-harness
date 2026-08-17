#!/usr/bin/env bash
#SBATCH --job-name=claude-ewm-smoke
#SBATCH --output=/work/hdd/bgtb/acheng11/CRMArena/logs/ewm-smoke/slurm/%x_%j.out
#SBATCH --error=/work/hdd/bgtb/acheng11/CRMArena/logs/ewm-smoke/slurm/%x_%j.err
#SBATCH --time=04:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gpus-per-node=1
#SBATCH --account=bhit-dtai-gh

set -euo pipefail

# Claude generic EWM smoke benchmark.
#
# Defaults are intentionally small:
#   - 2 examples per task family
#   - 4 total agent turns
#   - 4 simulated-user turns
#   - 8 EWM workflow steps per agent turn
#
# Usage:
#   sbatch scripts/deltaai_claude_ewm_smoke.sbatch
#
# Common overrides:
#   sbatch --account=bgtb-dtai-gh scripts/deltaai_claude_ewm_smoke.sbatch
#   sbatch --export=ALL,MAX_TASKS_PER_CATEGORY=10 scripts/deltaai_claude_ewm_smoke.sbatch
#   sbatch --export=ALL,CLAUDE_CLI_MODEL=claude-opus-5 scripts/deltaai_claude_ewm_smoke.sbatch

REPO_DIR="${REPO_DIR:-/work/hdd/bgtb/acheng11/CRMArena}"
MODEL_CONFIG_FILE="${MODEL_CONFIG_FILE:-/work/hdd/bgtb/acheng11/.model-configs.txt}"

RUN_TAG="${RUN_TAG:-claude_ewm_smoke_${MAX_TASKS_PER_CATEGORY:-2}each_4turn_$(date +%Y%m%d_%H%M)}"
LOG_TAG="${LOG_TAG:-$RUN_TAG}"

mkdir -p "$REPO_DIR/logs/ewm-smoke/slurm" "$REPO_DIR/logs/run_wrappers"
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
export CLI_MODEL_TIMEOUT_SECONDS="${CLI_MODEL_TIMEOUT_SECONDS:-900}"
export HF_HOME="${HF_HOME:-/work/hdd/bgtb/acheng11/qwen_agent_ft/cache/huggingface}"
export HF_DATASETS_CACHE="${HF_DATASETS_CACHE:-$HF_HOME/datasets}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"
export VECLIB_MAXIMUM_THREADS="${VECLIB_MAXIMUM_THREADS:-1}"
export TOKENIZERS_PARALLELISM="${TOKENIZERS_PARALLELISM:-false}"

if [[ -z "${OPENROUTER_API_KEY:-}" && -z "${JUDGE_API_KEY:-}" ]]; then
  echo "ERROR: OPENROUTER_API_KEY or JUDGE_API_KEY is required for the default user/judge." >&2
  exit 2
fi

COMMON_ENV=(
  MODEL_CONFIG_FILE=/dev/null
  AGENT_MODEL=claude_cli
  AGENT_PROVIDER=claude_cli
  AGENT_STRATEGY=ewm
  CLAUDE_CONFIG_DIR="$CLAUDE_CONFIG_DIR"
  CLAUDE_CLI_MODEL="$CLAUDE_CLI_MODEL"
  AGENT_REASONING_MODE="$AGENT_REASONING_MODE"
  JUDGE_PROVIDER="${JUDGE_PROVIDER:-openrouter}"
  USER_PROVIDER="${USER_PROVIDER:-openrouter}"
  JUDGE_MODEL="${JUDGE_MODEL:-openai/gpt-4o-2024-11-20}"
  USER_MODEL="${USER_MODEL:-openai/gpt-4o-2024-11-20}"
  JUDGE_API_KEY="${JUDGE_API_KEY:-${OPENROUTER_API_KEY:-}}"
  USER_API_KEY="${USER_API_KEY:-${OPENROUTER_API_KEY:-${JUDGE_API_KEY:-}}}"
  MAX_TASKS_PER_CATEGORY="${MAX_TASKS_PER_CATEGORY:-2}"
  INTERACTIVE=true
  PRIVACY_AWARE_PROMPT=true
  MAX_TURNS="${MAX_TURNS:-4}"
  MAX_USER_TURNS="${MAX_USER_TURNS:-4}"
  EWM_MAX_STEPS="${EWM_MAX_STEPS:-8}"
  EWM_FRAME_MAX_TOKENS="${EWM_FRAME_MAX_TOKENS:-2500}"
  EWM_DECISION_MAX_TOKENS="${EWM_DECISION_MAX_TOKENS:-4000}"
  EWM_CLAIM_MAX_TOKENS="${EWM_CLAIM_MAX_TOKENS:-2500}"
  EWM_COMPLETION_VERIFIER_MAX_TOKENS="${EWM_COMPLETION_VERIFIER_MAX_TOKENS:-2000}"
  AGENT_MAX_TOKENS="${AGENT_MAX_TOKENS:-4000}"
  USE_SYNTACTIC_VERIFIER=false
  USE_WORKING_MEMORY=false
  USE_QUOTE_CLIPBOARD=false
  USE_LEAD_CLIPBOARD=false
  ROUTING_MODE=none
  SCAFFOLD_MODE=none
  SKIP_HEALTH_CHECKS=true
  CRMARENA_VENV="${CRMARENA_VENV:-$REPO_DIR/.venv-crm-modern}"
  PYTHON_BIN="$(command -v python)"
  RUN_TAG="$RUN_TAG"
  LOG_TAG="$LOG_TAG"
)

echo "Claude EWM smoke"
echo "  run_tag=$RUN_TAG"
echo "  account=${SLURM_JOB_ACCOUNT:-unknown}"
echo "  claude_config_dir=$CLAUDE_CONFIG_DIR"
echo "  claude_model=$CLAUDE_CLI_MODEL"
echo "  max_tasks_per_category=${MAX_TASKS_PER_CATEGORY:-2}"
echo "  max_turns=${MAX_TURNS:-4}"
echo "  max_user_turns=${MAX_USER_TURNS:-4}"
echo "  ewm_max_steps=${EWM_MAX_STEPS:-8}"
echo "  ewm_frame_max_tokens=${EWM_FRAME_MAX_TOKENS:-2500}"
echo "  ewm_decision_max_tokens=${EWM_DECISION_MAX_TOKENS:-4000}"
echo "  ewm_claim_max_tokens=${EWM_CLAIM_MAX_TOKENS:-2500}"
echo "  ewm_completion_verifier_max_tokens=${EWM_COMPLETION_VERIFIER_MAX_TOKENS:-2000}"
echo "  agent_max_tokens=${AGENT_MAX_TOKENS:-4000}"
echo "  judge=${JUDGE_PROVIDER:-openrouter}/${JUDGE_MODEL:-openai/gpt-4o-2024-11-20}"
echo "  user=${USER_PROVIDER:-openrouter}/${USER_MODEL:-openai/gpt-4o-2024-11-20}"

run_task() {
  local org_type="$1"
  local task_category="$2"

  echo "============================================================"
  echo "Running org_type=$org_type task_category=$task_category"
  echo "============================================================"

  env "${COMMON_ENV[@]}" \
    EWM_ORG_TYPE="$org_type" \
    ORG_TYPES_CSV="$org_type" \
    TASKS_CSV="$task_category" \
    ./run_tasks_crmarena_pro.sh
}

# Same selected EWM task order as the Codex Slurm smoke job.
run_task original knowledge_qa
run_task b2b policy_violation_identification
run_task b2b confidential_company_knowledge
run_task b2b wrong_stage_rectification
run_task original named_entity_disambiguation
run_task b2b internal_operation_data
run_task b2b private_customer_information

echo "Done."
echo "Original-org results: $REPO_DIR/results/original_multi-turn/ewm_claude_cli_${RUN_TAG}_noverifier_nowm"
echo "B2B results: $REPO_DIR/results/b2b_multi-turn/ewm_claude_cli_${RUN_TAG}_noverifier_nowm"
