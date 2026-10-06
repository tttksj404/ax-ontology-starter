from ax_starter.data_contracts import DataContractRegistry
from ax_starter.knowledge_contracts import KnowledgeDocumentMeta
from ax_starter.retrieval import content_hash


def binding_is_current(meta: KnowledgeDocumentMeta, registry: DataContractRegistry | None) -> bool:
    if meta.contract_id is None:
        return (
            meta.contract_version is None
            and meta.contract_sha256 is None
            and meta.source_identifier == f"bootstrap.{meta.document_id}"
        )
    if registry is None or meta.contract_version is None or meta.contract_sha256 is None:
        return False
    contract = next(
        (
            item
            for item in registry.contracts
            if item.tenant == meta.tenant and item.id == meta.contract_id
        ),
        None,
    )
    return (
        contract is not None
        and contract.version == meta.contract_version
        and contract.collection_source.identifier == meta.source_identifier
        and content_hash(contract.model_dump_json()) == meta.contract_sha256
    )
