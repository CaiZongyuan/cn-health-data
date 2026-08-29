"""Dataset contract discovery and loading."""

from pathlib import Path
from typing import Any, cast

import yaml


def find_repository_root(start: Path | None = None) -> Path:
    """Find the nearest parent containing the dataset and schema directories."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "datasets").is_dir() and (candidate / "schemas").is_dir():
            return candidate
    raise FileNotFoundError("could not find repository root containing datasets/ and schemas/")


def iter_dataset_contracts(repo_root: Path) -> tuple[Path, ...]:
    """Return dataset contracts in stable Dataset ID order."""
    return tuple(sorted((repo_root / "datasets").glob("*/dataset.yaml")))


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    """Load a YAML document and require an object at its root."""
    document: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path} must contain a YAML object")
    return cast(dict[str, Any], document)
