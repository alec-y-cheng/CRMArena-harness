"""Completion-state evaluation for the generic EWM runtime."""

from ewm.ir.frame import InstanceFrame
from ewm.ir.state import CompletionState, ExecutionState


def evaluate_completion(frame: InstanceFrame, state: ExecutionState) -> CompletionState:
    raise NotImplementedError("Completion evaluation is implemented in a later phase.")

