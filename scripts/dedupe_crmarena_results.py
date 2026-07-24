#!/usr/bin/env python3
import argparse
import json
import shutil
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Optional


def result_files(path: Path):
    if path.is_file():
        return [path]
    return sorted(p for p in path.rglob("*.json") if p.is_file())


def row_key(row: dict) -> Optional[str]:
    value = row.get("task_id", row.get("idx"))
    return str(value) if value is not None else None


def dedupe_rows(rows, keep: str):
    by_key: OrderedDict[str, dict] = OrderedDict()
    without_key = []
    duplicates = 0

    for row in rows:
        key = row_key(row)
        if key is None:
            without_key.append(row)
            continue
        if key in by_key:
            duplicates += 1
            if keep == "last":
                by_key[key] = row
        else:
            by_key[key] = row

    return without_key + list(by_key.values()), duplicates


def load_result_file(path: Path):
    with path.open() as f:
        data = json.load(f)
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        return data["results"], data
    return None, data


def write_result_file(path: Path, rows: list[dict], original):
    if isinstance(original, dict):
        original["results"] = rows
        payload = original
    else:
        payload = rows
    path.write_text(json.dumps(payload, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Deduplicate CRMArena result JSON files by task_id/idx.")
    parser.add_argument("path", type=Path, help="A result JSON file or directory containing result JSON files.")
    parser.add_argument("--keep", choices=("first", "last"), default="last")
    parser.add_argument("--no-backup", action="store_true", help="Do not write .bak_TIMESTAMP backups before editing.")
    parser.add_argument("--dry-run", action="store_true", help="Report duplicate counts without writing files.")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    total_duplicates = 0
    changed = 0

    for path in result_files(args.path):
        rows, original = load_result_file(path)
        if rows is None:
            continue
        deduped, duplicates = dedupe_rows(rows, args.keep)
        total_duplicates += duplicates
        if duplicates:
            changed += 1
            print(f"{path}: rows={len(rows)} deduped={len(deduped)} duplicates={duplicates}")
            if not args.dry_run:
                if not args.no_backup:
                    shutil.copy2(path, path.with_suffix(path.suffix + f".bak_{timestamp}"))
                write_result_file(path, deduped, original)

    print(f"Files changed: {0 if args.dry_run else changed}")
    print(f"Duplicate rows found: {total_duplicates}")


if __name__ == "__main__":
    main()
