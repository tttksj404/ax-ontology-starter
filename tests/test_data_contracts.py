import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from ax_starter.common import Access, AXError, Purpose, Sensitivity
from ax_starter.data_contracts import (
    DataContract,
    DataContractRegistry,
    DataViolation,
    DeletionPolicy,
    DocumentCandidate,
    LifecyclePolicy,
    ProvenanceClaim,
    ReconciliationAction,
    ReconciliationPolicy,
    SourceReference,
    validate_document,
)

CONTENT = b'{"record":"synthetic"}'
_CONTRACT_DIGEST_SCRIPT = """
import hashlib
import json
from pathlib import Path

from ax_starter.data_contracts import DataContractRegistry

payload = json.loads(Path("examples/v0.2/data-contract-registry.json").read_text(encoding="utf-8"))
contract = payload["contracts"][0]
contract["required_provenance"] = ["zeta-source", "alpha-source", "mid-source"]
contract["access"]["groups"] = ["zeta-group", "alpha-group"]
contract["access"]["purposes"] = ["operations", "audit"]
registry = DataContractRegistry.model_validate(payload)
serialized = registry.resolve("synthetic-tenant", "support-record-v1").model_dump_json()
print(hashlib.sha256(serialized.encode()).hexdigest())
"""


def digest(content: bytes = CONTENT) -> str:
    return sha256(content).hexdigest()


def contract() -> DataContract:
    return DataContract(
        id="support-record-v1",
        version="1.0.0",
        tenant="synthetic-tenant",
        owner="data-owner",
        collection_source=SourceReference(
            identifier="synthetic-source", uri="memory://support-records"
        ),
        object_scope=("support-record",),
        access=Access(
            tenant="synthetic-tenant",
            groups=frozenset({"operators"}),
            sensitivity=Sensitivity.CONFIDENTIAL,
            purposes=frozenset({Purpose.OPERATIONS}),
        ),
        minimum_sensitivity=Sensitivity.INTERNAL,
        lifecycle=LifecyclePolicy(
            refresh_interval_hours=24,
            deletion=DeletionPolicy(
                retention_days=30,
                delete_within_hours=24,
                propagate_source_deletion=True,
            ),
            reconciliation=ReconciliationPolicy(
                interval_hours=24,
                action=ReconciliationAction.QUARANTINE,
            ),
        ),
        expected_content_sha256=digest(),
        required_provenance=frozenset({"synthetic-source"}),
    )


def document() -> DocumentCandidate:
    content_digest = digest()
    return DocumentCandidate(
        document_id="synthetic-tenant.support-record-1",
        tenant="synthetic-tenant",
        origin=SourceReference(identifier="synthetic-source", uri="memory://support-records"),
        source_version="source-v1",
        object_scope=("support-record",),
        access=Access(
            tenant="synthetic-tenant",
            groups=frozenset({"operators"}),
            sensitivity=Sensitivity.INTERNAL,
            purposes=frozenset({Purpose.OPERATIONS}),
        ),
        content=CONTENT,
        declared_sha256=content_digest,
        provenance=(
            ProvenanceClaim(
                source_identifier="synthetic-source",
                record_identifier="source-record-1",
                content_sha256=content_digest,
            ),
        ),
    )


def test_document_is_accepted_when_hash_provenance_and_access_match() -> None:
    # Given
    candidate = document()
    # When
    result = validate_document(contract(), candidate)
    # Then
    assert result.accepted
    assert result.violations == ()
    assert result.computed_sha256 == digest()
    assert result.origin_authenticated is False
    assert result.provenance_authenticated is False


def test_document_is_rejected_when_payload_and_provenance_are_tampered() -> None:
    # Given
    candidate = document().model_copy(update={"content": b"tampered"})
    # When
    result = validate_document(contract(), candidate)
    # Then
    assert result.accepted is False
    assert set(result.violations) == {
        DataViolation.CONTENT_HASH_MISMATCH,
        DataViolation.EXPECTED_HASH_MISMATCH,
        DataViolation.PROVENANCE_HASH_MISMATCH,
    }


def test_document_is_rejected_when_access_exceeds_contract_ceiling() -> None:
    # Given
    candidate = document().model_copy(
        update={
            "access": Access(
                tenant="synthetic-tenant",
                groups=frozenset({"outsiders"}),
                sensitivity=Sensitivity.RESTRICTED,
                purposes=frozenset({Purpose.AUDIT}),
            )
        }
    )
    # When
    result = validate_document(contract(), candidate)
    # Then
    assert set(result.violations) == {
        DataViolation.GROUP_NOT_ALLOWED,
        DataViolation.PURPOSE_NOT_ALLOWED,
        DataViolation.SENSITIVITY_EXCEEDED,
    }


