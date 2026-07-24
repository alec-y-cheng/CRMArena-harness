#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from verifiers.action_verifier import ActionVerifier
from verifiers.schema_loader import load_crmarena_schema


EXECUTE_RE = re.compile(r"<execute>(.*?)</execute>", re.DOTALL)
RESPOND_RE = re.compile(r"<respond>(.*?)</respond>", re.DOTALL)

QUERY_ERROR_MARKERS = (
    "SOQL/SOSL query error",
    "INVALID_FIELD",
    "INVALID_TYPE",
    "INVALID_QUERY",
    "INVALID_QUERY_FILTER_OPERATOR",
    "MALFORMED_QUERY",
    "MALFORMED_SEARCH",
    "ERROR at Row",
    "No such column",
    "unexpected token",
    "invalid ID field",
    "field '",
    "can not be filtered",
    "Semi join",
    "Nesting of semi join",
)
SALESFORCE_IDENTIFIER_RE = r"[A-Za-z_][A-Za-z0-9_]*"


def parse_action(content: str) -> dict[str, str] | None:
    execute_match = EXECUTE_RE.search(content or "")
    if execute_match and execute_match.group(1).strip():
        return {"name": "execute", "content": execute_match.group(1).strip()}

    respond_match = RESPOND_RE.search(content or "")
    if respond_match and respond_match.group(1).strip():
        return {"name": "respond", "content": respond_match.group(1).strip()}
    return None


def as_float(value) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def reward_scalar(reward) -> float | None:
    if isinstance(reward, Mapping):
        for key in ("score", "reward", "em", "f1"):
            value = as_float(reward.get(key))
            if value is not None:
                return value
        rouge = reward.get("rouge")
        if isinstance(rouge, Mapping):
            value = as_float(rouge.get("rouge-l"))
            if value is not None:
                return value
    return as_float(reward)


def end_reason(result: Mapping) -> tuple[str, str, str]:
    info = result.get("agent_info") or {}
    reason = info.get("end_reason") or {}
    return (
        str(reason.get("source", "")),
        str(reason.get("message", "")),
        str(reason.get("content", "")),
    )


def is_env_query_error(observation: str, final_end_reason: tuple[str, str, str], is_last_execute: bool) -> bool:
    if observation and any(marker in observation for marker in QUERY_ERROR_MARKERS):
        return True
    return is_last_execute and final_end_reason[1] == "SOQL/SOSL query error"


def short_text(text: str, limit: int = 240) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def is_shared_result_file(path: Path) -> bool:
    return "shared" in path.parts


def iter_result_files(paths: Iterable[Path], include_shared: bool = False) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix == ".json":
            if include_shared or not is_shared_result_file(path):
                files.append(path)
        elif path.is_dir():
            for result_file in sorted(path.rglob("*.json")):
                if include_shared or not is_shared_result_file(result_file):
                    files.append(result_file)
    return sorted(dict.fromkeys(files))


def default_previous_paths() -> list[Path]:
    candidates = [
        REPO_ROOT / "results" / "original",
        REPO_ROOT / "results" / "b2b_multi-turn",
        REPO_ROOT / "archived_results",
    ]
    return [path for path in candidates if path.exists()]


def run_name_from_source(source_file: Path) -> str:
    parts = source_file.parts
    if "results_openai" in parts:
        index = parts.index("results_openai")
        if index > 0:
            return parts[index - 1]
    return source_file.parent.name


def load_result_rows(path: Path) -> list[Mapping]:
    with path.open() as f:
        data = json.load(f)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, Mapping) and "traj" in row]
    if isinstance(data, Mapping):
        rows = data.get("results")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, Mapping) and "traj" in row]
    return []


