"""Exercise write ACL and contract-drift cleanup over installed-wheel HTTP."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx2 as httpx
import typer

from ax_starter.api import create_app
from ax_starter.auth import IdentityBinding, IdentityRegistry
from ax_starter.common import Principal, Sensitivity
from ax_starter.data_contracts import DataContractRegistry
from ax_starter.demo import demo_pack
from ax_starter.knowledge_contracts import (
    ChangeDocumentAccess,
    DocumentLifecycle,
    KnowledgeMutation,
    KnowledgeMutationBatch,
    KnowledgeMutationReceipt,
    KnowledgeState,
    RetireDocument,
    TombstoneDocument,
    UpsertDocument,
)
from tests.knowledge_fixtures import candidate, management_actor, registry, upsert_batch
from tests.live_server import live_server


def actor(group: str) -> Principal:
    return management_actor().model_copy(
        update={"subject": group + "-manager", "groups": frozenset({group})}
    )


def headers(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token, "Content-Type": "application/json"}


def state(client: httpx.Client, token: str) -> KnowledgeState:
    response = client.get("/v1/knowledge/state", headers=headers(token))
    assert response.status_code == httpx.codes.OK
    assert token not in response.text
    return KnowledgeState.model_validate_json(response.content)


def verify_namespace_rejection(
    client: httpx.Client, token: str, batch: KnowledgeMutationBatch
) -> None:
    before = state(client, token)
    invalid_ids = (
        demo_pack().documents[0].id,
        "unknown-legacy-id",
        "beta.private-doc",
        "acme.nested.document",
    )
    for index, document_id in enumerate(invalid_ids):
        for empty_groups in (False, True):
            proposed = candidate(document_id=document_id)
            if empty_groups:
                proposed = proposed.model_copy(
                    update={
                        "access": proposed.access.model_copy(update={"groups": frozenset[str]()})
                    }
                )
            rejected = batch.model_copy(
                update={
                    "request_key": f"smoke-namespace-{index}-{empty_groups}",
                    "expected_tenant_revision": before.tenant_revision,
                    "expected_source_revision": 1,
                    "mutations": (
                        UpsertDocument(
                            candidate=proposed,
                            title="Rejected namespace",
                            valid_until=datetime.now(UTC) + timedelta(days=30),
                        ),
                    ),
                }
            )
            response = client.post(
                "/v1/knowledge/apply", headers=headers(token), content=rejected.model_dump_json()
            )
            assert response.status_code == httpx.codes.UNPROCESSABLE_CONTENT
            assert response.json() == {"error": "data_contract_violation"}
            assert state(client, token) == before


def verify_hardening_runtime() -> None:
    now = datetime.now(UTC)
    tokens = {group: secrets.token_urlsafe(32) for group in ("private", "procurement")}
    identities = IdentityRegistry(
        bindings=tuple(
            IdentityBinding(
                token_sha256=hashlib.sha256(token.encode()).hexdigest(), principal=actor(group)
            )
            for group, token in tokens.items()
        )
    )
    contracts = registry()
    private_access = candidate().access.model_copy(
        update={"groups": frozenset({"private"}), "sensitivity": Sensitivity.RESTRICTED}
    )
    private_candidate = candidate().model_copy(update={"access": private_access})
    initial_batch = upsert_batch(now + timedelta(days=30), document=private_candidate)
    with TemporaryDirectory(prefix="ax-hardening-wheel-") as directory:
        workspace = Path(directory)
        contract_path = workspace / "contracts.json"
        _ = contract_path.write_text(contracts.model_dump_json(), encoding="utf-8")
        application = create_app(
            demo_pack(),
            workspace / "state.db",
            identities,
            data_contracts=contracts,
            contract_path=contract_path,
            clock=lambda: now,
        )
        with (
            live_server(application) as endpoint,
            httpx.Client(base_url=endpoint, timeout=10, trust_env=False) as client,
        ):
            seeded = client.post(
                "/v1/knowledge/apply",
                headers=headers(tokens["private"]),
                content=initial_batch.model_dump_json(),
            )
            assert seeded.status_code == httpx.codes.OK
            accepted = KnowledgeMutationReceipt.model_validate_json(seeded.content)
            assert len(accepted.documents) == 1
            verify_namespace_rejection(client, tokens["private"], initial_batch)
            private_before = state(client, tokens["private"])
            empty_access = private_access.model_copy(update={"groups": frozenset()})
            empty_mutations: tuple[KnowledgeMutation, ...] = (
                ChangeDocumentAccess(
                    document_id=private_candidate.document_id, access=empty_access
                ),
                UpsertDocument(
                    candidate=candidate(document_id="acme.empty-group-doc").model_copy(
                        update={"access": empty_access}
                    ),
                    title="Deny-all candidate",
                    valid_until=now + timedelta(days=30),
                ),
            )
            for index, mutation in enumerate(empty_mutations):
                empty_batch = KnowledgeMutationBatch(
                    contract_id=initial_batch.contract_id,
                    request_key=f"smoke-empty-groups-{index}",
                    expected_tenant_revision=1,
                    expected_source_revision=1,
                    mutations=(mutation,),
                )
                empty_response = client.post(
                    "/v1/knowledge/apply",
                    headers=headers(tokens["private"]),
                    content=empty_batch.model_dump_json(),
                )
                assert empty_response.status_code == httpx.codes.UNPROCESSABLE_CONTENT
                assert state(client, tokens["private"]) == private_before
            before = state(client, tokens["procurement"])
            assert all(
                meta.document_id != private_candidate.document_id for meta in before.documents
            )
            denied_mutations: tuple[KnowledgeMutation, ...] = (
                UpsertDocument(
                    candidate=private_candidate.model_copy(update={"source_version": "2"}),
                    title="Private replacement",
                    valid_until=now + timedelta(days=30),
                ),
                ChangeDocumentAccess(
                    document_id=private_candidate.document_id, access=candidate().access
                ),
                RetireDocument(document_id=private_candidate.document_id),
                TombstoneDocument(document_id=private_candidate.document_id),
            )
            for index, mutation in enumerate(denied_mutations):
                batch = KnowledgeMutationBatch(
                    contract_id=initial_batch.contract_id,
                    request_key=f"smoke-denied-{index}",
                    expected_tenant_revision=1,
                    expected_source_revision=1,
                    mutations=(mutation,),
                )
                response = client.post(
                    "/v1/knowledge/apply",
                    headers=headers(tokens["procurement"]),
                    content=batch.model_dump_json(),
                )
                assert response.status_code == httpx.codes.NOT_FOUND
                assert state(client, tokens["procurement"]) == before
            replay = client.post(
                "/v1/knowledge/apply",
                headers=headers(tokens["procurement"]),
                content=initial_batch.model_dump_json(),
            )
            assert replay.status_code == httpx.codes.OK
            projected = KnowledgeMutationReceipt.model_validate_json(replay.content)
            assert projected.documents == ()
            assert projected.model_copy(update={"documents": accepted.documents}) == accepted
            upgraded = DataContractRegistry(
                contracts=(contracts.contracts[0].model_copy(update={"version": "2"}),)
            )
            _ = contract_path.write_text(upgraded.model_dump_json(), encoding="utf-8")
            assert all(
                meta.document_id != private_candidate.document_id
                for meta in state(client, tokens["private"]).documents
            )
            cleanup = KnowledgeMutationBatch(
                contract_id=initial_batch.contract_id,
                request_key="smoke-drift-cleanup",
                expected_tenant_revision=1,
                expected_source_revision=1,
                mutations=(TombstoneDocument(document_id=private_candidate.document_id),),
            )
            deleted = client.post(
                "/v1/knowledge/apply",
                headers=headers(tokens["private"]),
                content=cleanup.model_dump_json(),
            )
            assert deleted.status_code == httpx.codes.OK
            tombstone = KnowledgeMutationReceipt.model_validate_json(deleted.content).documents[0]
            assert tombstone.lifecycle == DocumentLifecycle.TOMBSTONE
            assert tombstone.contract_version == "2"
            assert tombstone.source_version == "1"
            assert state(client, tokens["private"]).tenant_revision == 2
    typer.echo("V02_HARDENING_SMOKE_PASSED write_acl_namespace_replay_drift_cleanup=verified")


if __name__ == "__main__":
    verify_hardening_runtime()
