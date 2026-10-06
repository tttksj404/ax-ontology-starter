import hashlib
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ax_starter.api import create_app
from ax_starter.auth import AuthenticationMode, IdentityBinding, IdentityRegistry, read_identities
from ax_starter.common import ActorKind, AXError, Principal
from ax_starter.demo import demo_pack
from tests.oidc_fixtures import (
    AUDIENCE,
    RegistrySpec,
    TokenSpec,
    access_token,
    registry,
    signing_key,
)


def test_rs256_access_token_maps_only_to_server_principal(
    principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    key = signing_key()
    identities = registry(principals[0], (key.public_jwk,))
    token = access_token(
        key.private,
        now,
        TokenSpec(
            extra_claims={
                "tenant": "forged-tenant",
                "groups": ["administrators"],
                "roles": ["owner"],
                "clearance": 3,
            }
        ),
    )
    # When
    authenticated = identities.authenticate(token, now=now)
    # Then
    assert authenticated == principals[0]


def test_application_typ_is_accepted_for_one_api_audience(
    principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    key = signing_key()
    identities = registry(principals[0], (key.public_jwk,))
    token = access_token(
        key.private,
        now,
        TokenSpec(typ="application/at+JWT"),
    )
    # When / Then
    assert identities.authenticate(token, now=now) == principals[0]


@pytest.mark.parametrize(
    "spec",
    [
        TokenSpec(audience="urn:other-api"),
        TokenSpec(issuer="https://untrusted.example.test"),
        TokenSpec(expires_delta=timedelta(seconds=-1)),
        TokenSpec(issued_delta=timedelta(seconds=1)),
        TokenSpec(not_before_delta=timedelta(seconds=1)),
        TokenSpec(typ="JWT"),
        TokenSpec(omit_claims=frozenset({"exp"})),
        TokenSpec(extra_claims={"aud": ["urn:secondary", AUDIENCE]}),
    ],
)
def test_access_token_is_rejected_when_claim_contract_fails(
    spec: TokenSpec, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    key = signing_key()
    identities = registry(principals[0], (key.public_jwk,))
    token = access_token(key.private, now, spec)
    # When / Then
    with pytest.raises(AXError, match="authentication_required"):
        _ = identities.authenticate(token, now=now)


def test_key_rotation_uses_only_current_pinned_jwks(
    principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    previous = signing_key("key-old")
    current = signing_key("key-new")
    rotating = registry(principals[0], (previous.public_jwk, current.public_jwk))
    old_token = access_token(previous.private, now, TokenSpec(kid="key-old"))
    new_token = access_token(current.private, now, TokenSpec(kid="key-new"))
    # When / Then
    assert rotating.authenticate(old_token, now=now) == principals[0]
    assert rotating.authenticate(new_token, now=now) == principals[0]
    after_rotation = registry(principals[0], (current.public_jwk,))
    with pytest.raises(AXError, match="authentication_required"):
        _ = after_rotation.authenticate(old_token, now=now)


def test_file_reload_revokes_disabled_oidc_binding(
    tmp_path: Path, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    key = signing_key()
    token = access_token(key.private, now)
    path = tmp_path / "identities.json"
    enabled = registry(principals[0], (key.public_jwk,))
    _ = path.write_text(enabled.model_dump_json(), encoding="utf-8")
    assert read_identities(path).authenticate(token, now=now) == principals[0]
    # When
    disabled = registry(principals[0], (key.public_jwk,), RegistrySpec(enabled=False))
    _ = path.write_text(disabled.model_dump_json(), encoding="utf-8")
    # Then
    assert read_identities(path).principals() == ()
    with pytest.raises(AXError, match="authentication_required"):
        _ = read_identities(path).authenticate(token, now=now)


def test_file_reload_fails_closed_after_removal_or_partial_write(
    tmp_path: Path, principals: tuple[Principal, ...], now: datetime
) -> None:
    key = signing_key()
    token = access_token(key.private, now)
    path = tmp_path / "identities.json"
    _ = path.write_text(registry(principals[0], (key.public_jwk,)).model_dump_json())
    assert read_identities(path).authenticate(token, now=now) == principals[0]

    path.unlink()
    with pytest.raises(AXError, match="identity_registry_unavailable"):
        _ = read_identities(path)

    _ = path.write_text('{"authentication_mode":"jwt_only","oidc":', encoding="utf-8")
    with pytest.raises(AXError, match="identity_registry_unavailable"):
        _ = read_identities(path)


def test_opaque_credential_remains_compatible_with_injected_time(
    principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    credential = "synthetic-test-credential-role-0000"
    identities = IdentityRegistry(
        bindings=(
            IdentityBinding(
                token_sha256=hashlib.sha256(credential.encode()).hexdigest(),
                principal=principals[0],
            ),
        )
    )
    # When / Then
    assert identities.authenticate(credential, now=now) == identities.bindings[0].principal


def test_both_mode_does_not_fallback_from_jwt_shape_to_opaque_hash(
    principals: tuple[Principal, ...], now: datetime
) -> None:
    credential = "header.payload.signature-padding-0000"
    jwt_registry = registry(principals[0], (signing_key().public_jwk,))
    identities = IdentityRegistry(
        authentication_mode=AuthenticationMode.BOTH,
        bindings=(
            IdentityBinding(
                token_sha256=hashlib.sha256(credential.encode()).hexdigest(),
                principal=principals[0],
            ),
        ),
        oidc=jwt_registry.oidc,
    )

    with pytest.raises(AXError, match="authentication_required"):
        _ = identities.authenticate(credential, now=now)


def test_same_server_principal_can_have_opaque_and_jwt_credentials(
    principals: tuple[Principal, ...],
) -> None:
    jwt_registry = registry(principals[0], (signing_key().public_jwk,))
    identities = IdentityRegistry(
        authentication_mode=AuthenticationMode.BOTH,
        bindings=(IdentityBinding(token_sha256="a" * 64, principal=principals[0]),),
        oidc=jwt_registry.oidc,
    )

    assert identities.principals() == (principals[0],)


def test_distinct_active_human_principals_cannot_share_tenant_person(
    principals: tuple[Principal, ...],
) -> None:
    first = principals[0].model_copy(update={"person_id": "person-1"})
    second = principals[1].model_copy(
        update={"actor_kind": ActorKind.HUMAN, "person_id": "person-1"}
    )
    jwt_registry = registry(second, (signing_key().public_jwk,))

    with pytest.raises(ValidationError, match="duplicate_human_person"):
        _ = IdentityRegistry(
            authentication_mode=AuthenticationMode.BOTH,
            bindings=(IdentityBinding(token_sha256="b" * 64, principal=first),),
            oidc=jwt_registry.oidc,
        )


def test_api_authentication_uses_injected_clock(
    tmp_path: Path, principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    key = signing_key()
    identities = registry(principals[0], (key.public_jwk,))
    token = access_token(key.private, now)
    app = create_app(demo_pack(), tmp_path / "state.db", identities, clock=lambda: now)
    # When
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.get("/v1/objects", headers={"Authorization": f"Bearer {token}"})
    # Then
    assert response.status_code == 200
