import hashlib
import secrets
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final, assert_never

from pydantic import Field, ValidationError, model_validator
from pydantic_core import PydanticCustomError

from ax_starter.common import ActorKind, AXError, Contract, Principal
from ax_starter.oidc import authenticate_oidc
from ax_starter.oidc_contracts import OIDCRegistry

MIN_CREDENTIAL_LENGTH: Final = 32
MAX_CREDENTIAL_LENGTH: Final = 512
JWT_SEPARATOR_COUNT: Final = 2


class AuthenticationMode(StrEnum):
    OPAQUE_ONLY = "opaque_only"
    JWT_ONLY = "jwt_only"
    BOTH = "both"


class IdentityBinding(Contract):
    token_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    principal: Principal


class IdentityRegistry(Contract):
    authentication_mode: AuthenticationMode = AuthenticationMode.OPAQUE_ONLY
    bindings: tuple[IdentityBinding, ...] = Field(default=(), max_length=100)
    oidc: OIDCRegistry | None = None

    @model_validator(mode="after")
    def unique_identities(self) -> "IdentityRegistry":
        digests = {item.token_sha256 for item in self.bindings}
        subjects = {(item.principal.tenant, item.principal.subject) for item in self.bindings}
        if len(digests) != len(self.bindings) or len(subjects) != len(self.bindings):
            raise PydanticCustomError("duplicate_identity", "중복 credential 또는 subject")
        self._validate_authentication_mode()
        principals: dict[tuple[str, str], Principal] = {}
        people: dict[tuple[str, str], Principal] = {}
        for principal in self._all_principals():
            key = (principal.tenant, principal.subject)
            previous = principals.get(key)
            if previous is not None and previous != principal:
                raise PydanticCustomError("conflicting_principal", "서버 principal 권한 충돌")
            principals[key] = principal
            person_id = principal.effective_person_id
            if principal.actor_kind is ActorKind.HUMAN and person_id is not None:
                person_key = (principal.tenant, person_id)
                previous_person = people.get(person_key)
                if previous_person is not None and previous_person != principal:
                    raise PydanticCustomError(
                        "duplicate_human_person", "tenant/person has multiple active principals"
                    )
                people[person_key] = principal
        return self

    def authenticate(self, credential: str, *, now: datetime | None = None) -> Principal:
        match self.authentication_mode:
            case AuthenticationMode.OPAQUE_ONLY:
                return self._authenticate_opaque(credential)
            case AuthenticationMode.JWT_ONLY:
                return self._authenticate_jwt(credential, now)
            case AuthenticationMode.BOTH:
                if credential.count(".") == JWT_SEPARATOR_COUNT:
                    return self._authenticate_jwt(credential, now)
                return self._authenticate_opaque(credential)
            case unreachable:
                assert_never(unreachable)

    def _authenticate_opaque(self, credential: str) -> Principal:
        if MIN_CREDENTIAL_LENGTH <= len(credential) <= MAX_CREDENTIAL_LENGTH:
            digest = hashlib.sha256(credential.encode("utf-8")).hexdigest()
            principal = next(
                (
                    binding.principal
                    for binding in self.bindings
                    if secrets.compare_digest(binding.token_sha256, digest)
                ),
                None,
            )
            if principal is not None:
                return principal
        raise AXError("authentication_required", 401)

    def _authenticate_jwt(self, credential: str, now: datetime | None) -> Principal:
        if self.oidc is None:
            raise AXError("authentication_required", 401)
        return authenticate_oidc(self.oidc, credential, now or datetime.now(UTC))

    def _validate_authentication_mode(self) -> None:
        match self.authentication_mode:
            case AuthenticationMode.OPAQUE_ONLY:
                valid = bool(self.bindings) and self.oidc is None
            case AuthenticationMode.JWT_ONLY:
                valid = not self.bindings and self.oidc is not None
            case AuthenticationMode.BOTH:
                valid = bool(self.bindings) and self.oidc is not None
            case unreachable:
                assert_never(unreachable)
        if not valid:
            raise PydanticCustomError(
                "authentication_mode", "authentication mode must match configured mechanisms"
            )

    def principals(self) -> tuple[Principal, ...]:
        unique: dict[tuple[str, str], Principal] = {}
        for principal in self._all_principals():
            unique[(principal.tenant, principal.subject)] = principal
        return tuple(unique.values())

    def _all_principals(self) -> tuple[Principal, ...]:
        opaque = tuple(binding.principal for binding in self.bindings)
        oidc = (
            tuple(binding.principal for binding in self.oidc.bindings if binding.enabled)
            if self.oidc is not None
            else ()
        )
        return opaque + oidc


def read_identities(path: Path) -> IdentityRegistry:
    try:
        return IdentityRegistry.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as exc:
        raise AXError("identity_registry_unavailable", 503) from exc
