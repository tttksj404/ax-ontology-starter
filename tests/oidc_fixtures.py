import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final

import jwt
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from jwt import PyJWT

from ax_starter.auth import AuthenticationMode, IdentityRegistry
from ax_starter.common import Principal
from ax_starter.oidc_contracts import (
    JWKS,
    RSAJWK,
    OIDCIdentityBinding,
    OIDCIssuer,
    OIDCRegistry,
    OIDCSubjectKind,
)

ISSUER = "https://issuer.example.test/tenant"
AUDIENCE = "urn:ax-ontology-starter"


@dataclass(frozen=True, slots=True)
class SigningKey:
    private: rsa.RSAPrivateKey
    public_jwk: RSAJWK


@dataclass(frozen=True, slots=True)
class RegistrySpec:
    enabled: bool = True
    subject_kind: OIDCSubjectKind = OIDCSubjectKind.USER
    allowed_client_ids: tuple[str, ...] = ("synthetic-client",)
    max_token_age: int = 3600
    max_lifetime: int = 3600


@dataclass(frozen=True, slots=True)
class TokenSpec:
    issuer: str = ISSUER
    audience: str = AUDIENCE
    subject: str = "external-subject"
    client_id: str = "synthetic-client"
    kid: str = "key-a"
    typ: str = "at+jwt"
    expires_delta: timedelta = timedelta(minutes=5)
    issued_delta: timedelta = timedelta()
    not_before_delta: timedelta | None = None
    extra_claims: dict[str, str | list[str] | int | float | bool | None] = field(
        default_factory=dict
    )
    extra_headers: dict[str, str | bool | list[str] | dict[str, str]] = field(default_factory=dict)
    omit_claims: frozenset[str] = frozenset()


DEFAULT_TOKEN_SPEC: Final = TokenSpec()
DEFAULT_REGISTRY_SPEC: Final = RegistrySpec()


def signing_key(kid: str = "key-a", *, bits: int = 2048, exponent: int = 65537) -> SigningKey:
    private = rsa.generate_private_key(public_exponent=exponent, key_size=bits)
    numbers = private.public_key().public_numbers()
    return SigningKey(
        private=private,
        public_jwk=RSAJWK(
            kid=kid,
            kty="RSA",
            use="sig",
            alg="RS256",
            n=_uint64(numbers.n),
            e=_uint64(numbers.e),
        ),
    )


def registry(
    principal: Principal,
    keys: tuple[RSAJWK, ...],
    spec: RegistrySpec = DEFAULT_REGISTRY_SPEC,
) -> IdentityRegistry:
    return IdentityRegistry(
        authentication_mode=AuthenticationMode.JWT_ONLY,
        bindings=(),
        oidc=OIDCRegistry(
            issuers=(
                OIDCIssuer(
                    issuer=ISSUER,
                    audience=AUDIENCE,
                    jwks=JWKS(keys=keys),
                    max_token_age=spec.max_token_age,
                    max_lifetime=spec.max_lifetime,
                ),
            ),
            bindings=(
                OIDCIdentityBinding(
                    issuer=ISSUER,
                    subject="external-subject",
                    subject_kind=spec.subject_kind,
                    allowed_client_ids=spec.allowed_client_ids,
                    principal=principal,
                    enabled=spec.enabled,
                ),
            ),
        ),
    )


def access_token(
    key: rsa.RSAPrivateKey, now: datetime, spec: TokenSpec = DEFAULT_TOKEN_SPEC
) -> str:
    claims: dict[str, str | list[str] | int | float | bool | None] = {
        "iss": spec.issuer,
        "aud": spec.audience,
        "sub": spec.subject,
        "client_id": spec.client_id,
        "jti": "synthetic-token-id",
        "exp": int((now + spec.expires_delta).timestamp()),
        "iat": int((now + spec.issued_delta).timestamp()),
        **spec.extra_claims,
    }
    if spec.not_before_delta is not None:
        claims["nbf"] = int((now + spec.not_before_delta).timestamp())
    for claim in spec.omit_claims:
        _ = claims.pop(claim, None)
    headers: dict[str, str | bool | list[str] | dict[str, str]] = {
        "kid": spec.kid,
        "typ": spec.typ,
        **spec.extra_headers,
    }
    return PyJWT().encode(claims, key, algorithm="RS256", headers=headers)


def raw_access_token(key: rsa.RSAPrivateKey, *, header_json: str, claims_json: str) -> str:
    header = _segment(header_json.encode("utf-8"))
    claims = _segment(claims_json.encode("utf-8"))
    signing_input = f"{header}.{claims}".encode("ascii")
    signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{claims}.{_segment(signature)}"


def hs256_token(now: datetime) -> str:
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "external-subject",
        "client_id": "synthetic-client",
        "jti": "synthetic-token-id",
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "iat": int(now.timestamp()),
    }
    return jwt.encode(
        claims,
        "synthetic-secret-long-enough-for-test-only",
        algorithm="HS256",
        headers={"kid": "key-a", "typ": "at+jwt"},
    )


def _uint64(value: int) -> str:
    size = max(1, (value.bit_length() + 7) // 8)
    return base64.urlsafe_b64encode(value.to_bytes(size, "big")).rstrip(b"=").decode("ascii")


def _segment(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")