def schema_from_prompt(system_prompt: str) -> list[dict]:
    schemas: list[dict] = []
    current_object: str | None = None
    current_fields: dict[str, str] = {}
    in_fields = False

    def flush_current() -> None:
        nonlocal current_object, current_fields
        if current_object:
            schemas.append({"object": current_object, "fields": dict(current_fields)})
        current_object = None
        current_fields = {}

    for raw_line in (system_prompt or "").splitlines():
        line = raw_line.rstrip()
        if line.startswith("## The fields available"):
            in_fields = True
            continue
        if not in_fields:
            continue
        if line.startswith("# Domain Details") or line.startswith("## Domain Details"):
            flush_current()
            break

        object_match = re.match(rf"^({SALESFORCE_IDENTIFIER_RE})$", line)
        if object_match:
            flush_current()
            current_object = object_match.group(1)
            continue

        field_match = re.match(rf"^\s*-\s+({SALESFORCE_IDENTIFIER_RE}):\s*(.*)$", line)
        if current_object and field_match:
            current_fields[field_match.group(1)] = field_match.group(2).strip()

    flush_current()
    return schemas


def first_system_prompt(rows: list[Mapping]) -> str:
    for row in rows:
        for message in row.get("traj") or []:
            if message.get("role") == "system":
                return str(message.get("content") or "")
    return ""


def schema_from_assets(schema_name: str) -> list[Mapping]:
    return load_crmarena_schema(schema_name)


def build_verifier(rows: list[Mapping], schema_name: str) -> ActionVerifier:
    if schema_name == "prompt":
        schema = schema_from_prompt(first_system_prompt(rows))
        if not schema:
            raise RuntimeError("Could not parse schema from trajectory system prompt.")
        return ActionVerifier.from_schema(schema)

    if schema_name == "auto":
        schema = schema_from_prompt(first_system_prompt(rows))
        if schema:
            return ActionVerifier.from_schema(schema)
        return ActionVerifier.from_schema(schema_from_assets("b2b"))

    return ActionVerifier.from_schema(schema_from_assets(schema_name))


def classify_step(action: Mapping, verifier_valid: bool, verifier_status: str, env_query_error: bool) -> str:
    if verifier_status == "UNKNOWN":
        if action["name"] == "execute" and env_query_error:
            return "verifier_unknown_env_failure"
        if action["name"] == "execute":
            return "verifier_unknown_execute"
        return "verifier_unknown_respond"

    if action["name"] == "execute":
        if not verifier_valid and env_query_error:
            return "verifier_true_positive"
        if not verifier_valid:
            return "verifier_reject_unconfirmed"
        if env_query_error:
            return "verifier_missed_env_failure"
        return "verifier_pass_execute"

    if not verifier_valid:
        return "verifier_reject_response"
    return "verifier_pass_respond"


def verifier_decision(action_name: str, verifier_valid: bool | str, verifier_status: str | None) -> str:
    if not action_name:
        return "PARSER_FAILURE"
    if verifier_status == "UNKNOWN":
        return "UNKNOWN"
    if verifier_valid is False:
        return "INVALID"
    return "VALID"


def environment_label(action_name: str, env_query_error) -> str:
    if action_name != "execute":
        return ""
    return "environment-invalid" if env_query_error is True else "environment-valid"


def alignment_class(decision: str, env_label: str) -> str:
    if env_label not in {"environment-valid", "environment-invalid"}:
        return ""
    if decision == "INVALID" and env_label == "environment-invalid":
        return "true_positive"
    if decision == "INVALID" and env_label == "environment-valid":
        return "false_positive"
    if decision == "UNKNOWN" and env_label == "environment-invalid":
        return "unknown_env_invalid"
    if decision == "UNKNOWN" and env_label == "environment-valid":
        return "unknown_env_valid"
    if decision == "VALID" and env_label == "environment-invalid":
        return "false_negative"
    return "true_negative"


def add_counts(counter: Counter, row: Mapping) -> None:
    for key, value in row.items():
        counter[key] += value


