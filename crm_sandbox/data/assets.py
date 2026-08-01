import json
import os
from pathlib import Path
from typing import Callable, Iterator, List, Optional

from datasets import load_dataset
from huggingface_hub import hf_hub_download


def _clean_fields_in_schemas(schema_list_of_dicts):
    """
    Helper function to remove None values from 'fields' dictionaries
    in a list of schemas. This is a work around for huggingface's
    data representations where fields might contain None values.
    """
    for schema_dict in schema_list_of_dicts:
        if isinstance(schema_dict.get("fields"), dict):
            schema_dict["fields"] = {
                k: v for k, v in schema_dict["fields"].items() if v is not None
            }


class LazyDatasetRecords:
    """Load a Hugging Face dataset split only when the selected run needs it."""

    def __init__(
        self,
        dataset_name: str,
        config_name: str,
        split_name: str,
        json_filename: Optional[str] = None,
        postprocess: Optional[Callable[[List[dict]], None]] = None,
    ) -> None:
        self.dataset_name = dataset_name
        self.config_name = config_name
        self.split_name = split_name
        self.json_filename = json_filename
        self.postprocess = postprocess
        self._records = None

    def materialize(self) -> List[dict]:
        if self._records is None:
            records = self._load_records()
            if self.postprocess is not None:
                self.postprocess(records)
            self._records = records
        return self._records

    def _load_records(self) -> List[dict]:
        if self.json_filename:
            try:
                return _load_hf_json_records(self.dataset_name, self.json_filename)
            except Exception as exc:
                print(
                    "Direct JSON asset load failed; falling back to datasets.load_dataset "
                    f"for {self.dataset_name}/{self.config_name}/{self.split_name}: {exc}",
                    flush=True,
                )
        dataset = load_dataset(self.dataset_name, self.config_name)
        return [data for data in dataset[self.split_name]]

    def __iter__(self) -> Iterator[dict]:
        return iter(self.materialize())

    def __len__(self) -> int:
        return len(self.materialize())

    def __getitem__(self, index):
        return self.materialize()[index]

    def __repr__(self) -> str:
        if self._records is None:
            return (
                "LazyDatasetRecords("
                f"dataset_name={self.dataset_name!r}, "
                f"config_name={self.config_name!r}, "
                f"split_name={self.split_name!r}, "
                f"json_filename={self.json_filename!r}, "
                "loaded=False)"
            )
        return repr(self._records)


def _load_hf_json_records(dataset_name: str, filename: str) -> List[dict]:
    path = _hf_json_path(dataset_name, filename)
    with open(path, "r") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array in {path}, found {type(data).__name__}")
    return data


def _hf_json_path(dataset_name: str, filename: str) -> str:
    local_files_only = os.environ.get("HF_HUB_OFFLINE") == "1" or os.environ.get("HF_DATASETS_OFFLINE") == "1"
    cache_dir = os.environ.get("HF_HOME")
    try:
        return hf_hub_download(
            repo_id=dataset_name,
            filename=filename,
            repo_type="dataset",
            cache_dir=cache_dir,
            local_files_only=local_files_only,
        )
    except Exception:
        cached_path = _find_cached_download(filename)
        if cached_path:
            return cached_path
        raise


def _find_cached_download(filename: str) -> Optional[str]:
    cache_roots = []
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        cache_roots.append(Path(hf_home))
    cache_roots.append(Path.home() / ".cache" / "huggingface")
    cache_roots.append(Path("/work/hdd/bgtb/acheng11/qwen_agent_ft/cache/huggingface"))

    seen = set()
    for cache_root in cache_roots:
        if cache_root in seen:
            continue
        seen.add(cache_root)
        downloads_dir = cache_root / "datasets" / "downloads"
        if not downloads_dir.exists():
            continue
        for metadata_path in downloads_dir.glob("*.json"):
            try:
                with metadata_path.open("r") as handle:
                    metadata = json.load(handle)
            except Exception:
                continue
            url = str(metadata.get("url", ""))
            if not url.endswith("/" + filename):
                continue
            data_path = metadata_path.with_suffix("")
            if data_path.exists():
                return str(data_path)
    return None


## CRMArena
TASKS_ORIGINAL = LazyDatasetRecords(
    "Salesforce/CRMArena",
    "CRMArena",
    "test",
    json_filename="crmarena_w_metadata.json",
)
SCHEMA_ORIGINAL = LazyDatasetRecords(
    "Salesforce/CRMArena",
    "schema",
    "test",
    json_filename="schema_with_dependencies.json",
    postprocess=_clean_fields_in_schemas,
)


## CRMArena Pro
TASKS_B2B = LazyDatasetRecords(
    "Salesforce/CRMArenaPro",
    "CRMArenaPro",
    "b2b",
    json_filename="tasks_b2b.json",
)
TASKS_B2B_INTERACTIVE = LazyDatasetRecords(
    "Salesforce/CRMArenaPro",
    "CRMArenaPro",
    "b2b_interactive",
    json_filename="tasks_b2b_interactive.json",
)
TASKS_B2C = LazyDatasetRecords(
    "Salesforce/CRMArenaPro",
    "CRMArenaPro",
    "b2c",
    json_filename="tasks_b2c.json",
)
TASKS_B2C_INTERACTIVE = LazyDatasetRecords(
    "Salesforce/CRMArenaPro",
    "CRMArenaPro",
    "b2c_interactive",
    json_filename="tasks_b2c_interactive.json",
)
B2B_SCHEMA = LazyDatasetRecords(
    "Salesforce/CRMArenaPro",
    "b2b_schema",
    "b2b_schema",
    json_filename="b2b_schema.json",
    postprocess=_clean_fields_in_schemas,
)
B2C_SCHEMA = LazyDatasetRecords(
    "Salesforce/CRMArenaPro",
    "b2c_schema",
    "b2c_schema",
    json_filename="b2c_schema.json",
    postprocess=_clean_fields_in_schemas,
)


TOOLS = None

EXTERNAL_FACING_TASKS = [
    "knowledge_qa",
    "named_entity_disambiguation",
    "private_customer_information",
    "internal_operation_data",
    "confidential_company_knowledge",
]
