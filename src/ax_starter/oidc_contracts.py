import base64
import binascii
from enum import StrEnum
from typing import Annotated, Final, Literal
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import Field, StringConstraints, field_validator, model_validator
from pydantic_core import PydanticCustomError

from ax_starter.common import ActorKind, Contract, Principal

Issuer = Annotated[str, StringConstraints(min_length=9, max_length=512)]
Audience = Annotated[str, StringConstraints(min_length=1, max_length=512)]
ExternalSubject = Annotated[str, StringConstraints(min_length=1, max_length=512)]
ClientId = Annotated[str, StringConstraints(min_length=1, max_length=512)]
KeyId = Annotated[str, StringConstraints(min_length=1, max_length=128)]
Base64UrlUInt = Annotated[
    str, StringConstraints(min_length=1, max_length=2048, pattern=r"^[\w-]+$")
]
MIN_RSA_BITS: Final = 2048
MAX_RSA_BITS: Final = 8192
RSA_EXPONENT: Final = 65537


class OIDCSubjectKind(StrEnum):
    USER = "user"
    SERVICE = "service"


class RSAJWK(Contract):
    kty: Literal["RSA"]
    kid: KeyId
    n: Base64UrlUInt
    e: Base64UrlUInt
    use: Literal["sig"] = "sig"
    alg: Literal["RS256"] = "RS256"
    key_ops: tuple[Literal["verify"], ...] = Field(default=("verify",), min_length=1, max_length=1)


class JWKS(Contract):
    keys: tuple[RSAJWK, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def strong_unique_signing_keys(self) -> "JWKS":
        if len({key.kid for key in self.keys}) != len(self.keys):
            raise PydanticCustomError("duplicate_oidc_kid", "OIDC kid must be unique")
        for key in self.keys:
            modulus = _uint(key.n)
            exponent = _uint(key.e)
            if not MIN_RSA_BITS <= modulus.bit_length() <= MAX_RSA_BITS:
                raise PydanticCustomError(
                    "weak_oidc_key", "OIDC RSA key must be between 2048 and 8192 bits"
                )
            if exponent != RSA_EXPONENT:
                raise PydanticCustomError("invalid_oidc_key", "OIDC RSA exponent must be 65537")
            try:
                _ = rsa.RSAPublicNumbers(e=exponent, n=modulus).public_key()
            except ValueError as exc:
                raise PydanticCustomError("invalid_oidc_key", "OIDC RSA key is invalid") from exc
        return self


class OIDCIssuer(Contract):
    issuer: Issuer
    audience: Audience
    jwks: JWKS
    max_token_age: int = Field(default=3600, ge=1, le=86400)
    max_lifetime: int = Field(default=3600, ge=1, le=86400)

    @field_validator("issuer")
    @classmethod
    def trusted_https_issuer(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise PydanticCustomError(
                "invalid_oidc_issuer", "OIDC issuer must be a trusted HTTPS URL"
            )
        return value


class OIDCIdentityBinding(Contract):
    issuer: Issuer
    subject: ExternalSubject
    subject_kind: OIDCSubjectKind
    allowed_client_ids: tuple[ClientId, ...] = Field(min_length=1, max_length=20)
    principal: Principal
    enabled: bool = True

    @model_validator(mode="after")
    def server_owned_subject_kind(self) -> "OIDCIdentityBinding":
        if len(set(self.allowed_client_ids)) != len(self.allowed_client_ids):
            raise PydanticCustomError(
                "duplicate_client_id", "allowed client_id values must be unique"
            )
        expected_actor = (
            ActorKind.HUMAN if self.subject_kind is OIDCSubjectKind.USER else ActorKind.SERVICE
        )
        if self.principal.actor_kind is not expected_actor:
            raise PydanticCustomError(
                "oidc_binding_kind", "OIDC binding kind must match server principal kind"
            )
        if self.subject_kind is OIDCSubjectKind.SERVICE and self.allowed_client_ids != (
            self.subject,
        ):
            raise PydanticCustomError(
                "service_client_id", "service binding client_id must equal subject"
            )
        return self


class OIDCRegistry(Contract):
    issuers: tuple[OIDCIssuer, ...] = Field(min_length=1, max_length=10)
    bindings: tuple[OIDCIdentityBinding, ...] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def trusted_unique_bindings(self) -> "OIDCRegistry":
        trusted = {item.issuer for item in self.issuers}
        if len(trusted) != len(self.issuers):
            raise PydanticCustomError("duplicate_oidc_issuer", "OIDC issuer must be unique")
        identities = {(item.issuer, item.subject) for item in self.bindings}
        if len(identities) != len(self.bindings):
            raise PydanticCustomError("duplicate_oidc_identity", "OIDC identity must be unique")
        if any(item.issuer not in trusted for item in self.bindings):
            raise PydanticCustomError(
                "untrusted_oidc_binding", "OIDC binding issuer is not trusted"
            )
        return self


def _uint(value: str) -> int:
    try:
        encoded = value.encode("ascii")
        padding = b"=" * (-len(encoded) % 4)
        raw = base64.b64decode(encoded + padding, altchars=b"-_", validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise PydanticCustomError("invalid_oidc_key", "OIDC RSA key is invalid") from exc
    return int.from_bytes(raw, "big")
