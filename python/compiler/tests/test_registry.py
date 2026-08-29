import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cn_health_compiler.core.registry import build_signed_registry, generate_signing_keypair
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_build_signed_registry_includes_only_eligible_release(tmp_path: Path) -> None:
    private_key = tmp_path / "registry.key"
    public_key = tmp_path / "registry.pub"
    registry_path = tmp_path / "registry.json"
    signature_path = tmp_path / "registry.json.sig"
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "release": {
                    "id": "example@2026.r1",
                    "sequence": 1,
                    "storageKey": "2026.r1",
                    "buildRevision": 1,
                    "revoked": False,
                },
                "dataset": {"id": "example", "sourceVersion": "2026"},
                "rights": {"releaseEligible": True},
            }
        ),
        encoding="utf-8",
    )
    generate_signing_keypair(private_key, public_key)

    registry = build_signed_registry(
        [manifest_path],
        registry_path=registry_path,
        signature_path=signature_path,
        private_key_path=private_key,
        schema_path=REPO_ROOT / "schemas/registry.schema.json",
        manifest_base_url="https://data.example/releases",
        created_at=datetime(2026, 8, 29, tzinfo=UTC),
    )

    assert registry["datasets"]["example"]["recommendedRelease"] == "example@2026.r1"
    release = registry["datasets"]["example"]["releases"][0]
    assert release["manifestUrl"] == "https://data.example/releases/example/2026.r1/manifest.json"
    public = Ed25519PublicKey.from_public_bytes(public_key.read_bytes())
    public.verify(signature_path.read_bytes(), registry_path.read_bytes())
    assert len(registry["signature"]["keyId"]) == 16


def test_registry_rejects_data_without_release_rights(tmp_path: Path) -> None:
    private_key = tmp_path / "registry.key"
    public_key = tmp_path / "registry.pub"
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "release": {
                    "id": "private@1.r1",
                    "sequence": 1,
                    "storageKey": "1.r1",
                    "buildRevision": 1,
                    "revoked": False,
                },
                "dataset": {"id": "private", "sourceVersion": "1"},
                "rights": {"releaseEligible": False},
            }
        ),
        encoding="utf-8",
    )
    generate_signing_keypair(private_key, public_key)

    with pytest.raises(ValueError, match="not release-eligible"):
        build_signed_registry(
            [manifest],
            registry_path=tmp_path / "registry.json",
            signature_path=tmp_path / "registry.json.sig",
            private_key_path=private_key,
            schema_path=REPO_ROOT / "schemas/registry.schema.json",
            manifest_base_url="https://data.example/releases",
        )