def analyze_rows(rows: list[Mapping], source_file: Path, verifier: ActionVerifier) -> list[dict]:
    records: list[dict] = []
    source_run = run_name_from_source(source_file)
    for row_index, result in enumerate(rows):
        traj = result.get("traj") or []
        reward = reward_scalar(result.get("reward"))
        trajectory_success = bool(reward is not None and reward > 0)
        task_type = str(result.get("task_type", "unknown"))
        task_id = result.get("task_id", row_index)
        final_end_reason = end_reason(result)
        agent_info = result.get("agent_info") or {}
        failed_queries: list[str] = []

        assistant_positions = [
            idx for idx, message in enumerate(traj) if message.get("role") == "assistant"
        ]
        last_assistant_idx = assistant_positions[-1] if assistant_positions else None

        for turn_number, idx in enumerate(assistant_positions, start=1):
            message = traj[idx]
            raw_output = str(message.get("content") or "")
            action = parse_action(raw_output)
            next_message = traj[idx + 1] if idx + 1 < len(traj) else {}
            next_observation = (
                str(next_message.get("content") or "")
                if next_message.get("role") == "user"
                else ""
            )

            base_record = {
                "source_file": str(source_file),
                "source_run": source_run,
                "task_id": task_id,
                "task_type": task_type,
                "row_index": row_index,
                "turn_number": turn_number,
                "trajectory_success": trajectory_success,
                "reward": reward,
                "end_reason_source": final_end_reason[0],
                "end_reason_message": final_end_reason[1],
                "reported_model_calls": agent_info.get("model_calls", ""),
                "reported_env_steps": agent_info.get("env_steps", ""),
            }

            if action is None:
                records.append(
                    {
                        **base_record,
                        "classification": "parser_failure",
                        "action_name": "",
                        "verifier_decision": "PARSER_FAILURE",
                        "verifier_valid": "",
                        "verifier_status": "",
                        "error_code": "EMPTY_ACTION",
                        "env_query_error": "",
                        "environment_label": "",
                        "alignment_class": "",
                        "query_or_response": "",
                        "observation_excerpt": "",
                        "raw_output_excerpt": short_text(raw_output),
                    }
                )
                continue

            env_query_error = (
                action["name"] == "execute"
                and is_env_query_error(next_observation, final_end_reason, idx == last_assistant_idx)
            )
            verification = verifier.verify_action(action, failed_queries=failed_queries)
            verifier_status = getattr(verification, "status", "VALID")
            decision = verifier_decision(action["name"], verification.valid, verifier_status)
            env_label = environment_label(action["name"], env_query_error)
            classification = classify_step(action, verification.valid, verifier_status, env_query_error)

            records.append(
                {
                    **base_record,
                    "classification": classification,
                    "action_name": action["name"],
                    "verifier_decision": decision,
                    "verifier_valid": verification.valid,
                    "verifier_status": verifier_status,
                    "error_code": verification.error_code or "",
                    "env_query_error": env_query_error if action["name"] == "execute" else "",
                    "environment_label": env_label,
                    "alignment_class": alignment_class(decision, env_label),
                    "query_or_response": short_text(action["content"]),
                    "observation_excerpt": short_text(next_observation),
                    "raw_output_excerpt": short_text(raw_output),
                }
            )

            if env_query_error:
                failed_queries.append(action["content"])
    return records


