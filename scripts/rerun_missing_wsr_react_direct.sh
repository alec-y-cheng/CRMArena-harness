#!/usr/bin/env bash
set -euo pipefail

cd /work/hdd/bgtb/acheng11/CRMArena

usage() {
  cat <<'EOF'
Rerun specific task IDs into an existing CRMArena result folder while writing
fresh logs. This is intended for replacing API/CLI stub rows after a provider
quota or transient failure.

Presets:
  PRESET=kqa_react_api_stubs      Rerun Claude ReAct KQA task 80.
  PRESET=pvi_react_api_stubs      Rerun Claude ReAct PVI tasks 1427,1428,1429.
  PRESET=pvi_dsl_api_stubs        Rerun Claude General DSL PVI tasks 1399,1403.

Custom required variables:
  TASKS_CSV, TASK_IDS_CSV, RUN_TAG

Useful optional variables:
  ORG_TYPES_CSV=b2b|original
  AGENT_STRATEGY=react|general_dsl
  AGENT_MODEL=claude_cli|default
  CLAUDE_CLI_MODEL=default|claude-opus-5
  LOG_TAG=<fresh-log-tag>

Examples:
  PRESET=pvi_react_api_stubs scripts/rerun_missing_wsr_react_direct.sh
  PRESET=pvi_dsl_api_stubs LOG_TAG=my_fresh_logs scripts/rerun_missing_wsr_react_direct.sh
  TASKS_CSV=wrong_stage_rectification TASK_IDS_CSV=1356,1357 RUN_TAG=old_result_tag scripts/rerun_missing_wsr_react_direct.sh
EOF
}

PRESET="${PRESET:-}"

if [[ "${1:-}" == "help" || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

case "$PRESET" in
  "")
    ;;
  kqa_react_api_stubs)
    export ORG_TYPES_CSV="original"
    export AGENT_STRATEGY="react"
    export AGENT_MODEL="default"
    export AGENT_PROVIDER="claude_cli"
    export CLAUDE_CLI_MODEL="claude-opus-5"
    export TASKS_CSV="knowledge_qa"
    export TASK_IDS_CSV="80"
    export RUN_TAG="claude_cli_opus_openrouter_gpt4o_external_conf_full_20260802_2346_regular_external"
    export PRIVACY_AWARE_PROMPT="true"
    ;;
  pvi_react_api_stubs)
    export ORG_TYPES_CSV="b2b"
    export AGENT_STRATEGY="react"
    export AGENT_MODEL="claude_cli"
    export AGENT_PROVIDER="claude_cli"
    export CLAUDE_CLI_MODEL="claude-opus-5"
    export TASKS_CSV="policy_violation_identification"
    export TASK_IDS_CSV="1427,1428,1429"
    export RUN_TAG="claude_cli_opus_react_pvi_full_20260809_1550"
    export PRIVACY_AWARE_PROMPT="false"
    ;;
  pvi_dsl_api_stubs)
    export ORG_TYPES_CSV="b2b"
    export AGENT_STRATEGY="general_dsl"
    export AGENT_MODEL="claude_cli"
    export AGENT_PROVIDER="claude_cli"
    export CLAUDE_CLI_MODEL="default"
    export TASKS_CSV="policy_violation_identification"
    export TASK_IDS_CSV="1399,1403"
    export RUN_TAG="claude_internal_full_20260805_1654"
    export PRIVACY_AWARE_PROMPT="false"
    ;;
  *)
    echo "Unknown PRESET: $PRESET" >&2
    usage >&2
    exit 2
    ;;
esac

if [[ -z "${TASKS_CSV:-}" || -z "${TASK_IDS_CSV:-}" || -z "${RUN_TAG:-}" ]]; then
  echo "ERROR: set PRESET, or set TASKS_CSV, TASK_IDS_CSV, and RUN_TAG." >&2
  usage >&2
  exit 2
fi

set -a
source /work/hdd/bgtb/acheng11/.model-configs.txt
set +a

export CLAUDE_CONFIG_DIR="${CLAUDE_CONFIG_DIR:-/work/hdd/bgtb/acheng11/.claude-bench}"
export CLAUDE_CLI_MODEL="${CLAUDE_CLI_MODEL:-default}"

export MODEL_CONFIG_FILE=/dev/null
export AGENT_MODEL="${AGENT_MODEL:-claude_cli}"
export AGENT_PROVIDER="${AGENT_PROVIDER:-claude_cli}"
export AGENT_REASONING_MODE="${AGENT_REASONING_MODE:-default}"
export AGENT_STRATEGY="${AGENT_STRATEGY:-react}"
export RERUN_TASK_IDS=true
export ORG_TYPES_CSV="${ORG_TYPES_CSV:-b2b}"
export JUDGE_PROVIDER="${JUDGE_PROVIDER:-openrouter}"
export USER_PROVIDER="${USER_PROVIDER:-openrouter}"
export JUDGE_MODEL="${JUDGE_MODEL:-openai/gpt-4o-2024-11-20}"
export USER_MODEL="${USER_MODEL:-openai/gpt-4o-2024-11-20}"
export JUDGE_API_KEY="${OPENROUTER_API_KEY:?OPENROUTER_API_KEY is required}"
export USER_API_KEY="${OPENROUTER_API_KEY:?OPENROUTER_API_KEY is required}"
export MAX_TASKS_PER_CATEGORY=0
export INTERACTIVE="${INTERACTIVE:-true}"
export MAX_TURNS="${MAX_TURNS:-20}"
export MAX_USER_TURNS="${MAX_USER_TURNS:-10}"
export AGENT_MAX_TOKENS="${AGENT_MAX_TOKENS:-2500}"
export USE_SYNTACTIC_VERIFIER="${USE_SYNTACTIC_VERIFIER:-false}"
export USE_WORKING_MEMORY="${USE_WORKING_MEMORY:-false}"
export USE_QUOTE_CLIPBOARD="${USE_QUOTE_CLIPBOARD:-false}"
export USE_LEAD_CLIPBOARD="${USE_LEAD_CLIPBOARD:-false}"
export ROUTING_MODE="${ROUTING_MODE:-none}"
export SCAFFOLD_MODE="${SCAFFOLD_MODE:-none}"
export SKIP_HEALTH_CHECKS="${SKIP_HEALTH_CHECKS:-true}"
export CRMARENA_VENV="${CRMARENA_VENV:-/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern}"
export PYTHON_BIN="${PYTHON_BIN:-/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern/bin/python}"
export LOG_TAG="${LOG_TAG:-${RUN_TAG}_rerun_${TASKS_CSV}_${TASK_IDS_CSV//,/_}_$(date +%Y%m%d_%H%M)}"

echo "Rerunning API-stub rows"
echo "  preset=${PRESET:-custom}"
echo "  org=${ORG_TYPES_CSV}"
echo "  task=${TASKS_CSV}"
echo "  ids=${TASK_IDS_CSV}"
echo "  strategy=${AGENT_STRATEGY}"
echo "  agent_model=${AGENT_MODEL}"
echo "  claude_cli_model=${CLAUDE_CLI_MODEL}"
echo "  result_run_tag=${RUN_TAG}"
echo "  fresh_log_tag=${LOG_TAG}"

./run_tasks_crmarena_pro.sh
