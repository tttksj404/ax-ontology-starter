from dataclasses import dataclass

from pydantic import Field, SecretStr

from ax_starter.common import Contract, Principal
from ax_starter.release_gate import ReleaseCriteria, ReleaseEvaluation


@dataclass(frozen=True, slots=True)
class AuthenticatedContext:
    """Request-local credential used for revocation checks, never a response or audit record."""

    principal: Principal
    credential: SecretStr


class ApprovalRequest(Contract):
    reviewed_payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ReleaseRequest(Contract):
    evaluation: ReleaseEvaluation
    criteria: ReleaseCriteria
