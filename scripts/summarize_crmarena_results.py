#!/usr/bin/env python3
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def as_float(value):
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def reward_scalar(reward):
    if isinstance(reward, dict):
        for key in ("score", "reward", "em", "f1"):
            value = as_float(reward.get(key))
            if value is not None:
                return value
        rouge = reward.get("rouge")
        if isinstance(rouge, dict):
            value = as_float(rouge.get("rouge-l"))
            if value is not None:
                return value
    return as_float(reward)


def reward_metric(reward, metric):
    if not isinstance(reward, dict):
        return None
    if metric in reward:
        return as_float(reward[metric])
    if metric.startswith("rouge."):
        rouge = reward.get("rouge")
        if isinstance(rouge, dict):
            return as_float(rouge.get(metric.split(".", 1)[1]))
    return None


def end_reason(result):
    info = result.get("agent_info") or {}
    reason = info.get("end_reason") or {}
    if reason:
        return reason.get("source", ""), reason.get("message", ""), reason.get("content", "")
    return info.get("source", ""), info.get("content", ""), info.get("content", "")


def result_files(path):
    if path.is_file():
        return [path]
    return sorted(p for p in path.rglob("*.json") if p.is_file())


def load_rows(path):
    rows = []
    for result_file in result_files(path):
        with result_file.open() as f:
            data = json.load(f)
        if isinstance(data, list):
            file_rows = data
        elif isinstance(data, dict) and isinstance(data.get("results"), list):
            file_rows = data["results"]
        else:
            continue
        for row in file_rows:
            if isinstance(row, dict):
                rows.append(row)
    return rows


