from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from ax_starter.action_contracts import Proposal, ProposalState
from ax_starter.api import create_app
from ax_starter.api_contracts import ApprovalRequest
from ax_starter.auth import AuthenticationMode, IdentityRegistry
from ax_starter.common import Principal
from ax_starter.ontology import DomainPack
from ax_starter.store import Store
from tests.oidc_fixtures import registry as oidc_registry
from tests.oidc_fixtures import signing_key
from tests.test_actions import request
from tests.test_api import headers, registry


def test_revoked_request_credential_blocks_write_even_when_other_binding_keeps_person(
    tmp_path: Path,
    pack: DomainPack,
    principals: tuple[Principal, ...],
    now: datetime,
) -> None:
    # Given
    key = signing_key()
    original = IdentityRegistry(
        authentication_mode=AuthenticationMode.BOTH,
        bindings=registry(principals).bindings,
        oidc=oidc_registry(principals[1], (key.public_jwk,)).oidc,
    )
    identity_path = tmp_path / "identities.json"
    _ = identity_path.write_text(original.model_dump_json(), encoding="utf-8")
    database = tmp_path / "state.db"
    armed = False
    calls = 0

    def clock() -> datetime:
        nonlocal calls
        if armed:
            calls += 1
            if calls == 2:
                changed = original.model_copy(
                    update={
                        "bindings": tuple(
                            binding
                            for binding in original.bindings
                            if binding.principal.subject != "reviewer"
                        )
                    }
                )
                _ = identity_path.write_text(changed.model_dump_json(), encoding="utf-8")
        return now

    client = TestClient(
        create_app(pack, database, original, identity_path=identity_path, clock=clock),
        base_url="http://127.0.0.1",
    )
    proposed = client.post(
        "/v1/actions/propose", content=request().model_dump_json(), headers=headers(0)
    )
    proposal = Proposal.model_validate_json(proposed.content)
    armed = True
    # When
    response = client.post(
        f"/v1/actions/{proposal.id}/approve",
        content=ApprovalRequest(reviewed_payload_hash=proposal.payload_hash).model_dump_json(),
        headers=headers(1),
    )
    # Then
    assert response.status_code == 401
    assert response.json() == {"error": "authentication_required"}
    store = Store(database, pack)
    with store.transaction() as conn:
        assert store.proposal(conn, proposal.id).state == ProposalState.PROPOSED
        assert store.audit_check(conn, "acme").event_count == 1
