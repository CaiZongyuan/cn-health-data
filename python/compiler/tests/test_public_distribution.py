import hashlib
import json
import sqlite3
from pathlib import Path

import zstandard
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

REPO_ROOT = Path(__file__).resolve().parents[3]
PUBLIC_ORIGIN = "https://raw.githubusercontent.com/CaiZongyuan/cn-health-data/main/"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_starter_registry_is_signed_eligible_and_installable(tmp_path: Path) -> None:
    distribution = REPO_ROOT / "distribution"
    registry_bytes = (distribution / "registry.json").read_bytes()
    signature = (distribution / "registry.json.sig").read_bytes()
    public_bytes = (distribution / "registry.pub").read_bytes()
    Ed25519PublicKey.from_public_bytes(public_bytes).verify(signature, registry_bytes)

    registry = json.loads(registry_bytes)
    assert registry["signature"]["keyId"] == _sha256(public_bytes)[:16]
    assert set(registry["datasets"]) == {"laboratory-cn"}
    dataset = registry["datasets"]["laboratory-cn"]
    assert dataset["recommendedRelease"] == "laboratory-cn@2026-08-30.r1"
    assert len(dataset["releases"]) == 1

    release = dataset["releases"][0]
    assert release["manifestUrl"].startswith(PUBLIC_ORIGIN)
    manifest_path = REPO_ROOT / release["manifestUrl"].removeprefix(PUBLIC_ORIGIN)
    manifest_bytes = manifest_path.read_bytes()
    assert _sha256(manifest_bytes) == release["manifestSha256"]

    manifest = json.loads(manifest_bytes)
    assert manifest["release"]["id"] == release["id"]
    assert manifest["rights"]["releaseEligible"] is True
    assert manifest["rights"]["redistribution"] == "public"
    assert manifest["runtime"]["minimumCliVersion"] == "0.2.0"
    assert manifest["canonical"]["recordCount"] == 18

    for declared in manifest["artifacts"]:
        artifact_bytes = manifest_path.with_name(declared["url"]).read_bytes()
        assert len(artifact_bytes) == declared["sizeBytes"]
        assert _sha256(artifact_bytes) == declared["sha256"]
    for report_name in ["diff", "validation"]:
        report = manifest[report_name]
        assert _sha256(manifest_path.with_name(report["report"]).read_bytes()) == report["sha256"]

    artifact = next(item for item in manifest["artifacts"] if item["name"] == "data.sqlite.zst")
    compressed = manifest_path.with_name(artifact["url"]).read_bytes()
    database_bytes = zstandard.ZstdDecompressor().decompress(
        compressed,
        max_output_size=artifact["uncompressedSizeBytes"],
    )
    assert len(database_bytes) == artifact["uncompressedSizeBytes"]
    assert _sha256(database_bytes) == artifact["uncompressedSha256"]

    database_path = tmp_path / "data.sqlite"
    database_path.write_bytes(database_bytes)
    with sqlite3.connect(f"file:{database_path}?mode=ro", uri=True) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA application_id").fetchone() == (0x434E4844,)
        assert connection.execute("SELECT count(*) FROM laboratory_concept").fetchone() == (18,)
