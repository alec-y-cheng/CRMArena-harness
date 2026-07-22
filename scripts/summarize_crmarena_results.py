#!/usr/bin/env python3
import argparse
import csv
import json
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


def summarize(path):
    with path.open() as f:
        rows = json.load(f)

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

        summaries.append(
            {
                "task_type": task_type,
                "n": len(items),
                "submitted": submitted,
                "max_turns": max_turns,
                "query_errors": query_errors,
                "invalid_actions": invalid_actions,
                "empty_content": empty_content,
                "api_errors": api_errors,
                "avg_reward": sum(reward_values) / len(reward_values) if reward_values else "",
                "avg_em": sum(em_values) / len(em_values) if em_values else "",
                "avg_f1": sum(f1_values) / len(f1_values) if f1_values else "",
                "nonzero_rewards": sum(1 for value in reward_values if value > 0),
                "top_end_reasons": "; ".join(f"{k}:{v}" for k, v in reason_counts.most_common(4)),
            }
        )
    return rows, summaries, errors


def main():
    parser = argparse.ArgumentParser(description="Summarize CRMArena result JSON files.")
    parser.add_argument("results_json", type=Path)
    parser.add_argument("--csv", type=Path, default=None, help="Optional CSV output path.")
    parser.add_argument("--top-errors", type=int, default=10)
    args = parser.parse_args()

    rows, summaries, errors = summarize(args.results_json)
    fieldnames = [
        "task_type",
        "n",
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
        "top_end_reasons",
    ]

    print(f"File: {args.results_json}")
    print(f"Total tasks: {len(rows)}")
    writer = csv.DictWriter(__import__("sys").stdout, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(summaries)

    if errors:
        print("\nTop API/errors:")
        for message, count in errors.most_common(args.top_errors):
            print(f"{count}\t{message}")

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(summaries)
        print(f"\nWrote CSV: {args.csv}")


if __name__ == "__main__":
    main()