def number_value(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def list_sum(value):
    if not isinstance(value, list):
        return None
    total = 0.0
    found = False
    for item in value:
        item_value = number_value(item)
        if item_value is not None:
            total += item_value
            found = True
    return total if found else None


def agent_metric(item, key):
    info = item.get("agent_info") or {}
    return number_value(info.get(key))


def usage_total(item, key):
    info = item.get("agent_info") or {}
    usage = info.get("usage") or {}
    return list_sum(usage.get(key))


def mean(values):
    values = [value for value in values if value is not None]
    if not values:
        return ""
    return sum(values) / len(values)


def fmt(value):
    if value == "":
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def summarize(path):
    rows = load_rows(path)

    groups = defaultdict(list)
    for row in rows:
        groups[row.get("task_type", "unknown")].append(row)

    summaries = []
    errors = Counter()
    for task_type, items in sorted(groups.items()):
        reward_values = [reward_scalar(item.get("reward")) for item in items]
        reward_values = [value for value in reward_values if value is not None]
        f1_values = [reward_metric(item.get("reward"), "f1") for item in items]
        f1_values = [value for value in f1_values if value is not None]
        em_values = [reward_metric(item.get("reward"), "em") for item in items]
        em_values = [value for value in em_values if value is not None]

        reason_counts = Counter()
        api_errors = 0
        empty_content = 0
        query_errors = 0
        invalid_actions = 0
        submitted = 0
        max_turns = 0
        for item in items:
            source, message, content = end_reason(item)
            message = str(message or "unknown")
            reason_counts[message] += 1
            if source == "api" or str(message).startswith("Error:"):
                api_errors += 1
                errors[str(message)] += 1
            if message == "Submit action":
                submitted += 1
            elif message == "Max turns reached":
                max_turns += 1
            elif message == "Invalid action":
                invalid_actions += 1
                if not str(content).strip():
                    empty_content += 1
            elif message == "SOQL/SOSL query error":
                query_errors += 1

        successes = sum(1 for value in reward_values if value > 0)
        model_calls = [agent_metric(item, "model_calls") for item in items]
        env_steps = [agent_metric(item, "env_steps") for item in items]
        prompt_tokens = [usage_total(item, "prompt_tokens") for item in items]
        completion_tokens = [usage_total(item, "completion_tokens") for item in items]
        total_tokens = [usage_total(item, "total_tokens") for item in items]

        summaries.append(
            {
                "task_type": task_type,
                "n": len(items),
                "successes": successes,
                "success_rate": successes / len(items) if items else "",
                "submitted": submitted,
                "max_turns": max_turns,
                "query_errors": query_errors,
                "invalid_actions": invalid_actions,
                "empty_content": empty_content,
                "api_errors": api_errors,
                "avg_reward": sum(reward_values) / len(reward_values) if reward_values else "",
                "avg_em": sum(em_values) / len(em_values) if em_values else "",
                "avg_f1": sum(f1_values) / len(f1_values) if f1_values else "",
                "nonzero_rewards": successes,
                "avg_model_calls": mean(model_calls),
                "avg_env_steps": mean(env_steps),
                "avg_prompt_tokens": mean(prompt_tokens),
                "avg_completion_tokens": mean(completion_tokens),
                "avg_total_tokens": mean(total_tokens),
                "top_end_reasons": "; ".join(f"{k}:{v}" for k, v in reason_counts.most_common(4)),
            }
        )
    return rows, summaries, errors


def write_csv(path, summaries, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summaries)


def markdown_table(summaries, fieldnames):
    lines = []
    lines.append("| " + " | ".join(fieldnames) + " |")
    lines.append("| " + " | ".join(["---"] * len(fieldnames)) + " |")
    for row in summaries:
        lines.append("| " + " | ".join(fmt(row.get(field, "")) for field in fieldnames) + " |")
    return "\n".join(lines)


def write_markdown(path, source_path, rows, summaries, errors, table_fields, top_errors):
    path.parent.mkdir(parents=True, exist_ok=True)
    total = len(rows)
    total_successes = sum(int(row["successes"]) for row in summaries)
    total_api_errors = sum(int(row["api_errors"]) for row in summaries)
    total_query_errors = sum(int(row["query_errors"]) for row in summaries)
    total_invalid_actions = sum(int(row["invalid_actions"]) for row in summaries)
    success_rate = total_successes / total if total else 0.0

    lines = [
        "# CRMArena Result Summary",
        "",
        f"Source: `{source_path}`",
        "",
        "## Overall",
        "",
        f"- Tasks: {total}",
        f"- Successes: {total_successes}",
        f"- Success rate: {success_rate:.4f}",
        f"- API errors: {total_api_errors}",
        f"- SOQL/SOSL query-error endings: {total_query_errors}",
        f"- Invalid-action endings: {total_invalid_actions}",
        "",
        "## By Task",
        "",
        markdown_table(summaries, table_fields),
    ]
    if errors:
        lines.extend(["", "## Top API/Run Errors", ""])
        for message, count in errors.most_common(top_errors):
            lines.append(f"- {count}: {message}")
    path.write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Summarize CRMArena result JSON files.")
    parser.add_argument("results_path", type=Path, help="A result JSON file or directory containing result JSON files.")
    parser.add_argument("--csv", type=Path, default=None, help="Optional CSV output path.")
    parser.add_argument("--markdown", type=Path, default=None, help="Optional Markdown summary output path.")
    parser.add_argument("--top-errors", type=int, default=10)
    args = parser.parse_args()

    rows, summaries, errors = summarize(args.results_path)
    fieldnames = [
        "task_type",
        "n",
        "successes",
        "success_rate",
        "submitted",
        "max_turns",
        "query_errors",
        "invalid_actions",
        "empty_content",
        "api_errors",
        "avg_reward",
        "avg_em",
        "avg_f1",
        "nonzero_rewards",
        "avg_model_calls",
        "avg_env_steps",
        "avg_prompt_tokens",
        "avg_completion_tokens",
        "avg_total_tokens",
        "top_end_reasons",
    ]

    print(f"Path: {args.results_path}")
    print(f"Total tasks: {len(rows)}")
    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(summaries)

    if errors:
        print("\nTop API/errors:")
        for message, count in errors.most_common(args.top_errors):
            print(f"{count}\t{message}")

    if args.csv:
        write_csv(args.csv, summaries, fieldnames)
        print(f"\nWrote CSV: {args.csv}")
    if args.markdown:
        write_markdown(args.markdown, args.results_path, rows, summaries, errors, fieldnames, args.top_errors)
        print(f"Wrote Markdown: {args.markdown}")


if __name__ == "__main__":
    main()
