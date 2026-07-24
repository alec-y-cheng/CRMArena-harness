#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from verifiers.schema_loader import write_schema_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Export official CRMArena schema configs to local JSON snapshots.")
    parser.add_argument(
        "--schemas",
        nargs="+",
        choices=("b2b", "b2c", "original"),
        default=["b2b", "b2c", "original"],
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "verifiers" / "schema_snapshots",
    )
    args = parser.parse_args()

    for schema_name in args.schemas:
        output_path = write_schema_snapshot(schema_name, args.output_dir)
        print(output_path)


if __name__ == "__main__":
    main()
