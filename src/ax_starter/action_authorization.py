import sqlite3
from dataclasses import dataclass
from datetime import datetime

from ax_starter.action_contracts import ActionPayload, Proposal, ProposalState
from ax_starter.common import ActorKind, AXError, Operation, Principal
from ax_starter.ontology import DomainPack, Entity
from ax_starter.policy import require, visible
from ax_starter.store import Store


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    store: Store
    template: DomainPack
    conn: sqlite3.Connection
    directory: tuple[Principal, ...]


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    key: str
    actor: Principal
    operation: Operation
    now: datetime


@dataclass(frozen=True, slots=True)
class AuthorizedAction:
    proposal: Proposal
    entity: Entity
    actor: Principal
    pack: DomainPack


def require_independent_human(approver: Principal, proposer: Principal) -> None:
    if approver.actor_kind != ActorKind.HUMAN:
        raise AXError("human_approval_required", 403)
    if approver.subject == proposer.subject or (
        proposer.effective_person_id is not None
        and approver.effective_person_id == proposer.effective_person_id
    ):
        raise AXError("self_approval_forbidden", 403)


def require_proposer_binding(payload: ActionPayload, proposer: Principal) -> None:
    if payload.proposer_actor_kind is None:
        raise AXError("proposal_reproposal_required")
    if (
        payload.proposer_actor_kind != proposer.actor_kind
        or payload.proposer_person_id != proposer.effective_person_id
    ):
        raise AXError("principal_identity_changed", 403)


def require_approver_binding(proposal: Proposal, approver: Principal) -> None:
    if proposal.approver_actor_kind is None or proposal.approver_person_id is None:
        raise AXError("proposal_reapproval_required")
    if (
        proposal.approver_actor_kind != approver.actor_kind
        or proposal.approver_person_id != approver.effective_person_id
    ):
        raise AXError("principal_identity_changed", 403)


def authorize(context: AuthorizationContext, request: AuthorizationRequest) -> AuthorizedAction:
    proposal = context.store.proposal(context.conn, request.key)
    entity = context.store.entity(context.conn, proposal.payload.object_id)
    if request.actor.tenant != proposal.payload.tenant:
        raise AXError("proposal_not_found", 404)
    current = next(
        (
            item
            for item in context.directory
            if item.tenant == request.actor.tenant and item.subject == request.actor.subject
        ),
        None,
    )
    if current is None:
        raise AXError("actor_revoked", 403)
    if not visible(current, entity.access, proposal.payload.purpose):
        raise AXError("proposal_not_found", 404)
    require(current, entity.access, proposal.payload.purpose, request.operation)
    if proposal.payload.pack_hash != context.store.pack_hash:
        raise AXError("pack_version_changed")
    if (
        proposal.state in (ProposalState.PROPOSED, ProposalState.APPROVED)
        and request.now >= proposal.payload.expires_at
    ):
        raise AXError("proposal_expired")
    return AuthorizedAction(
        proposal=proposal,
        entity=entity,
        actor=current,
        pack=context.store.current_pack(context.conn, context.template),
    )