def summarize(records: list[dict]) -> tuple[list[dict], list[dict], list[dict], list[dict], Counter]:
    task_counts: dict[str, Counter] = defaultdict(Counter)
    outcome_counts: dict[str, Counter] = defaultdict(Counter)
    trajectory_counts: dict[str, Counter] = defaultdict(Counter)
    error_codes = Counter()
    trajectory_records: dict[tuple[str, int], list[dict]] = defaultdict(list)

    for record in records:
        trajectory_records[(record["source_file"], record["row_index"])].append(record)
        row_counts = Counter()
        row_counts["steps"] = 1
        classification = record["classification"]
        row_counts[classification] += 1
        if record["action_name"] == "execute":
            row_counts["parsed_execute"] += 1
            if record["env_query_error"] is True:
                row_counts["env_query_errors"] += 1
        elif record["action_name"] == "respond":
            row_counts["parsed_respond"] += 1
        else:
            row_counts["parser_failures"] += 1

        if record["verifier_valid"] is False:
            row_counts["verifier_rejects"] += 1
            if record["action_name"] == "execute":
                row_counts["verifier_rejects_execute"] += 1
            if record["error_code"]:
                error_codes[record["error_code"]] += 1
        elif record.get("verifier_status") == "UNKNOWN":
            row_counts["verifier_unknowns"] += 1
            if record["action_name"] == "execute":
                row_counts["verifier_unknowns_execute"] += 1
            if record["error_code"]:
                error_codes[record["error_code"]] += 1

        if classification == "verifier_true_positive":
            row_counts["correctly_identified_query_failures"] += 1
        elif classification == "verifier_missed_env_failure":
            row_counts["missed_query_failures"] += 1
        elif classification == "verifier_unknown_env_failure":
            row_counts["unknown_env_failures"] += 1
        elif classification == "verifier_reject_unconfirmed":
            row_counts["unconfirmed_rejects"] += 1

        add_counts(task_counts[record["task_type"]], row_counts)
        add_counts(outcome_counts["success" if record["trajectory_success"] else "failure"], row_counts)

    for grouped_records in trajectory_records.values():
        first = grouped_records[0]
        key = "success" if first["trajectory_success"] else "failure"
        counts = Counter()
        counts["trajectories"] = 1
        if any(record["classification"] == "parser_failure" for record in grouped_records):
            counts["trajectories_with_parser_failure"] = 1
        if any(record["verifier_valid"] is False for record in grouped_records):
            counts["trajectories_with_verifier_reject"] = 1
        if any(record.get("verifier_status") == "UNKNOWN" for record in grouped_records):
            counts["trajectories_with_verifier_unknown"] = 1
        if any(record["env_query_error"] is True for record in grouped_records):
            counts["trajectories_with_env_query_error"] = 1
        if any(record["classification"] == "verifier_true_positive" for record in grouped_records):
            counts["trajectories_with_correctly_identified_query_failure"] = 1
        if any(record["classification"] == "verifier_missed_env_failure" for record in grouped_records):
            counts["trajectories_with_missed_query_failure"] = 1
        if first["end_reason_message"] == "Invalid action":
            counts["trajectories_ended_invalid_action"] = 1
        if first["end_reason_message"] == "SOQL/SOSL query error":
            counts["trajectories_ended_query_error"] = 1
        if isinstance(first.get("reported_model_calls"), int):
            counts["reported_model_calls"] = first["reported_model_calls"]
        if isinstance(first.get("reported_env_steps"), int):
            counts["reported_env_steps"] = first["reported_env_steps"]
        add_counts(trajectory_counts[key], counts)

    task_rows = [{"task_type": key, **dict(counter)} for key, counter in sorted(task_counts.items())]
    outcome_rows = [{"trajectory_outcome": key, **dict(counter)} for key, counter in sorted(outcome_counts.items())]
    trajectory_rows = [
        {"trajectory_outcome": key, **dict(counter)}
        for key, counter in sorted(trajectory_counts.items())
    ]
    overall = [{"scope": "overall", **dict(sum(task_counts.values(), Counter()))}]
    return overall, task_rows, outcome_rows, trajectory_rows, error_codes


