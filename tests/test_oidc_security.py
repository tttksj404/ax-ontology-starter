import base64
from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from ax_starter.auth import IdentityRegistry
from ax_starter.common import AXError, Principal
from ax_starter.oidc_contracts import JWKS, RSAJWK, OIDCIssuer, OIDCRegistry
from tests.oidc_fixtures import (
    AUDIENCE,
    ISSUER,
    RegistrySpec,
    TokenSpec,
    access_token,
    hs256_token,
    raw_access_token,
    registry,
    signing_key,
)


def test_signature_forgery_is_rejected(principals: tuple[Principal, ...], now: datetime) -> None:
    # Given
    trusted = signing_key()
    attacker = signing_key()
    identities = registry(principals[0], (trusted.public_jwk,))
    forged = access_token(attacker.private, now)
    # When / Then
    with pytest.raises(AXError, match="authentication_required"):
        _ = identities.authenticate(forged, now=now)


def test_non_rs256_algorithm_is_rejected(principals: tuple[Principal, ...], now: datetime) -> None:
    # Given
    trusted = signing_key()
    identities = registry(principals[0], (trusted.public_jwk,))
    # When / Then
    with pytest.raises(AXError, match="authentication_required"):
        _ = identities.authenticate(hs256_token(now), now=now)


@pytest.mark.parametrize(
    "header",
    [
        {"jku": "https://attacker.example/jwks.json"},
        {"x5u": "https://attacker.example/cert.pem"},
        {"jwk": {"kty": "oct", "k": "attacker"}},
        {"crit": ["jku"], "jku": "https://attacker.example/jwks.json"},
        {"x5c": ["attacker-certificate"]},
        {"cty": "JWT"},
        {"zip": "DEF"},
        {"b64": False},
    ],
)
def test_attacker_key_headers_cannot_change_key_selection(
    header: dict[str, str | bool | list[str] | dict[str, str]],
    principals: tuple[Principal, ...],
    now: datetime,
) -> None:
    # Given
    key = signing_key()
    identities = registry(principals[0], (key.public_jwk,))
    token = access_token(key.private, now, TokenSpec(extra_headers=header))
    # When / Then
    with pytest.raises(AXError, match="authentication_required"):
        _ = identities.authenticate(token, now=now)


