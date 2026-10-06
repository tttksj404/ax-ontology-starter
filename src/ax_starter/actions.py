from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from ax_starter.action_authorization import (
    AuthorizationContext,
    AuthorizationRequest,
    authorize,
    require_approver_binding,
    require_independent_human,
    require_proposer_binding,
)
from ax_starter.action_contracts import (
    AuditEvent,
    Proposal,
    ProposalState,
    ProposeRequest,
    Simulation,
)
from ax_starter.common import AXError, Operation, Principal
from ax_starter.ontology import DomainPack, Entity, PropertyValue
from ax_starter.policy import require
from ax_starter.proposal_builder import ProposalContext, create_proposal, verify_evidence
from ax_starter.store import Store

if TYPE_CHECKING:
    import sqlite3


def changed(entity: Entity, status: str) -> Entity:
    properties = tuple(
        PropertyValue(key=item.key, value=status if item.key == "status" else item.value)
        for item in entity.properties
    )
    return entity.model_copy(update={"properties": properties, "version": entity.version + 1})


class ActionEngine:
    def __init__(
        self,
        store: Store,
        pack: DomainPack,
        principals: tuple[Principal, ...],
        *,
        principal_resolver: Callable[[], tuple[Principal, ...]] | None = None,
    ) -> None:
        self.store: Store = store
        self.pack: DomainPack = pack
        self.principals: tuple[Principal, ...] = principals
        self.principal_resolver: Callable[[], tuple[Principal, ...]] = principal_resolver or (
            lambda: self.principals
        )

    def propose(self, actor: Principal, request: ProposeRequest, now: datetime) -> Proposal:
        return create_proposal(
            ProposalContext(self.store, self.pack, self.principal_resolver), actor, request, now
        )

    def approve(
        self, actor: Principal, key: str, now: datetime, reviewed_payload_hash: str
    ) -> Proposal:
        with self.store.transaction() as conn:
            directory = self.principal_resolver()
            authorized = authorize(
                AuthorizationContext(self.store, self.pack, conn, directory),
                AuthorizationRequest(key, actor, Operation.APPROVE, now),
            )
            proposal, entity, current, pack = (
                authorized.proposal,
                authorized.entity,
                authorized.actor,
                authorized.pack,
            )
            if proposal.state in (ProposalState.EXECUTED, ProposalState.ROLLED_BACK):
                raise AXError("proposal_state_conflict")
            proposer = next(
                (
                    item
                    for item in directory
                    if item.tenant == current.tenant and item.subject == proposal.payload.proposer
                ),
                None,
            )
            if proposer is None:
                raise AXError("proposer_revoked", 403)
            require_proposer_binding(proposal.payload, proposer)
            require_independent_human(current, proposer)
            require(proposer, entity.access, proposal.payload.purpose, Operation.PROPOSE)
            verify_evidence(pack, proposer, proposal.payload, now)
            if reviewed_payload_hash != proposal.payload_hash:
                raise AXError("reviewed_hash_mismatch")
            verify_evidence(pack, current, proposal.payload, now)
            if entity.version != proposal.payload.expected_version:
                raise AXError("stale_object_version")
            if proposal.state == ProposalState.APPROVED and proposal.approver == current.subject:
                require_approver_binding(proposal, current)
                return proposal
            if proposal.state != ProposalState.PROPOSED:
                raise AXError("proposal_state_conflict")
            approved = proposal.model_copy(
                update={
                    "state": ProposalState.APPROVED,
                    "approver": actor.subject,
                    "approver_actor_kind": current.actor_kind,
                    "approver_person_id": current.effective_person_id,
                    "approval_hash": proposal.payload_hash,
                }
            )
            self.store.save_proposal(conn, approved)
            self._audit(conn, actor, "action.approved", approved, now)
            return approved

    def simulate(self, actor: Principal, key: str, now: datetime) -> Simulation:
        with self.store.transaction() as conn:
            directory = self.principal_resolver()
            authorized = authorize(
                AuthorizationContext(self.store, self.pack, conn, directory),
                AuthorizationRequest(key, actor, Operation.READ, now),
            )
            proposal, entity, current, pack = (
                authorized.proposal,
                authorized.entity,
                authorized.actor,
                authorized.pack,
            )
            verify_evidence(pack, current, proposal.payload, now)
            return Simulation(
                proposal_id=key,
                reviewed_payload_hash=proposal.payload_hash,
                payload=proposal.payload,
                state=proposal.state,
                stale=(
                    entity.version != proposal.payload.expected_version
                    or entity.property("status") != proposal.payload.previous_status
                ),
                before=entity,
                after=changed(entity, proposal.payload.new_status),
            )

    def execute(self, actor: Principal, key: str, now: datetime) -> Proposal:
        with self.store.transaction() as conn:
            directory = self.principal_resolver()
            authorized = authorize(
                AuthorizationContext(self.store, self.pack, conn, directory),
                AuthorizationRequest(key, actor, Operation.EXECUTE, now),
            )
            proposal, entity, current, pack = (
                authorized.proposal,
                authorized.entity,
                authorized.actor,
                authorized.pack,
            )
            if proposal.state == ProposalState.EXECUTED:
                return proposal
            if proposal.state == ProposalState.ROLLED_BACK:
                raise AXError("proposal_state_conflict")
            if (
                proposal.state != ProposalState.APPROVED
                or proposal.approval_hash != proposal.payload_hash
                or proposal.approver == proposal.payload.proposer
            ):
                raise AXError("independent_approval_required", 403)
            verify_evidence(pack, current, proposal.payload, now)
            approver = next(
                (
                    item
                    for item in directory
                    if item.subject == proposal.approver and item.tenant == actor.tenant
                ),
                None,
            )
            if approver is None:
                raise AXError("approver_revoked", 403)
            require_approver_binding(proposal, approver)
            require(approver, entity.access, proposal.payload.purpose, Operation.APPROVE)
            verify_evidence(pack, approver, proposal.payload, now)
            proposer = next(
                (
                    item
                    for item in directory
                    if item.subject == proposal.payload.proposer and item.tenant == actor.tenant
                ),
                None,
            )
            if proposer is None:
                raise AXError("proposer_revoked", 403)
            require_proposer_binding(proposal.payload, proposer)
            require_independent_human(approver, proposer)
            require(proposer, entity.access, proposal.payload.purpose, Operation.PROPOSE)
            verify_evidence(pack, proposer, proposal.payload, now)
            if (
                entity.version != proposal.payload.expected_version
                or entity.property("status") != proposal.payload.previous_status
            ):
                raise AXError("stale_object_version")
            updated = changed(entity, proposal.payload.new_status)
            executed = proposal.model_copy(
                update={
                    "state": ProposalState.EXECUTED,
                    "result_version": updated.version,
                    "executed_at": now,
                }
            )
            self.store.save_entity(conn, updated)
            self.store.save_proposal(conn, executed)
            self._audit(conn, actor, "action.executed", executed, now)
            return executed

    def rollback(self, actor: Principal, key: str, now: datetime) -> Proposal:
        with self.store.transaction() as conn:
            directory = self.principal_resolver()
            authorized = authorize(
                AuthorizationContext(self.store, self.pack, conn, directory),
                AuthorizationRequest(key, actor, Operation.ROLLBACK, now),
            )
            proposal, entity = authorized.proposal, authorized.entity
            if proposal.state == ProposalState.ROLLED_BACK:
                return proposal
            if proposal.state != ProposalState.EXECUTED:
                raise AXError("proposal_state_conflict")
            if proposal.executed_at is None or now > proposal.executed_at + timedelta(hours=24):
                raise AXError("rollback_window_expired")
            if (
                entity.version != proposal.result_version
                or entity.property("status") != proposal.payload.new_status
            ):
                raise AXError("rollback_would_overwrite_newer_change")
            updated = changed(entity, proposal.payload.previous_status)
            rolled = proposal.model_copy(
                update={"state": ProposalState.ROLLED_BACK, "rollback_version": updated.version}
            )
            self.store.save_entity(conn, updated)
            self.store.save_proposal(conn, rolled)
            self._audit(conn, actor, "action.rolled_back", rolled, now)
            return rolled

    def _audit(
        self,
        conn: "sqlite3.Connection",
        actor: Principal,
        event: str,
        proposal: Proposal,
        now: datetime,
    ) -> None:
        self.store.append_audit(
            conn,
            AuditEvent(
                tenant=actor.tenant,
                actor=actor.subject,
                event=event,
                reference=proposal.id,
                payload_hash=proposal.payload_hash,
                occurred_at=now,
            ),
        )
