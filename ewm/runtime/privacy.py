"""Disclosure verifier interfaces."""

from ewm.ir.state import ExecutionState


def verify_disclosure(state: ExecutionState):
    raise NotImplementedError("Disclosure verification is implemented in a later phase.")