def summarize_alignment(records: list[dict]) -> tuple[list[dict], list[dict]]:
    overall_counter = Counter()
    task_counters: dict[str, Counter] = defaultdict(Counter)
    for record in records:
        if record["action_name"] != "execute":
            continue
        row_counts = Counter()
        row_counts["query_steps"] = 1
        env_label = record.get("environment_label")
        decision = record.get("verifier_decision")
        klass = record.get("alignment_class")

        if env_label == "environment-invalid":
            row_counts["environment_invalid"] = 1
        elif env_label == "environment-valid":
            row_counts["environment_valid"] = 1
        if decision == "INVALID":
            row_counts["invalid_decisions"] = 1
        elif decision == "UNKNOWN":
            row_counts["unknown_decisions"] = 1
        elif decision == "VALID":
            row_counts["valid_decisions"] = 1

        if klass:
            row_counts[klass] = 1
        if klass == "true_positive":
            row_counts["environment_calls_avoided"] = 1

        add_counts(overall_counter, row_counts)
        add_counts(task_counters[record["task_type"]], row_counts)

    return (
        [_alignment_row("overall", overall_counter)],
        [_alignment_row(task_type, counter) for task_type, counter in sorted(task_counters.items())],
    )


def _alignment_row(scope: str, counts: Counter) -> dict:
    true_positive = counts["true_positive"]
    false_positive = counts["false_positive"]
    false_negative = counts["false_negative"] + counts["unknown_env_invalid"]
    true_negative = counts["true_negative"]
    environment_invalid = counts["environment_invalid"]
    environment_valid = counts["environment_valid"]
    query_steps = counts["query_steps"]
    review_hits = true_positive + counts["unknown_env_invalid"]

    return {
        "scope": scope,
        "query_steps": query_steps,
        "environment_invalid": environment_invalid,
        "environment_valid": environment_valid,
        "invalid_decisions": counts["invalid_decisions"],
        "unknown_decisions": counts["unknown_decisions"],
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative_strict": false_negative,
        "true_negative": true_negative,
        "unknown_env_invalid": counts["unknown_env_invalid"],
        "unknown_env_valid": counts["unknown_env_valid"],
        "invalid_precision": _rate(true_positive, true_positive + false_positive),
        "strict_recall": _rate(true_positive, environment_invalid),
        "review_coverage": _rate(review_hits, environment_invalid),
        "false_positive_rate": _rate(false_positive, environment_valid),
        "false_negative_rate_strict": _rate(false_negative, environment_invalid),
        "unknown_rate": _rate(counts["unknown_decisions"], query_steps),
        "environment_calls_avoided": counts["environment_calls_avoided"],
    }


def _rate(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return ""
    return f"{numerator / denominator:.3f}"


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def print_table(title: str, rows: list[dict], fieldnames: list[str]) -> None:
    print(f"\n{title}")
    print(",".join(fieldnames))
    for row in rows:
        print(",".join(str(row.get(field, 0)) for field in fieldnames))


def markdown_table(title: str, rows: list[dict], fieldnames: list[str]) -> str:
    lines = [f"## {title}", ""]
    lines.append("| " + " | ".join(fieldnames) + " |")
    lines.append("| " + " | ".join("---" for _ in fieldnames) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(field, 0)) for field in fieldnames) + " |")
    lines.append("")
    return "\n".join(lines)


