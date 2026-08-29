"""Signed public Dataset Registry construction."""

import hashlib
import json
import os
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, cast

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jsonschema import Draft202012Validator, FormatChecker

from cn_health_compiler.core.manifest import write_json_atomic
from cn_health_compiler.core.source import hash_file


def generate_signing_keypair(private_path: Path, public_path: Path) -> str:
    """Generate raw Ed25519 key files and return the stable key ID."""
    if private_path.exists() or public_path.exists():
        raise FileExistsError("refusing to overwrite an existing Registry key")
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    _write_bytes_atomic(private_path, private_bytes, mode=0o600)
    _write_bytes_atomic(public_path, public_bytes, mode=0o644)
    return _key_id(public_bytes)


def build_signed_registry(
    manifest_paths: list[Path],
    *,
    registry_path: Path,
    signature_path: Path,
    private_key_path: Path,
    schema_path: Path,
    manifest_base_url: str,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Build and sign a Registry from release-eligible immutable Manifests."""
    if not manifest_paths:
        raise ValueError("at least one Manifest is required")
    private_key = Ed25519PrivateKey.from_private_bytes(private_key_path.read_bytes())
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    base_url = manifest_base_url.rstrip("/")
    for manifest_path in manifest_paths:
        manifest = cast(dict[str, Any], json.loads(manifest_path.read_text(encoding="utf-8")))
        rights = cast(dict[str, Any], manifest["rights"])
        if rights.get("releaseEligible") is not True:
            raise ValueError(f"Manifest is not release-eligible: {manifest_path}")
        dataset = cast(dict[str, Any], manifest["dataset"])
        release = cast(dict[str, Any], manifest["release"])
        manifest_sha256, _ = hash_file(manifest_path)
        dataset_id = str(dataset["id"])
        storage_key = str(release["storageKey"])
        grouped[dataset_id].append(
            {
                "id": str(release["id"]),
                "sequence": int(release["sequence"]),
                "storageKey": storage_key,
                "sourceVersion": str(dataset["sourceVersion"]),
                "buildRevision": int(release["buildRevision"]),
                "manifestUrl": f"{base_url}/{dataset_id}/{storage_key}/manifest.json",
                "manifestSha256": manifest_sha256,
                "revoked": bool(release["revoked"]),
            }
        )

    datasets: dict[str, Any] = {}
    for dataset_id, releases in sorted(grouped.items()):
        releases.sort(key=lambda release: int(release["sequence"]))
        recommended = next(
            (release["id"] for release in reversed(releases) if not release["revoked"]),
            None,
        )
        datasets[dataset_id] = {
            "recommendedRelease": recommended,
            "releases": releases,
        }
    timestamp = created_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise ValueError("created_at must be timezone-aware")
    registry = {
        "schemaVersion": 1,
        "generatedAt": timestamp.astimezone(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "datasets": datasets,
        "signature": {
            "algorithm": "Ed25519",
            "keyId": _key_id(public_bytes),
            "url": signature_path.name,
        },
    }
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(registry)
    write_json_atomic(registry_path, registry)
    _write_bytes_atomic(signature_path, private_key.sign(registry_path.read_bytes()), mode=0o644)
    return registry


def _key_id(public_bytes: bytes) -> str:
    return hashlib.sha256(public_bytes).hexdigest()[:16]


def _write_bytes_atomic(path: Path, payload: bytes, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}-", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
