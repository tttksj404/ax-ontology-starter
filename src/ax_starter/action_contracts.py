from enum import StrEnum

from pydantic import AwareDatetime, Field

from ax_starter.common import ActorKind, Contract, Identifier, Purpose
from ax_starter.ontology import Entity


class ProposalState(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    EXECUTED = "executed"
    ROLLED_BACK = "rolled_back"


class ProposeRequest(Contract):
    action_type: Identifier
    object_id: Identifier
    new_status: Identifier
    expected_version: int = Field(ge=1)
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=10)
    purpose: Purpose = Purpose.OPERATIONS
    request_key: Identifier


class EvidenceRef(Contract):
    id: Identifier
    source_version: Identifier
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    access_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


def _missing(value: ActorKind | str | None) -> bool:
    return value is None


def _no_evidence(value: tuple[EvidenceRef, ...]) -> bool:
    return not value


class ActionPayload(Contract):
    action_type: str
    object_id: str
    tenant: str
    proposer: str
    proposer_actor_kind: ActorKind | None = Field(default=None, exclude_if=_missing)
    proposer_person_id: Identifier | None = Field(default=None, exclude_if=_missing)
    previous_status: str
    new_status: str
    expected_version: int
    evidence_ids: tuple[str, ...]
    evidence_hashes: tuple[str, ...]
    evidence_refs: tuple[EvidenceRef, ...] = Field(default=(), exclude_if=_no_evidence)
    purpose: Purpose
    pack_hash: str
    expires_at: AwareDatetime


class Proposal(Contract):
    id: str
    request_key: str
    payload: ActionPayload
    payload_hash: str
    state: ProposalState
    approver: str | None = None
    approver_actor_kind: ActorKind | None = Field(default=None, exclude_if=_missing)
    approver_person_id: Identifier | None = Field(default=None, exclude_if=_missing)
    approval_hash: str | None = None
    result_version: int | None = None
    rollback_version: int | None = None
    executed_at: AwareDatetime | None = None


class Simulation(Contract):
    proposal_id: str
    reviewed_payload_hash: str
    payload: ActionPayload
    state: ProposalState
    stale: bool
    before: Entity
    after: Entity
    will_execute: bool = False


class AuditEvent(Contract):
    tenant: str
    actor: str
    event: str
    reference: str
    payload_hash: str
    occurred_at: AwareDatetime


class AuditCheck(Contract):
    intact: bool
    event_count: int
    head_hash: str
    externally_anchored: bool = False