def make_markdown_report(
    result_files: list[Path],
    skipped_count: int,
    records: list[dict],
    overall: list[dict],
    task_rows: list[dict],
    outcome_rows: list[dict],
    trajectory_rows: list[dict],
    alignment_overall: list[dict],
    alignment_by_task: list[dict],
    error_codes: Counter,
    examples_per_class: int,
) -> str:
    step_fields = [
        "steps",
        "parser_failures",
        "parsed_execute",
        "parsed_respond",
        "env_query_errors",
        "verifier_rejects",
        "verifier_unknowns",
        "correctly_identified_query_failures",
        "missed_query_failures",
        "unknown_env_failures",
        "unconfirmed_rejects",
    ]
    trajectory_fields = [
        "trajectories",
        "trajectories_with_parser_failure",
        "trajectories_with_verifier_reject",
        "trajectories_with_verifier_unknown",
        "trajectories_with_env_query_error",
        "trajectories_with_correctly_identified_query_failure",
        "trajectories_with_missed_query_failure",
        "trajectories_ended_invalid_action",
        "trajectories_ended_query_error",
        "reported_model_calls",
        "reported_env_steps",
    ]
    alignment_fields = [
        "query_steps",
        "environment_invalid",
        "environment_valid",
        "invalid_decisions",
        "unknown_decisions",
        "true_positive",
        "false_positive",
        "false_negative_strict",
        "true_negative",
        "unknown_env_invalid",
        "unknown_env_valid",
        "invalid_precision",
        "strict_recall",
        "review_coverage",
        "false_positive_rate",
        "false_negative_rate_strict",
        "unknown_rate",
        "environment_calls_avoided",
    ]
    lines = [
        "# CRMArena Syntactic Verifier Replay",
        "",
        f"- Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"- Analyzed files: {len(result_files) - skipped_count}",
        f"- Skipped non-result JSON files: {skipped_count}",
        f"- Analyzed assistant steps: {len(records)}",
        "",
        (
            "Correctly identified and missed query failures are inferred from saved Salesforce "
            "observations immediately after `execute` actions. The script looks for recorded "
            "Salesforce error markers such as `MALFORMED_QUERY`, `INVALID_FIELD`, and "
            "`ERROR at Row`; it does not re-run live queries."
        ),
        "",
        markdown_table("Overall Step Counts", overall, ["scope", *step_fields]),
        markdown_table("Step Counts By Task", task_rows, ["task_type", *step_fields]),
        markdown_table("Step Counts By Trajectory Outcome", outcome_rows, ["trajectory_outcome", *step_fields]),
        markdown_table(
            "Trajectory-Level Invalid Action Impact",
            trajectory_rows,
            ["trajectory_outcome", *trajectory_fields],
        ),
        markdown_table("Verifier Alignment Overall", alignment_overall, ["scope", *alignment_fields]),
        markdown_table("Verifier Alignment By Task", alignment_by_task, ["scope", *alignment_fields]),
    ]
    if error_codes:
        lines.extend(["## Verifier Error Codes", "", "| error_code | count |", "| --- | --- |"])
        for code, count in error_codes.most_common():
            lines.append(f"| {code} | {count} |")
        lines.append("")

    if examples_per_class > 0:
        lines.extend(["## Examples", ""])
        for classification in (
            "parser_failure",
            "verifier_true_positive",
            "verifier_unknown_env_failure",
            "verifier_missed_env_failure",
            "verifier_reject_unconfirmed",
        ):
            matches = [record for record in records if record["classification"] == classification]
            if not matches:
                continue
            lines.extend([f"### {classification}", ""])
            for record in matches[:examples_per_class]:
                lines.append(
                    f"- `{record['task_type']}` task_id={record['task_id']} "
                    f"turn={record['turn_number']} success={record['trajectory_success']} "
                    f"code={record['error_code'] or 'none'}"
                )
                if record["query_or_response"]:
                    lines.append(f"  - action: `{record['query_or_response']}`")
                if record["observation_excerpt"]:
                    lines.append(f"  - observation: `{record['observation_excerpt']}`")
                elif record["raw_output_excerpt"]:
                    lines.append(f"  - raw: `{record['raw_output_excerpt']}`")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def default_summary_path(paths: list[Path], label: str | None = None) -> Path:
    source_name = "results"
    if label:
        source_name = label
    elif paths:
        source_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", paths[0].name).strip("_") or source_name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "verifiers" / "summaries" / f"{source_name}_verifier_replay_{timestamp}.md"


