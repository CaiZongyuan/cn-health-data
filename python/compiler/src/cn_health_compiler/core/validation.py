"""Machine-readable contract validation."""

import json
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker

from cn_health_compiler.core.dataset import iter_dataset_contracts, load_yaml_mapping


class ContractValidationError(ValueError):
    """Raised when a repository contract fails its JSON Schema."""


def _load_json_mapping(path: Path) -> dict[str, Any]:
    document: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return cast(dict[str, Any], document)


def validate_dataset_contracts(repo_root: Path) -> tuple[Path, ...]:
    """Validate all Dataset Contracts and return their paths in stable order."""
    schema_path = repo_root / "schemas" / "dataset.schema.json"
    schema = _load_json_mapping(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    contract_paths = iter_dataset_contracts(repo_root)
    if not contract_paths:
        raise ContractValidationError("no datasets/*/dataset.yaml contracts found")

    failures: list[str] = []
    for contract_path in contract_paths:
        contract = load_yaml_mapping(contract_path)
        dataset_id = contract.get("id")
        if dataset_id != contract_path.parent.name:
            failures.append(f"{contract_path}: id {dataset_id!r} does not match directory name")
        for error in sorted(validator.iter_errors(contract), key=lambda item: list(item.path)):
            failures.append(f"{contract_path} {error.json_path}: {error.message}")

    if failures:
        raise ContractValidationError("\n".join(failures))
    return contract_paths
