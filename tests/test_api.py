import hashlib
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ax_starter.action_contracts import Proposal
from ax_starter.api import ApprovalRequest, create_app
from ax_starter.auth import IdentityBinding, IdentityRegistry
from ax_starter.common import Principal
from ax_starter.demo import demo_pack
from ax_starter.retrieval import Answer
from tests.test_actions import request


def token(index: int) -> str:
    return f"synthetic-test-credential-role-{index:04d}"


def registry(principals: tuple[Principal, ...]) -> IdentityRegistry:
    return IdentityRegistry(
        bindings=tuple(
            IdentityBinding(
                token_sha256=hashlib.sha256(token(index).encode()).hexdigest(), principal=principal
            )
            for index, principal in enumerate(principals)
        )
    )


def headers(index: int) -> dict[str, str]:
    return {"Authorization": "Bearer " + token(index), "Content-Type": "application/json"}


@pytest.fixture
def client(tmp_path: Path, principals: tuple[Principal, ...], now: datetime) -> TestClient:
    return TestClient(
        create_app(demo_pack(), tmp_path / "state.db", registry(principals), clock=lambda: now),
        base_url="http://127.0.0.1",
    )


def test_http_flow_when_authorized_operator_and_reviewer(client: TestClient) -> None:
    # Given
    proposal = Proposal.model_validate_json(
        client.post(
            "/v1/actions/propose", content=request().model_dump_json(), headers=headers(0)
        ).content
    )
    approved = client.post(
        f"/v1/actions/{proposal.id}/approve",
        content=ApprovalRequest(reviewed_payload_hash=proposal.payload_hash).model_dump_json(),
        headers=headers(1),
    )
    assert approved.status_code == 200
    # When
    response = client.post(f"/v1/actions/{proposal.id}/execute", headers=headers(0))
    # Then
    assert response.status_code == 200
    assert Proposal.model_validate_json(response.content).result_version == 2


def test_authentication_when_no_credential(client: TestClient) -> None:
    # Given / When
    response = client.post("/v1/ask", json={"question": "검토 절차"})
    # Then
    assert response.status_code == 401


def test_role_forgery_when_request_body_claims_admin(client: TestClient) -> None:
    # Given / When
    response = client.post(
        "/v1/ask",
        json={"question": "검토 절차", "groups": ["private-board"], "clearance": 3},
        headers=headers(0),
    )
    # Then
    assert response.status_code == 422


def test_tenant_isolation_when_foreign_and_missing_ids(client: TestClient) -> None:
    # Given / When
    responses = tuple(
        client.post("/v1/ask", json={"question": "検討", "object_id": key}, headers=headers(0))
        for key in ("beta-request", "missing")
    )
    # Then
    assert responses[0].status_code == responses[1].status_code == 404
    assert responses[0].content == responses[1].content


def test_body_limit_when_content_length_is_false(client: TestClient) -> None:
    # Given / When
    response = client.post(
        "/v1/ask", content=b"x" * 130_000, headers={**headers(0), "Content-Length": "1"}
    )
    # Then
    assert response.status_code == 413


def test_hidden_docs_when_asking_unscoped(client: TestClient) -> None:
    # Given / When
    response = client.post("/v1/ask", json={"question": "검토 절차"}, headers=headers(0))
    # Then
    assert response.status_code == 200
    assert tuple(
        cite.document_id for cite in Answer.model_validate_json(response.content).citations
    ) == ("sop-1",)


def test_revocation_when_registry_changes_before_execution(
    tmp_path: Path, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    path = tmp_path / "identities.json"
    identities = registry(principals)
    _ = path.write_text(identities.model_dump_json(), encoding="utf-8")
    with TestClient(
        create_app(
            demo_pack(), tmp_path / "state.db", identities, identity_path=path, clock=lambda: now
        ),
        base_url="http://127.0.0.1",
    ) as client:
        proposal = Proposal.model_validate_json(
            client.post(
                "/v1/actions/propose", content=request().model_dump_json(), headers=headers(0)
            ).content
        )
        _ = client.post(
            f"/v1/actions/{proposal.id}/approve",
            content=ApprovalRequest(reviewed_payload_hash=proposal.payload_hash).model_dump_json(),
            headers=headers(1),
        )
        revoked = identities.model_copy(
            update={"bindings": (identities.bindings[0], *identities.bindings[2:])}
        )
        _ = path.write_text(revoked.model_dump_json(), encoding="utf-8")
        # When
        response = client.post(f"/v1/actions/{proposal.id}/execute", headers=headers(0))
        # Then
        assert response.status_code == 403
