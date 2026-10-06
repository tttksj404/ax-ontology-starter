import hashlib
from datetime import datetime

import pytest
from pydantic import ValidationError

from ax_starter.auth import AuthenticationMode, IdentityBinding, IdentityRegistry
from ax_starter.common import ActorKind, AXError, Principal
from ax_starter.oidc_contracts import OIDCSubjectKind
from tests.oidc_fixtures import RegistrySpec, TokenSpec, access_token, registry, signing_key


def test_user_binding_requires_distinct_subject_and_allowed_client(
    principals: tuple[Principal, ...], now: datetime
) -> None:
    key = signing_key()
    allowed = registry(principals[0], (key.public_jwk,))
    wrong_client = access_token(key.private, now, TokenSpec(client_id="other-client"))
    confused = registry(
        principals[0],
        (key.public_jwk,),
        RegistrySpec(allowed_client_ids=("external-subject",)),
    )
    subject_as_client = access_token(key.private, now, TokenSpec(client_id="external-subject"))

    with pytest.raises(AXError, match="authentication_required"):
        _ = allowed.authenticate(wrong_client, now=now)
    with pytest.raises(AXError, match="authentication_required"):
        _ = confused.authenticate(subject_as_client, now=now)


def test_service_binding_requires_subject_equal_client_and_service_principal(
    principals: tuple[Principal, ...], now: datetime
) -> None:
    key = signing_key()
    service = principals[0].model_copy(
        update={"subject": "server-service", "actor_kind": ActorKind.SERVICE}
    )
    identities = registry(
        service,
        (key.public_jwk,),
        RegistrySpec(
            subject_kind=OIDCSubjectKind.SERVICE,
            allowed_client_ids=("external-subject",),
        ),
    )
    token = access_token(key.private, now, TokenSpec(client_id="external-subject"))

    assert identities.authenticate(token, now=now) == service
    with pytest.raises(AXError, match="authentication_required"):
        _ = identities.authenticate(
            access_token(key.private, now, TokenSpec(client_id="synthetic-client")),
            now=now,
        )


def test_binding_kind_must_match_server_principal_kind(principals: tuple[Principal, ...]) -> None:
    key = signing_key()
    with pytest.raises(ValidationError, match="binding kind"):
        _ = registry(
            principals[0],
            (key.public_jwk,),
            RegistrySpec(
                subject_kind=OIDCSubjectKind.SERVICE,
                allowed_client_ids=("external-subject",),
            ),
        )


def test_service_principal_cannot_have_person_id(principals: tuple[Principal, ...]) -> None:
    with pytest.raises(ValidationError, match="service principal"):
        _ = Principal.model_validate(
            {
                **principals[0].model_dump(),
                "actor_kind": ActorKind.SERVICE,
                "person_id": "human-person",
            }
        )


def test_authentication_mode_rejects_missing_or_extra_mechanisms(
    principals: tuple[Principal, ...],
) -> None:
    opaque = IdentityBinding(token_sha256="c" * 64, principal=principals[0])
    configured_oidc = registry(principals[0], (signing_key().public_jwk,)).oidc
    assert configured_oidc is not None

    invalid = (
        {"authentication_mode": AuthenticationMode.OPAQUE_ONLY, "oidc": configured_oidc},
        {
            "authentication_mode": AuthenticationMode.JWT_ONLY,
            "bindings": (opaque,),
            "oidc": configured_oidc,
        },
        {"authentication_mode": AuthenticationMode.BOTH, "bindings": (opaque,)},
    )
    for values in invalid:
        with pytest.raises(ValidationError, match="authentication mode"):
            _ = IdentityRegistry.model_validate(values)


def test_default_mode_preserves_opaque_demo_credential(
    principals: tuple[Principal, ...], now: datetime
) -> None:
    credential = "opaque-demo-credential-synthetic-01"
    identities = IdentityRegistry(
        bindings=(
            IdentityBinding(
                token_sha256=hashlib.sha256(credential.encode()).hexdigest(),
                principal=principals[0],
            ),
        )
    )

    assert identities.authenticate(credential, now=now) == principals[0]
