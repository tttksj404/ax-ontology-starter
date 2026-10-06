from enum import StrEnum
from typing import Final

from ax_starter.common import Contract, Identifier

DERIVED_WIKI_MARKER: Final = "AX_DERIVED_WIKI_V1"


class EvidenceRole(StrEnum):
    RAW_SOURCE = "raw_source"
    DERIVED_OUTPUT = "derived_output"


class EvidenceRoleEntry(Contract):
    tenant: Identifier
    contract_id: Identifier
    role: EvidenceRole