def test_document_can_narrow_groups_and_purposes_without_broadening_access() -> None:
    # Given
    candidate = document().model_copy(
        update={
            "access": document().access.model_copy(
                update={"groups": frozenset(), "purposes": frozenset()}
            )
        }
    )
    # When
    result = validate_document(contract(), candidate)
    # Then
    assert result.accepted


def test_document_is_rejected_when_sensitivity_is_underclassified() -> None:
    # Given
    candidate = document().model_copy(
        update={"access": document().access.model_copy(update={"sensitivity": Sensitivity.PUBLIC})}
    )
    # When
    result = validate_document(contract(), candidate)
    # Then
    assert DataViolation.SENSITIVITY_UNDERCLASSIFIED in result.violations


def test_omitted_minimum_sensitivity_defaults_to_contract_access_level() -> None:
    # Given
    payload = contract().model_dump(exclude={"minimum_sensitivity"})
    conservative = DataContract.model_validate(payload)
    # When
    result = validate_document(conservative, document())
    # Then
    assert DataViolation.SENSITIVITY_UNDERCLASSIFIED in result.violations


def test_minimum_sensitivity_cannot_exceed_contract_access_ceiling() -> None:
    # Given
    payload = contract().model_dump()
    payload["minimum_sensitivity"] = Sensitivity.RESTRICTED
    # When / Then
    with pytest.raises(ValidationError, match="invalid_sensitivity_range"):
        _ = DataContract.model_validate(payload)


@pytest.mark.parametrize(
    "uri",
    [
        "https://user:password@example.invalid/records",
        "https://example.invalid/records?To%4Ben=secret",
        "https://example.invalid/records?api_key=secret",
        "https://example.invalid/records?X-Amz-%43redential=secret",
    ],
)
def test_source_uri_rejects_embedded_authentication_material(uri: str) -> None:
    # Given / When / Then
    with pytest.raises(ValidationError, match="source_uri_contains_auth"):
        _ = SourceReference(identifier="synthetic-source", uri=uri)


def test_source_uri_allows_non_secret_stable_query_identifiers() -> None:
    # Given / When
    source = SourceReference(
        identifier="synthetic-source",
        uri="https://example.invalid/records?version=1",
    )
    # Then
    assert source.uri.endswith("version=1")


def test_registry_resolves_only_the_registered_tenant_contract() -> None:
    # Given
    registry = DataContractRegistry(contracts=(contract(),))
    # When
    resolved = registry.resolve("synthetic-tenant", "support-record-v1")
    # Then
    assert resolved == contract()
    with pytest.raises(AXError, match="data_contract_not_found") as error:
        _ = registry.resolve("other-tenant", "support-record-v1")
    assert error.value.status == 404


def test_registry_rejects_duplicate_tenant_and_contract_id() -> None:
    # Given
    duplicate = contract().model_copy(update={"version": "2.0.0"})
    # When / Then
    with pytest.raises(ValidationError, match="duplicate_data_contract"):
        _ = DataContractRegistry(contracts=(contract(), duplicate))


def test_contract_binding_digest_is_stable_across_python_hash_seeds() -> None:
    # Given / When
    root = Path(__file__).parents[1]
    digests = {
        subprocess.run(  # noqa: S603
            [sys.executable, "-c", _CONTRACT_DIGEST_SCRIPT],
            cwd=root,
            env=os.environ | {"PYTHONHASHSEED": str(seed)},
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        for seed in range(1, 9)
    }
    # Then
    assert len(digests) == 1


def test_contract_json_sorts_provenance_and_nested_access_sets() -> None:
    # Given
    subject = contract().model_copy(
        update={
            "required_provenance": frozenset({"zeta-source", "alpha-source"}),
            "access": contract().access.model_copy(
                update={
                    "groups": frozenset({"zeta-group", "alpha-group"}),
                    "purposes": frozenset({Purpose.OPERATIONS, Purpose.AUDIT}),
                }
            ),
        }
    )
    # When
    serialized = subject.model_dump_json()
    # Then
    assert serialized.index('"alpha-source"') < serialized.index('"zeta-source"')
    assert serialized.index('"alpha-group"') < serialized.index('"zeta-group"')
    assert serialized.index('"audit"') < serialized.index('"operations"')


def test_synthetic_data_contract_example_validates_its_document() -> None:
    # Given
    root = Path(__file__).parents[1] / "examples" / "v0.2"
    registry = DataContractRegistry.model_validate_json(
        (root / "data-contract-registry.json").read_text(encoding="utf-8")
    )
    candidate = DocumentCandidate.model_validate_json(
        (root / "document-candidate.json").read_text(encoding="utf-8")
    )
    # When
    result = validate_document(
        registry.resolve(candidate.tenant, "support-record-v1"),
        candidate,
    )
    # Then
    assert result.accepted
    assert result.origin_authenticated is False
