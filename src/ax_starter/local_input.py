import os
import re
import stat
from pathlib import Path
from typing import Final

import typer
from pydantic import ValidationError

from ax_starter.common import AXError, Contract

MAX_INPUT_BYTES: Final = 1_048_576
DRIVE_PREFIX_LENGTH: Final = 2
_DEVICE_NAME: Final = re.compile(r"^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])$", re.IGNORECASE)


def _local_path_text(path: Path) -> None:
    value = str(path)
    if value.startswith(("\\\\", "//")):
        raise AXError("input_path_must_be_local", 422)
    if ":" in value:
        drive_rooted = (
            len(value) > DRIVE_PREFIX_LENGTH
            and value[0].isalpha()
            and value[1] == ":"
            and value[DRIVE_PREFIX_LENGTH] in "/\\"
        )
        if not drive_rooted or ":" in value[DRIVE_PREFIX_LENGTH:]:
            raise AXError("input_path_must_be_local", 422)
    if any(_DEVICE_NAME.fullmatch(part.split(".")[0]) for part in path.parts):
        raise AXError("input_path_must_be_local", 422)


def _no_reparse_path(path: Path) -> None:
    for component in (*reversed(path.parents), path):
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode) or (
            os.name == "nt" and info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise AXError("input_path_must_be_local", 422)


def checked_input_path(path: Path) -> Path:
    _local_path_text(path)
    root = Path(os.environ.get("AX_INPUT_ROOT") or Path.cwd())
    _local_path_text(root)
    absolute = Path(os.path.abspath(path))  # noqa: PTH100 - lexical check before any reparse resolution
    allowed = Path(os.path.abspath(root))  # noqa: PTH100 - lexical check before any reparse resolution
    if not absolute.is_relative_to(allowed):
        raise AXError("input_path_outside_root", 422)
    _no_reparse_path(absolute)
    resolved = absolute.resolve(strict=True)
    if not resolved.is_relative_to(allowed.resolve(strict=True)):
        raise AXError("input_path_outside_root", 422)
    return resolved


def _input_bytes(path: Path) -> bytes:
    source = checked_input_path(path)
    with source.open("rb") as stream:
        content = stream.read(MAX_INPUT_BYTES + 1)
    if len(content) > MAX_INPUT_BYTES:
        raise AXError("input_file_too_large", 422)
    return content


def read_input[ContractType: Contract](path: Path, contract: type[ContractType]) -> ContractType:
    try:
        return contract.model_validate_json(_input_bytes(path))
    except AXError as exc:
        typer.echo(exc.code, err=True)
        raise typer.Exit(code=1) from exc
    except (OSError, ValidationError) as exc:
        typer.echo("invalid_input_file", err=True)
        raise typer.Exit(code=1) from exc
