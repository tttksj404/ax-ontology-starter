import base64
import binascii
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, ClassVar, Final, Literal, final

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    TypeAdapter,
    ValidationError,
)

from ax_starter.common import AXError, Contract
from ax_starter.oidc_contracts import RSAJWK, OIDCIssuer, OIDCRegistry

MAX_JWT_LENGTH: Final = 8192
ALLOWED_TOKEN_TYPES: Final = frozenset({"at+jwt", "application/at+jwt"})
JWT_SEPARATOR_COUNT: Final = 2
ClaimText = Annotated[str, StringConstraints(min_length=1, max_length=512)]
NumericDate = Annotated[StrictInt, Field(ge=0, le=253_402_300_799)]
_STRING_ADAPTER = TypeAdapter(str)


class AccessTokenHeader(Contract):
    alg: Literal["RS256"]
    kid: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    typ: ClaimText


class AccessTokenClaims(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore", strict=True)

    iss: ClaimText
    aud: ClaimText
    sub: ClaimText
    client_id: ClaimText
    jti: ClaimText
    exp: NumericDate
    iat: NumericDate
    nbf: NumericDate | None = None


@dataclass(frozen=True, slots=True)
class VerifiedSubject:
    issuer: str
    subject: str
    client_id: str


def verify_access_token(token: str, registry: OIDCRegistry, now: datetime) -> VerifiedSubject:
    if (
        len(token) > MAX_JWT_LENGTH
        or token.count(".") != JWT_SEPARATOR_COUNT
        or now.utcoffset() is None
    ):
        raise AXError("authentication_required", 401)
    try:
        header_part, claims_part, _signature = token.split(".")
        header_json = _decode_segment(header_part)
        claims_json = _decode_segment(claims_part)
        header = AccessTokenHeader.model_validate_json(header_json)
        claims = AccessTokenClaims.model_validate_json(claims_json)
        _reject_duplicate_json_keys(header_json)
        _reject_duplicate_json_keys(claims_json)
    except ValidationError as exc:
        raise AXError("authentication_required", 401) from exc
    if header.typ.casefold() not in ALLOWED_TOKEN_TYPES:
        raise AXError("authentication_required", 401)
    issuer = next((item for item in registry.issuers if item.issuer == claims.iss), None)
    if issuer is None:
        raise AXError("authentication_required", 401)
    key = next((item for item in issuer.jwks.keys if item.kid == header.kid), None)
    if key is None:
        raise AXError("authentication_required", 401)
    _verify_signature_and_registered_claims(token, issuer, key)
    current = now.timestamp()
    if (
        claims.aud != issuer.audience
        or claims.exp <= current
        or claims.iat > current
        or current - claims.iat > issuer.max_token_age
        or claims.exp <= claims.iat
        or claims.exp - claims.iat > issuer.max_lifetime
        or (claims.nbf is not None and claims.nbf > current)
    ):
        raise AXError("authentication_required", 401)
    return VerifiedSubject(issuer=claims.iss, subject=claims.sub, client_id=claims.client_id)


def _verify_signature_and_registered_claims(token: str, issuer: OIDCIssuer, key: RSAJWK) -> None:
    public_key = rsa.RSAPublicNumbers(e=_uint(key.e), n=_uint(key.n)).public_key()
    try:
        _ = bool(
            jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience=issuer.audience,
                issuer=issuer.issuer,
                options={
                    "require": ["iss", "aud", "sub", "client_id", "jti", "exp", "iat"],
                    "verify_exp": False,
                    "verify_iat": False,
                    "verify_nbf": False,
                    "strict_aud": True,
                },
            )
        )
    except jwt.PyJWTError as exc:
        raise AXError("authentication_required", 401) from exc


def _decode_segment(segment: str) -> bytes:
    try:
        encoded = segment.encode("ascii")
        padding = b"=" * (-len(encoded) % 4)
        return base64.b64decode(encoded + padding, altchars=b"-_", validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise AXError("authentication_required", 401) from exc


def _uint(value: str) -> int:
    return int.from_bytes(_decode_segment(value), "big")


def _reject_duplicate_json_keys(document: bytes) -> None:
    try:
        _JSONKeyScanner(document.decode("utf-8")).scan()
    except (UnicodeDecodeError, ValueError) as exc:
        raise AXError("authentication_required", 401) from exc


@final
class _JSONKeyScanner:
    __slots__ = ("index", "text")

    def __init__(self, text: str) -> None:
        self.text = text
        self.index = 0

    def scan(self) -> None:
        self._value()

    def _value(self) -> None:
        self._space()
        current = self.text[self.index]
        if current == "{":
            self._object()
        elif current == "[":
            self._array()
        elif current == '"':
            self._string()
        else:
            self._literal()
        self._space()

    def _object(self) -> None:
        self.index += 1
        keys: set[str] = set()
        self._space()
        while self.text[self.index] != "}":
            start = self.index
            self._string()
            key = _STRING_ADAPTER.validate_json(self.text[start : self.index])
            if key in keys:
                raise ValueError(key)
            keys.add(key)
            self._space()
            self.index += 1
            self._value()
            if self.text[self.index] != ",":
                break
            self.index += 1
            self._space()
        self.index += 1

    def _array(self) -> None:
        self.index += 1
        self._space()
        while self.text[self.index] != "]":
            self._value()
            if self.text[self.index] != ",":
                break
            self.index += 1
        self.index += 1

    def _string(self) -> None:
        self.index += 1
        while self.text[self.index] != '"':
            self.index += 2 if self.text[self.index] == "\\" else 1
        self.index += 1

    def _literal(self) -> None:
        start = self.index
        while self.index < len(self.text) and self.text[self.index] not in ",]}":
            self.index += 1
        if self.text[start : self.index].strip() in {"NaN", "Infinity", "-Infinity"}:
            raise ValueError

    def _space(self) -> None:
        while self.index < len(self.text) and self.text[self.index].isspace():
            self.index += 1
