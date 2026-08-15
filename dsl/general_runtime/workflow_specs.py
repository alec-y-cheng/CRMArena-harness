"""Loader for bundled general-runtime workflow specs."""

import json
from pathlib import Path
from typing import List

from dsl.general_runtime.state import WorkflowSpec
from dsl.general_runtime.verifier import validate_workflow_spec

SPEC_DIR = Path(__file__).with_name("workflow_specs")


def list_workflow_specs() -> List[str]:
    return sorted(path.stem for path in SPEC_DIR.glob("*.json"))


def load_workflow_spec(workflow_id: str, validate: bool = True) -> WorkflowSpec:
    path = SPEC_DIR / "{}.json".format(workflow_id)
    if not path.exists():
        raise KeyError("Unknown workflow spec: {}".format(workflow_id))
    spec = WorkflowSpec(json.loads(path.read_text()))
    if validate:
        validate_workflow_spec(spec)
    return spec


def load_all_workflow_specs(validate: bool = True) -> List[WorkflowSpec]:
    return [load_workflow_spec(name, validate=validate) for name in list_workflow_specs()]
