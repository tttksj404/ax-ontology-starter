from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from pydantic import ValidationError

from ax_starter.action_contracts import AuditEvent
from ax_starter.common import AXError, Operation, Principal, Purpose
from ax_starter.data_contracts import DataContract, DataContractRegistry
from ax_starter.knowledge_contracts import (
    DocumentLifecycle,
    KnowledgeMutationBatch,
    KnowledgeMutationReceipt,
    KnowledgeState,
    SourceSnapshotInput,
    mutation_batch_from_snapshot,
)
from ax_starter.knowledge_history import save_source_watermark, source_watermark
from ax_starter.knowledge_mutations import MutationContext, apply_mutation
from ax_starter.knowledge_store import (
    BatchKind,
    advance_state,
    save_batch,
    source_head,
    stored_batch,
    tenant_head,
)
from ax_starter.knowledge_visibility import document_metas, project_receipt, source_heads
from ax_starter.ontology import DomainPack
from ax_starter.policy import require
from ax_starter.retrieval import content_hash
from ax_starter.store import Store
from ax_starter.wiki_schema import invalidate_wiki_sources


@dataclass(frozen=True, slots=True)
class _BatchEnvelope:
    kind: BatchKind
    payload_sha256: str
    observed_at: datetime | None = None


class KnowledgeService:
    def __init__(
        self,
        store: Store,
        template: DomainPack,
        registry: DataContractRegistry,
        *,
        credential_guard: Callable[[], None] | None = None,
    ) -> None:
        self.store: Store = store
        self.template: DomainPack = template
        self.registry: DataContractRegistry = registry
        self.credential_guard: Callable[[], None] | None = credential_guard

    def apply(
        self, actor: Principal, batch: KnowledgeMutationBatch, now: datetime
    ) -> KnowledgeMutationReceipt:
        contract = self._authorize(actor, batch.contract_id)
        envelope = _BatchEnvelope(
            kind="apply", payload_sha256=content_hash(batch.model_dump_json())
        )
        return self._apply(actor, batch, now, contract, envelope)

    def import_snapshot(
        self, actor: Principal, snapshot: SourceSnapshotInput, now: datetime
    ) -> KnowledgeMutationReceipt:
        contract = self._authorize(actor, snapshot.contract_id)
        batch = mutation_batch_from_snapshot(snapshot)
        envelope = _BatchEnvelope(
            kind="import",
            payload_sha256=content_hash(snapshot.model_dump_json()),
            observed_at=snapshot.observed_at,
        )
        return self._apply(actor, batch, now, contract, envelope)

    def state(self, actor: Principal) -> KnowledgeState:
        if (
            Operation.READ not in actor.operations
            or Operation.MANAGE_KNOWLEDGE not in actor.operations
            or Purpose.AUDIT not in actor.purposes
        ):
            raise AXError("access_denied", 403)
        with self.store.transaction() as conn:
            self._guard_credentials()
            registry = self._current_registry()
            head = tenant_head(conn, actor.tenant)
            return KnowledgeState(
                tenant=actor.tenant,
                tenant_revision=head.revision,
                state_hash=head.state_hash,
                sources=source_heads(conn, actor, registry),
                documents=document_metas(conn, actor, registry),
            )

    def _authorize(self, actor: Principal, contract_id: str) -> DataContract:
        contract = self.registry.resolve(actor.tenant, contract_id)
        require(actor, contract.access, Purpose.AUDIT, Operation.MANAGE_KNOWLEDGE)
        return contract

    def _guard_credentials(self) -> None:
        if self.credential_guard is not None:
            self.credential_guard()

    def _current_registry(self) -> DataContractRegistry:
        if self.store.contract_resolver is None:
            return self.registry
        registry = self.store.contract_resolver()
        if registry is None:
            raise AXError("data_contract_registry_unavailable", 503)
        return registry

    def _live_contract(
        self, actor: Principal, expected: DataContract
    ) -> tuple[DataContract, DataContractRegistry]:
        registry = self._current_registry()
        live = next(
            (
                item
                for item in registry.contracts
                if item.tenant == actor.tenant and item.id == expected.id
            ),
            None,
        )
        if live is None or (
            live.version != expected.version
            or content_hash(live.model_dump_json()) != content_hash(expected.model_dump_json())
        ):
            raise AXError("data_contract_changed")
        require(actor, live.access, Purpose.AUDIT, Operation.MANAGE_KNOWLEDGE)
        return live, registry

    def _apply(
        self,
        actor: Principal,
        batch: KnowledgeMutationBatch,
        now: datetime,
        contract: DataContract,
        envelope: _BatchEnvelope,
    ) -> KnowledgeMutationReceipt:
        with self.store.transaction() as conn:
            self._guard_credentials()
            contract, registry = self._live_contract(actor, contract)
            source_identifier = contract.collection_source.identifier
            previous = stored_batch(
                conn, actor.tenant, batch.contract_id, envelope.kind, batch.request_key
            )
            if previous is not None:
                if previous.payload_sha256 != envelope.payload_sha256:
                    raise AXError("idempotency_conflict")
                return project_receipt(conn, previous.receipt, actor, contract)
            tenant_state = tenant_head(conn, actor.tenant)
            source_state = source_head(conn, actor.tenant, source_identifier)
            if envelope.observed_at is not None:
                _validate_snapshot_time(
                    contract,
                    now,
                    envelope.observed_at,
                    source_watermark(conn, actor.tenant, source_identifier),
                )
            if tenant_state.revision != batch.expected_tenant_revision:
                raise AXError("tenant_revision_conflict")
            if source_state.revision != batch.expected_source_revision:
                raise AXError("source_revision_conflict")
            context = MutationContext(
                conn=conn,
                template=self.template,
                contract=contract,
                actor=actor,
            )
            try:
                changed = tuple(apply_mutation(context, item) for item in batch.mutations)
                _ = self.store.current_pack(conn, self.template, registry=registry)
            except ValidationError as exc:
                raise AXError("document_domain_invalid", 422) from exc
            invalidate_wiki_sources(
                conn,
                actor.tenant,
                tuple(item.meta.document_id for item in changed),
                tuple(
                    item.meta.document_id
                    for item in changed
                    if item.meta.lifecycle is DocumentLifecycle.TOMBSTONE
                ),
                actor=actor.subject,
                now=now,
            )
            next_tenant, next_source = advance_state(
                conn, actor.tenant, source_identifier, envelope.payload_sha256
            )
            receipt = KnowledgeMutationReceipt(
                tenant=actor.tenant,
                contract_id=contract.id,
                request_key=batch.request_key,
                payload_sha256=envelope.payload_sha256,
                tenant_revision=next_tenant.revision,
                source_revision=next_source.revision,
                documents=tuple(item.meta for item in changed),
            )
            self.store.append_audit(
                conn,
                AuditEvent(
                    tenant=actor.tenant,
                    actor=actor.subject,
                    event="knowledge.batch_applied",
                    reference=f"{envelope.kind}:{contract.id}:{batch.request_key}",
                    payload_hash=envelope.payload_sha256,
                    occurred_at=now,
                ),
            )
            if envelope.observed_at is not None:
                save_source_watermark(conn, actor.tenant, source_identifier, envelope.observed_at)
            save_batch(conn, receipt, envelope.kind)
            return project_receipt(conn, receipt, actor, contract)


def _validate_snapshot_time(
    contract: DataContract,
    now: datetime,
    observed_at: datetime,
    last_observed_at: datetime | None,
) -> None:
    if observed_at > now:
        raise AXError("snapshot_observed_in_future", 422)
    if now - observed_at > timedelta(hours=contract.lifecycle.refresh_interval_hours):
        raise AXError("snapshot_stale", 422)
    if last_observed_at is not None and observed_at <= last_observed_at:
        raise AXError("snapshot_watermark_conflict")