def test_unregistered_and_disabled_subjects_are_rejected(
    principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    key = signing_key()
    unregistered = access_token(key.private, now, TokenSpec(subject="other-subject"))
    disabled = registry(principals[0], (key.public_jwk,), RegistrySpec(enabled=False))
    # When / Then
    with pytest.raises(AXError, match="authentication_required"):
        _ = disabled.authenticate(unregistered, now=now)
    with pytest.raises(AXError, match="authentication_required"):
        _ = disabled.authenticate(access_token(key.private, now), now=now)


def test_oidc_configuration_requires_https_unique_issuer_and_strong_unique_keys() -> None:
    # Given
    key = signing_key()
    weak = signing_key("weak", bits=1024)
    # When / Then
    with pytest.raises(ValidationError):
        _ = OIDCIssuer(
            issuer="http://issuer.example.test",
            audience=AUDIENCE,
            jwks=JWKS(keys=(key.public_jwk,)),
        )
    with pytest.raises(ValidationError):
        _ = OIDCIssuer(issuer=ISSUER, audience=AUDIENCE, jwks=JWKS(keys=(weak.public_jwk,)))
    with pytest.raises(ValidationError):
        _ = OIDCIssuer(
            issuer=ISSUER,
            audience=AUDIENCE,
            jwks=JWKS(keys=(key.public_jwk, key.public_jwk)),
        )


@pytest.mark.parametrize("member", ["d", "x5c", "unregistered"])
def test_pinned_jwk_rejects_nonstandard_exponent_oversize_and_private_members(
    member: str,
) -> None:
    exponent_three = signing_key("exponent-three", exponent=3)
    oversize = signing_key().public_jwk.model_copy(
        update={"kid": "oversize", "n": _uint64((1 << 8192) | 1)}
    )

    with pytest.raises(ValidationError, match="exponent"):
        _ = JWKS(keys=(exponent_three.public_jwk,))
    with pytest.raises(ValidationError, match="between 2048 and 8192"):
        _ = JWKS(keys=(oversize,))
    with pytest.raises(ValidationError):
        _ = RSAJWK.model_validate({**signing_key().public_jwk.model_dump(), member: "not-allowed"})


def test_registry_requires_every_binding_issuer_to_be_trusted(
    principals: tuple[Principal, ...],
) -> None:
    # Given
    key = signing_key()
    configured = registry(principals[0], (key.public_jwk,)).oidc
    assert configured is not None
    untrusted = configured.bindings[0].model_copy(update={"issuer": "https://other.example.test"})
    # When / Then
    with pytest.raises(ValidationError):
        _ = IdentityRegistry(
            bindings=(),
            oidc=OIDCRegistry(issuers=configured.issuers, bindings=(untrusted,)),
        )


def test_jwt_uses_separate_bounded_length_from_opaque_credentials(
    principals: tuple[Principal, ...], now: datetime
) -> None:
    # Given
    key = signing_key()
    identities = registry(principals[0], (key.public_jwk,))
    token = access_token(key.private, now, TokenSpec(extra_claims={"padding": "x" * 600}))
    assert len(token) > 512
    # When / Then
    assert identities.authenticate(token, now=now) == principals[0]
    with pytest.raises(AXError, match="authentication_required"):
        _ = identities.authenticate(f"{token}.{'x' * 9000}", now=now)


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("exp", 1.5),
        ("iat", True),
        ("nbf", "1"),
        ("iat", -1),
    ],
)
def test_numeric_dates_require_nonnegative_integers(
    claim: str,
    value: str | float | bool,
    principals: tuple[Principal, ...],
    now: datetime,
) -> None:
    key = signing_key()
    identities = registry(principals[0], (key.public_jwk,))
    token = access_token(key.private, now, TokenSpec(extra_claims={claim: value}))

    with pytest.raises(AXError, match="authentication_required"):
        _ = identities.authenticate(token, now=now)


def test_token_age_and_lifetime_are_bounded(
    principals: tuple[Principal, ...], now: datetime
) -> None:
    key = signing_key()
    identities = registry(
        principals[0],
        (key.public_jwk,),
        RegistrySpec(max_token_age=600, max_lifetime=900),
    )
    old = access_token(
        key.private,
        now,
        TokenSpec(issued_delta=timedelta(seconds=-601), expires_delta=timedelta(minutes=5)),
    )
    long_lived = access_token(
        key.private,
        now,
        TokenSpec(issued_delta=timedelta(), expires_delta=timedelta(seconds=901)),
    )

    for token in (old, long_lived):
        with pytest.raises(AXError, match="authentication_required"):
            _ = identities.authenticate(token, now=now)


def test_duplicate_json_keys_in_header_or_payload_are_rejected(
    principals: tuple[Principal, ...], now: datetime
) -> None:
    key = signing_key()
    identities = registry(principals[0], (key.public_jwk,))
    timestamp = int(now.timestamp())
    header = '{"alg":"RS256","kid":"key-a","kid":"key-a","typ":"at+jwt"}'
    claims = (
        f'{{"iss":"{ISSUER}","aud":"{AUDIENCE}","sub":"external-subject",'
        f'"client_id":"synthetic-client","jti":"id","exp":{timestamp + 300},'
        f'"iat":{timestamp}}}'
    )
    duplicate_claims = claims[:-1] + f',"aud":"{AUDIENCE}"}}'

    for token in (
        raw_access_token(key.private, header_json=header, claims_json=claims),
        raw_access_token(
            key.private,
            header_json='{"alg":"RS256","kid":"key-a","typ":"at+jwt"}',
            claims_json=duplicate_claims,
        ),
    ):
        with pytest.raises(AXError, match="authentication_required"):
            _ = identities.authenticate(token, now=now)


def _uint64(value: int) -> str:
    size = max(1, (value.bit_length() + 7) // 8)
    return base64.urlsafe_b64encode(value.to_bytes(size, "big")).rstrip(b"=").decode("ascii")
