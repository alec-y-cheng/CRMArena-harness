from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    error_code: Optional[str] = None
    feedback: Optional[str] = None
    status: str = "VALID"
    rule: Optional[str] = None
