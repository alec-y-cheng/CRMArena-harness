"""Completion-state evaluation for the generic EWM runtime."""

from typing import Optional

from ewm.ir.frame import InstanceFrame
from ewm.ir.state import CompletionState, ExecutionState
from ewm.runtime.verifier import VerifierSuiteResult


def evaluate_completion(
    frame: InstanceFrame,
    state: ExecutionState,
    suite_result: Optional[VerifierSuiteResult] = None,
) -> CompletionState:
    """Evaluate whether the current candidate outcome/response can finish.

    This is deliberately generic. It does not know benchmark task labels; it
    checks common runtime invariants and leaves semantic judgments to verifier
    results and LLM-produced claims.
    """

    if suite_result is not None and not suite_result.valid:
        return CompletionState(
            ready=False,
            status="needs_verification",
            needed=[
                {
                    "source": "verifier",
                    "description": suite_result.reason,
                }
            ],
            verifier_summary=suite_result.to_dict(),
            reason=suite_result.reason,
        )

    if state.candidates.get("response") is None:
        return CompletionState(
            ready=False,
            status="needs_action",
            needed=[
                {
                    "source": "action",
                    "description": "No candidate response has been proposed.",
                }
            ],
            reason="The controller must propose a candidate response before completion.",
        )

    if suite_result is None and frame.outcome_contract.requires_verification and not _has_supporting_claim_or_evidence(state):
        return CompletionState(
            ready=False,
            status="needs_verification",
            needed=[
                {
                    "source": "environment",
                    "description": "No collected evidence or supported claim is available for the outcome contract.",
                }
            ],
            reason="The candidate response is not yet grounded in runtime evidence.",
        )

    return CompletionState(
        ready=True,
        status="ready_to_respond",
        needed=[],
        verifier_summary=suite_result.to_dict() if suite_result else {"status": "allowed"},
        reason="Candidate outcome and response satisfy generic completion checks.",
    )


def _has_supporting_claim_or_evidence(state: ExecutionState) -> bool:
    for claim in state.derived.get("claims", []):
        if claim.status in ("supported", "verified", "high_confidence") and claim.supporting_evidence_ids:
            return True
    return bool(state.collected.get("evidence"))
