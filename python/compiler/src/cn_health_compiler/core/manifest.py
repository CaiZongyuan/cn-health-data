"""Manifest serialization and validation helpers."""

import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from jsonschema import Draft202012Validator, FormatChecker

MANIFEST_SCHEMA_VERSION = 1


def write_json_atomic(path: Path, value: object) -> tuple[str, int]:
    """Atomically write deterministic JSON and return its SHA256 and size."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}-",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        return hashlib.sha256(payload).hexdigest(), len(payload)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def validate_manifest(manifest: object, schema_path: Path) -> None:
    """Validate a release manifest at the publication trust boundary."""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(manifest)