def default_corpus_path(label: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "verifiers" / "replay_corpus" / f"{label}_verifier_replay_{timestamp}.jsonl"


def default_alignment_path(label: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "verifiers" / "replay_corpus" / f"{label}_verifier_alignment_{timestamp}.json"


def print_examples(records: list[dict], per_class: int) -> None:
    if per_class <= 0:
        return
    classes = (
        "parser_failure",
        "verifier_true_positive",
        "verifier_unknown_env_failure",
        "verifier_missed_env_failure",
        "verifier_reject_unconfirmed",
    )
    print("\nExamples")
    for classification in classes:
        matches = [record for record in records if record["classification"] == classification]
        if not matches:
            continue
        print(f"\n[{classification}]")
        for record in matches[:per_class]:
            print(
                f"- {record['task_type']} task_id={record['task_id']} turn={record['turn_number']} "
                f"success={record['trajectory_success']} code={record['error_code']}"
            )
            if record["query_or_response"]:
                print(f"  action: {record['query_or_response']}")
            if record["observation_excerpt"]:
                print(f"  observation: {record['observation_excerpt']}")
            elif record["raw_output_excerpt"]:
                print(f"  raw: {record['raw_output_excerpt']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Replay CRMArena benchmark result JSONs through the syntactic verifier and "
            "compare verifier decisions against saved Salesforce query errors."
        )
    )
    parser.add_argument("paths", nargs="*", type=Path, help="Result JSON files or directories to scan recursively.")
    parser.add_argument(
        "--previous-runs",
        action="store_true",
        help="Analyze prior generated CRMArena runs under results/original, results/b2b_multi-turn, and archived_results.",
    )
    parser.add_argument(
        "--include-shared",
        action="store_true",
        help="Include bundled/reference result files under results/shared. Omitted by default for replay corpus generation.",
    )
    parser.add_argument(
        "--schema",
        choices=("auto", "prompt", "b2b", "b2c", "original"),
        default="auto",
        help="Schema source. auto uses saved system prompts first, then b2b assets.",
    )
    parser.add_argument("--csv", type=Path, default=None, help="Optional CSV path for per-step records.")
    parser.add_argument("--jsonl", type=Path, default=None, help="Optional JSONL path for per-step records.")
    parser.add_argument("--corpus-jsonl", type=Path, default=None, help="Optional JSONL path for replay corpus records.")
    parser.add_argument("--alignment-json", type=Path, default=None, help="Optional JSON path for alignment metrics.")
    parser.add_argument(
        "--md",
        type=Path,
        default=None,
        help="Markdown summary path. Defaults to verifiers/summaries/<input>_verifier_replay_<timestamp>.md.",
    )
    parser.add_argument(
        "--no-md",
        action="store_true",
        help="Do not write a Markdown summary.",
    )
    parser.add_argument("--examples", type=int, default=2, help="Examples to print for key classifications.")
    args = parser.parse_args()

    paths = list(args.paths)
    corpus_label = "results"
    if args.previous_runs:
        paths.extend(default_previous_paths())
        corpus_label = "all_previous_generated_runs"
    if not paths:
        parser.error("provide paths to analyze or use --previous-runs")

    result_files = iter_result_files(paths, include_shared=args.include_shared)
    all_records: list[dict] = []
    skipped = []

    for result_file in result_files:
        rows = load_result_rows(result_file)
        if not rows:
            skipped.append(result_file)
            continue
        verifier = build_verifier(rows, args.schema)
        all_records.extend(analyze_rows(rows, result_file, verifier))

    if not all_records:
        raise SystemExit("No benchmark result rows with trajectories were found.")

    overall, task_rows, outcome_rows, trajectory_rows, error_codes = summarize(all_records)
    alignment_overall, alignment_by_task = summarize_alignment(all_records)

    print(f"Analyzed files: {len(result_files) - len(skipped)}")
    print(f"Skipped non-result JSON files: {len(skipped)}")
    print(f"Analyzed assistant steps: {len(all_records)}")
    print(
        "Correct/missed query-failure labels are inferred from saved Salesforce output, "
        "not from live query execution."
    )

    fields = [
        "steps",
        "parser_failures",
        "parsed_execute",
        "parsed_respond",
        "env_query_errors",
        "verifier_rejects",
        "verifier_unknowns",
        "correctly_identified_query_failures",
        "missed_query_failures",
        "unknown_env_failures",
        "unconfirmed_rejects",
    ]
    print_table("Overall", overall, ["scope", *fields])
    print_table("By Task", task_rows, ["task_type", *fields])
    print_table("By Trajectory Outcome", outcome_rows, ["trajectory_outcome", *fields])
    trajectory_fields = [
        "trajectories",
        "trajectories_with_parser_failure",
        "trajectories_with_verifier_reject",
        "trajectories_with_verifier_unknown",
        "trajectories_with_env_query_error",
        "trajectories_with_correctly_identified_query_failure",
        "trajectories_with_missed_query_failure",
        "trajectories_ended_invalid_action",
        "trajectories_ended_query_error",
        "reported_model_calls",
        "reported_env_steps",
    ]
    print_table("Trajectory-Level Invalid Action Impact", trajectory_rows, ["trajectory_outcome", *trajectory_fields])
    alignment_fields = [
        "query_steps",
        "environment_invalid",
        "environment_valid",
        "invalid_decisions",
        "unknown_decisions",
        "true_positive",
        "false_positive",
        "false_negative_strict",
        "true_negative",
        "unknown_env_invalid",
        "unknown_env_valid",
        "invalid_precision",
        "strict_recall",
        "review_coverage",
        "false_positive_rate",
        "false_negative_rate_strict",
        "unknown_rate",
        "environment_calls_avoided",
    ]
    print_table("Verifier Alignment Overall", alignment_overall, ["scope", *alignment_fields])
    print_table("Verifier Alignment By Task", alignment_by_task, ["scope", *alignment_fields])

    if error_codes:
        print("\nVerifier Error Codes")
        print("error_code,count")
        for code, count in error_codes.most_common():
            print(f"{code},{count}")

    print_examples(all_records, args.examples)

    if args.csv:
        write_csv(args.csv, all_records)
        print(f"\nWrote per-step CSV: {args.csv}")
    if args.jsonl:
        write_jsonl(args.jsonl, all_records)
        print(f"Wrote per-step JSONL: {args.jsonl}")
    corpus_jsonl = args.corpus_jsonl
    if args.previous_runs and corpus_jsonl is None:
        corpus_jsonl = default_corpus_path(corpus_label)
    if corpus_jsonl:
        write_jsonl(corpus_jsonl, all_records)
        print(f"Wrote replay corpus JSONL: {corpus_jsonl}")
    alignment_json = args.alignment_json
    if args.previous_runs and alignment_json is None:
        alignment_json = default_alignment_path(corpus_label)
    if alignment_json:
        alignment_json.parent.mkdir(parents=True, exist_ok=True)
        alignment_json.write_text(
            json.dumps(
                {
                    "overall": alignment_overall,
                    "by_task": alignment_by_task,
                    "generated": datetime.now().isoformat(timespec="seconds"),
                    "source_files_analyzed": len(result_files) - len(skipped),
                    "source_files_skipped": len(skipped),
                    "records": len(all_records),
                    "shared_results_included": args.include_shared,
                },
                indent=2,
            )
            + "\n"
        )
        print(f"Wrote alignment JSON: {alignment_json}")
    if not args.no_md:
        md_path = args.md or default_summary_path(paths, corpus_label if args.previous_runs else None)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(
            make_markdown_report(
                result_files=result_files,
                skipped_count=len(skipped),
                records=all_records,
                overall=overall,
                task_rows=task_rows,
                outcome_rows=outcome_rows,
                trajectory_rows=trajectory_rows,
                alignment_overall=alignment_overall,
                alignment_by_task=alignment_by_task,
                error_codes=error_codes,
                examples_per_class=args.examples,
            )
        )
        print(f"Wrote Markdown summary: {md_path}")


if __name__ == "__main__":
    main()
