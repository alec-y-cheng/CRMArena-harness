import json
import os
from pathlib import Path
from typing import Iterable, List, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HF_HOME = Path("/work/11669/aleccheng/vista/cache-vista/huggingface")


def default_hf_cache_env() -> None:
    if DEFAULT_HF_HOME.exists():
        os.environ.setdefault("HF_HOME", str(DEFAULT_HF_HOME))
        os.environ.setdefault("HF_DATASETS_CACHE", str(DEFAULT_HF_HOME / "datasets"))


def load_crmarena_schema(schema_name: str) -> List[Mapping]:
    default_hf_cache_env()
    # Vista benchmark runs should be reproducible from the cached HF datasets.
    # Set CRMARENA_SCHEMA_OFFLINE=0 if a fresh download is intentionally needed.
    if os.environ.get("CRMARENA_SCHEMA_OFFLINE", "1") != "0":
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("HF_DATASETS_OFFLINE", "1")

    from datasets import load_dataset

    if schema_name == "b2b":
        dataset = load_dataset("Salesforce/CRMArenaPro", "b2b_schema")
        rows = list(dataset["b2b_schema"])
    elif schema_name == "b2c":
        dataset = load_dataset("Salesforce/CRMArenaPro", "b2c_schema")
        rows = list(dataset["b2c_schema"])
    elif schema_name == "original":
        dataset = load_dataset("Salesforce/CRMArena", "schema")
        rows = list(dataset["test"])
    else:
        raise ValueError(f"Unsupported schema: {schema_name}")

    return clean_schema(rows)


def clean_schema(schema_rows: Iterable[Mapping]) -> List[dict]:
    cleaned: List[dict] = []
    for item in schema_rows:
        object_name = item.get("object")
        fields = item.get("fields")
        if not object_name or not isinstance(fields, Mapping):
            continue
        cleaned.append(
            {
                "object": str(object_name),
                "fields": {
                    str(field): str(description or "")
                    for field, description in fields.items()
                    if field and description is not None
                },
            }
        )
    return cleaned


def write_schema_snapshot(schema_name: str, output_dir: Path) -> Path:
    schema = load_crmarena_schema(schema_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"crmarena_{schema_name}_schema.json"
    output_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    return output_path
