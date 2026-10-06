from typing import Final

from pydantic import JsonValue, TypeAdapter

from ax_starter.data_contracts import DataContractRegistry
from ax_starter.evidence_roles import DERIVED_WIKI_MARKER, EvidenceRole
from ax_starter.knowledge_contracts import KnowledgeDocumentMeta
from ax_starter.ontology import Document

_JSON_VALUE: Final = TypeAdapter[JsonValue](JsonValue)


def raw_source_allowed(
    meta: KnowledgeDocumentMeta, document: Document, registry: DataContractRegistry | None
) -> bool:
    """Exclude known derived outputs; this does not authenticate source identity or semantics."""
    if _known_wiki_export(document.text):
        return False
    if meta.contract_id is None or registry is None:
        return True
    return registry.evidence_role(meta.tenant, meta.contract_id) is EvidenceRole.RAW_SOURCE


def _known_wiki_export(text: str) -> bool:
    normalized = text.lstrip("\ufeff \t\r\n\v\f")
    if normalized.startswith(DERIVED_WIKI_MARKER):
        return True
    if not normalized.startswith("{"):
        return False
    try:
        wrapper = _JSON_VALUE.validate_json(normalized)
    except (ValueError, RecursionError):
        return False
    if not isinstance(wrapper, dict):
        return False
    exported_text = wrapper.get("text")
    return isinstance(exported_text, str) and exported_text.lstrip("\ufeff \t\r\n\v\f").startswith(
        DERIVED_WIKI_MARKER
    )
