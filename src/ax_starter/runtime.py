import os
from pathlib import Path

from fastapi import FastAPI

from ax_starter.api import create_app
from ax_starter.auth import read_identities
from ax_starter.common import AXError
from ax_starter.contract_registry import read_contracts
from ax_starter.ontology import DomainPack
from ax_starter.providers import ProviderConfig


def load_app() -> FastAPI:
    auth_file = os.environ.get("AX_AUTH_FILE")
    pack_file = os.environ.get("AX_PACK_FILE")
    database_file = os.environ.get("AX_DB_FILE")
    if not auth_file or not pack_file or not database_file:
        raise AXError("runtime_configuration_required", 503)
    database = Path(database_file)
    if not database.is_absolute() or not database.parent.is_dir():
        raise AXError("runtime_configuration_required", 503)
    pack = DomainPack.model_validate_json(Path(pack_file).read_bytes())
    identities = read_identities(Path(auth_file))
    provider_file = os.environ.get("AX_PROVIDER_FILE")
    provider = (
        ProviderConfig.model_validate_json(Path(provider_file).read_bytes())
        if provider_file
        else ProviderConfig()
    )
    contract_file = os.environ.get("AX_DATA_CONTRACTS_FILE")
    contract_path = Path(contract_file) if contract_file else None
    contracts = read_contracts(contract_path) if contract_path else None
    return create_app(
        pack,
        database,
        identities,
        provider,
        identity_path=Path(auth_file),
        data_contracts=contracts,
        contract_path=contract_path,
    )
