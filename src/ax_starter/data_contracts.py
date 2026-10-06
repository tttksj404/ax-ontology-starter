import re
from enum import StrEnum
from hashlib import sha256
from typing import Annotated, Final, Literal, Self
from urllib.parse import parse_qsl, unquote_plus, urlsplit

from pydantic import AfterValidator, Field, StringConstraints, field_serializer, model_validator
from pydantic_core import PydanticCustomError

from ax_starter.common import Access, AXError, Contract, Identifier, Sensitivity
from ax_starter.evidence_roles import EvidenceRole, EvidenceRoleEntry

_AUTH_QUERY_PARTS: Final = frozenset(
    {
        "access",
        "auth",
        "authorization",
        "credential",
        "key",
        "password",
        "secret",
        "sig",
        "signature",
        "token",
    }
)


def _source_uri_without_auth(value: str) -> str:
    try:
        parsed = urlsplit(value)
        query_names = tuple(name for name, _ in parse_qsl(parsed.query, keep_blank_values=True))
    except ValueError as exc:
        raise PydanticCustomError("source_uri_invalid", "source URI is invalid") from exc
    if parsed.username is not None or parsed.password is not None:
        raise PydanticCustomError(
            "source_uri_contains_auth",
            "source URI must not contain authentication material",
        )
    for name in query_names:
        decoded = unquote_plus(unquote_plus(name)).casefold()
        parts = frozenset(part for part in re.split(r"[^a-z0-9]+", decoded) if part)
        if parts & _AUTH_QUERY_PARTS:
            raise PydanticCustomError(
                "source_uri_contains_auth",
                "source URI must not contain authentication material",
            )
    return value


Sha256Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
SourceUri = Annotated[
    str,
    StringConstraints(min_length=4, max_length=2048, pattern=r"^[a-z][a-z0-9+.-]*://.+$"),
    AfterValidator(_source_uri_without_auth),
]


class ReconciliationAction(StrEnum):
    QUARANTINE = "quarantine"
    REJECT = "reject"
    REQUIRE_REVIEW = "require_review"


class DataViolation(StrEnum):
    TENANT_MISMATCH = "tenant_mismatch"
    ORIGIN_MISMATCH = "origin_mismatch"
    SCOPE_NOT_ALLOWED = "scope_not_allowed"
    ACCESS_TENANT_MISMATCH = "access_tenant_mismatch"
    SENSITIVITY_UNDERCLASSIFIED = "sensitivity_underclassified"
    SENSITIVITY_EXCEEDED = "sensitivity_exceeded"
    GROUP_NOT_ALLOWED = "group_not_allowed"
    PURPOSE_NOT_ALLOWED = "purpose_not_allowed"
    CONTENT_HASH_MISMATCH = "content_hash_mismatch"
    EXPECTED_HASH_MISMATCH = "expected_hash_mismatch"
    PROVENANCE_MISSING = "provenance_missing"
    PROVENANCE_HASH_MISMATCH = "provenance_hash_mismatch"


class SourceReference(Contract):
    identifier: Identifier
    uri: SourceUri


class DeletionPolicy(Contract):
    retention_days: int = Field(ge=0, le=36_500)
    delete_within_hours: int = Field(ge=1, le=8_760)
    propagate_source_deletion: bool


class ReconciliationPolicy(Contract):
    interval_hours: int = Field(ge=1, le=8_760)
    action: ReconciliationAction


class LifecyclePolicy(Contract):
    refresh_interval_hours: int = Field(ge=1, le=8_760)
    deletion: DeletionPolicy
    reconciliation: ReconciliationPolicy


class ProvenanceClaim(Contract):
    source_identifier: Identifier
    record_identifier: Identifier
    content_sha256: Sha256Digest


class DataContract(Contract):
    id: Identifier
    version: Identifier
    tenant: Identifier
    owner: Identifier
    collection_source: SourceReference
    object_scope: tuple[Identifier, ...] = Field(min_length=1, max_length=100)
    access: Access
    minimum_sensitivity: Sensitivity | None = None
    lifecycle: LifecyclePolicy
    expected_content_sha256: Sha256Digest | None = None
    required_provenance: frozenset[Identifier] = Field(min_length=1, max_length=30)

    @field_serializer("required_provenance")
    def stable_required_provenance(self, members: frozenset[str]) -> tuple[str, ...]:
        return tuple(sorted(members))

    @model_validator(mode="after")
    def access_policy_must_be_consistent(self) -> Self:
        if self.access.tenant != self.tenant:
            raise PydanticCustomError("access_tenant_mismatch", "access tenant must match contract")
        if self.effective_minimum_sensitivity > self.access.sensitivity:
            raise PydanticCustomError(
                "invalid_sensitivity_range",
                "minimum sensitivity exceeds contract access ceiling",
            )
        return self

    @property
    def effective_minimum_sensitivity(self) -> Sensitivity:
        if self.minimum_sensitivity is None:
            return self.access.sensitivity
        return self.minimum_sensitivity


