from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from ax_starter.action_authorization import require_proposer_binding
from ax_starter.action_contracts import (
    ActionPayload,
    AuditEvent,
    EvidenceRef,
    Proposal,
    ProposalState,
    ProposeRequest,
)
from ax_starter.common import AXError, Operation, Principal
from ax_starter.knowledge_store import access_hash
from ax_starter.ontology import DomainPack, Transition
from ax_starter.policy import require, visible
from ax_starter.retrieval import Query, content_hash, evidence_documents
from ax_starter.store import Store


@dataclass(frozen=True, slots=True)
class ProposalContext:
    store: Store
    template: DomainPack
    principal_resolver: Callable[[], tuple[Principal, ...]]


def create_proposal(
    context: ProposalContext,
    actor: Principal,
    request: ProposeRequest,
    now: datetime,
) -> Proposal:
    store, template = context.store, context.template
    with store.transaction() as conn:
        registered = next(
            (
                item
                for item in context.principal_resolver()
                if item.tenant == actor.tenant and item.subject == actor.subject
            ),
            None,
        )
        if registered != actor:
            raise AXError("actor_revoked", 403)
        pack = store.current_pack(conn, template)
        entity = store.entity(conn, request.object_id)
        if not visible(actor, entity.access, request.purpose):
            raise AXError("object_not_found", 404)
        require(actor, entity.access, request.purpose, Operation.PROPOSE)
        previous = store.by_request(conn, actor.tenant, actor.subject, request.request_key)
        if previous:
            if not previous.payload.evidence_refs and previous.state in (
                ProposalState.PROPOSED,
                ProposalState.APPROVED,
            ):
                raise AXError("proposal_reproposal_required")
            require_proposer_binding(previous.payload, actor)
            bound = previous.payload
            same = (
                bound.action_type,
                bound.object_id,
                bound.new_status,
                bound.expected_version,
                bound.evidence_ids,
                bound.purpose,
            ) == (
                request.action_type,
                request.object_id,
                request.new_status,
                request.expected_version,
                request.evidence_ids,
                request.purpose,
            )
            if not same:
                raise AXError("idempotency_conflict")
            return previous
        action = next((item for item in pack.action_types if item.id == request.action_type), None)
        if action is None or action.object_type != entity.type:
            raise AXError("action_not_allowed", 403)
        status = entity.property("status")
        if (
            type(status) is not str
            or Transition(before=status, after=request.new_status) not in action.transitions
        ):
            raise AXError("transition_not_allowed")
        documents = evidence_documents(
            pack,
            actor,
            Query(question="action evidence", object_id=entity.id, purpose=request.purpose),
            now,
        )
        doc_map = {doc.id: doc for doc in documents}
        if any(key not in doc_map for key in request.evidence_ids):
            raise AXError("evidence_not_available", 403)
        if entity.version != request.expected_version:
            raise AXError("stale_object_version")
        payload = ActionPayload(
            action_type=action.id,
            object_id=entity.id,
            tenant=actor.tenant,
            proposer=actor.subject,
            proposer_actor_kind=actor.actor_kind,
            proposer_person_id=actor.effective_person_id,
            previous_status=status,
            new_status=request.new_status,
            expected_version=entity.version,
            evidence_ids=request.evidence_ids,
            evidence_hashes=tuple(content_hash(doc_map[key].text) for key in request.evidence_ids),
            evidence_refs=tuple(
                EvidenceRef(
                    id=doc_map[key].id,
                    source_version=doc_map[key].source_version,
                    content_sha256=content_hash(doc_map[key].text),
                    access_hash=access_hash(doc_map[key].access),
                )
                for key in request.evidence_ids
            ),
            purpose=request.purpose,
            pack_hash=store.pack_hash,
            expires_at=now + timedelta(minutes=30),
        )
        proposal = Proposal(
            id=str(uuid4()),
            request_key=request.request_key,
            payload=payload,
            payload_hash=content_hash(payload.model_dump_json()),
            state=ProposalState.PROPOSED,
        )
        store.insert_proposal(conn, proposal)
        store.append_audit(
            conn,
            AuditEvent(
                tenant=actor.tenant,
                actor=actor.subject,
                event="action.proposed",
                reference=proposal.id,
                payload_hash=proposal.payload_hash,
                occurred_at=now,
            ),
        )
        return proposal


def verify_evidence(
    pack: DomainPack, actor: Principal, payload: ActionPayload, now: datetime
) -> None:
    if not payload.evidence_refs:
        raise AXError("proposal_reproposal_required")
    docs = evidence_documents(
        pack,
        actor,
        Query(question="action evidence", object_id=payload.object_id, purpose=payload.purpose),
        now,
    )
    current = {
        doc.id: EvidenceRef(
            id=doc.id,
            source_version=doc.source_version,
            content_sha256=content_hash(doc.text),
            access_hash=access_hash(doc.access),
        )
        for doc in docs
    }
    if any(current.get(reference.id) != reference for reference in payload.evidence_refs):
        raise AXError("evidence_changed_or_revoked", 403)
