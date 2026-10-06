from pathlib import Path

from pydantic import ValidationError

from ax_starter.common import AXError
from ax_starter.data_contracts import DataContractRegistry


def read_contracts(path: Path) -> DataContractRegistry:
    """Read operator-managed source policies; fail closed on missing or invalid policy."""
    try:
        return DataContractRegistry.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as exc:
        raise AXError("data_contract_registry_unavailable", 503) from exc