class DataContractRegistry(Contract):
    contracts: tuple[DataContract, ...] = Field(min_length=1, max_length=1_000)
    evidence_roles: tuple[EvidenceRoleEntry, ...] = Field(default=(), max_length=1_000)

    @model_validator(mode="after")
    def tenant_contract_ids_must_be_unique(self) -> Self:
        keys = {(contract.tenant, contract.id) for contract in self.contracts}
        if len(keys) != len(self.contracts):
            raise PydanticCustomError(
                "duplicate_data_contract",
                "duplicate tenant and contract id",
            )
        role_keys = {(entry.tenant, entry.contract_id) for entry in self.evidence_roles}
        if len(role_keys) != len(self.evidence_roles) or not role_keys <= keys:
            raise PydanticCustomError(
                "invalid_evidence_roles",
                "source roles must reference distinct registered contracts",
            )
        return self

    def evidence_role(self, tenant: str, contract_id: str) -> EvidenceRole:
        """Server registry owns source roles; omitted entries preserve v0.2 raw compatibility."""
        return next(
            (
                entry.role
                for entry in self.evidence_roles
                if entry.tenant == tenant and entry.contract_id == contract_id
            ),
            EvidenceRole.RAW_SOURCE,
        )

    def resolve(self, tenant: str, contract_id: str) -> DataContract:
        contract = next(
            (
                candidate
                for candidate in self.contracts
                if candidate.tenant == tenant and candidate.id == contract_id
            ),
            None,
        )
        if contract is None:
            raise AXError("data_contract_not_found", status=404)
        return contract


class DocumentCandidate(Contract):
    document_id: Identifier
    tenant: Identifier
    origin: SourceReference
    source_version: Identifier
    object_scope: tuple[Identifier, ...] = Field(min_length=1, max_length=100)
    access: Access
    content: bytes = Field(min_length=1, max_length=10_000_000)
    declared_sha256: Sha256Digest
    provenance: tuple[ProvenanceClaim, ...] = Field(min_length=1, max_length=100)


class DocumentValidation(Contract):
    accepted: bool
    violations: tuple[DataViolation, ...]
    computed_sha256: Sha256Digest
    origin_authenticated: Literal[False] = False
    provenance_authenticated: Literal[False] = False


def validate_document(contract: DataContract, document: DocumentCandidate) -> DocumentValidation:
    computed = sha256(document.content).hexdigest()
    checks = (
        (document.tenant != contract.tenant, DataViolation.TENANT_MISMATCH),
        (document.origin != contract.collection_source, DataViolation.ORIGIN_MISMATCH),
        (
            not set(document.object_scope) <= set(contract.object_scope),
            DataViolation.SCOPE_NOT_ALLOWED,
        ),
        (document.access.tenant != contract.tenant, DataViolation.ACCESS_TENANT_MISMATCH),
        (
            document.access.sensitivity < contract.effective_minimum_sensitivity,
            DataViolation.SENSITIVITY_UNDERCLASSIFIED,
        ),
        (
            document.access.sensitivity > contract.access.sensitivity,
            DataViolation.SENSITIVITY_EXCEEDED,
        ),
        (not document.access.groups <= contract.access.groups, DataViolation.GROUP_NOT_ALLOWED),
        (
            not document.access.purposes <= contract.access.purposes,
            DataViolation.PURPOSE_NOT_ALLOWED,
        ),
        (document.declared_sha256 != computed, DataViolation.CONTENT_HASH_MISMATCH),
        (
            contract.expected_content_sha256 is not None
            and contract.expected_content_sha256 != computed,
            DataViolation.EXPECTED_HASH_MISMATCH,
        ),
    )
    violations = [violation for failed, violation in checks if failed]
    for required_source in sorted(contract.required_provenance):
        claims = tuple(
            claim for claim in document.provenance if claim.source_identifier == required_source
        )
        if not claims:
            violations.append(DataViolation.PROVENANCE_MISSING)
        elif any(claim.content_sha256 != computed for claim in claims):
            violations.append(DataViolation.PROVENANCE_HASH_MISMATCH)
    return DocumentValidation(
        accepted=not violations,
        violations=tuple(violations),
        computed_sha256=computed,
    )
