import hashlib
import json
import sqlite3
from pathlib import Path

import zstandard
from cn_health_compiler.core.manifest import validate_manifest
from cn_health_compiler.core.source import hash_file
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

REPO_ROOT = Path(__file__).resolve().parents[3]
PUBLIC_ORIGIN = "https://raw.githubusercontent.com/CaiZongyuan/cn-health-data/main/"
EXPECTED_RELEASES = {
    "geography-cn": "geography-cn@2026-08-29.r2",
    "laboratory-cn": "laboratory-cn@2026-08-30.r2",
    "loinc-zh-cn": "loinc-zh-cn@2.83.r2",
    "names-cn": "names-cn@40.37.0.r2",
    "nhc-icd10-clinical": "nhc-icd10-clinical@2022.r4",
    "nhsa-drugs": "nhsa-drugs@2026-01-09.r4",
    "population-cn": "population-cn@WPP2024.r2",
}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_full_registry_is_signed_complete_and_installable(tmp_path: Path) -> None:
    distribution = REPO_ROOT / "distribution"
    registry_bytes = (distribution / "registry.json").read_bytes()
    signature = (distribution / "registry.json.sig").read_bytes()
    public_bytes = (distribution / "registry.pub").read_bytes()
    Ed25519PublicKey.from_public_bytes(public_bytes).verify(signature, registry_bytes)

    registry = json.loads(registry_bytes)
    assert registry["signature"]["keyId"] == _sha256(public_bytes)[:16]
    assert set(registry["datasets"]) == set(EXPECTED_RELEASES)
    assert not list(distribution.rglob("data.sqlite"))

    total_compressed = 0
    total_uncompressed = 0
    for dataset_id, expected_release_id in EXPECTED_RELEASES.items():
        dataset = registry["datasets"][dataset_id]
        assert dataset["recommendedRelease"] == expected_release_id
        assert len(dataset["releases"]) == 1
        release = dataset["releases"][0]
        assert release["manifestUrl"].startswith(PUBLIC_ORIGIN)
        manifest_path = REPO_ROOT / release["manifestUrl"].removeprefix(PUBLIC_ORIGIN)
        manifest_bytes = manifest_path.read_bytes()
        assert _sha256(manifest_bytes) == release["manifestSha256"]

        manifest = json.loads(manifest_bytes)
        validate_manifest(manifest, REPO_ROOT / "schemas/manifest.schema.json")
        assert manifest["release"]["id"] == expected_release_id
        assert manifest["rights"]["releaseEligible"] is True
        assert manifest["runtime"]["minimumCliVersion"] == "0.2.0"
        assert "data.sqlite" not in {item["name"] for item in manifest["artifacts"]}

        for declared in manifest["artifacts"]:
            artifact_path = manifest_path.with_name(declared["url"])
            assert hash_file(artifact_path) == (declared["sha256"], declared["sizeBytes"])
        for report_name in ["diff", "validation"]:
            report = manifest[report_name]
            assert hash_file(manifest_path.with_name(report["report"]))[0] == report["sha256"]

        compressed = next(
            item for item in manifest["artifacts"] if item["name"] == "data.sqlite.zst"
        )
        total_compressed += compressed["sizeBytes"]
        total_uncompressed += compressed["uncompressedSizeBytes"]
        database_path = tmp_path / f"{dataset_id}.sqlite"
        with (
            manifest_path.with_name(compressed["url"]).open("rb") as source,
            database_path.open("wb") as target,
        ):
            zstandard.ZstdDecompressor().copy_stream(source, target)
        assert hash_file(database_path) == (
            compressed["uncompressedSha256"],
            compressed["uncompressedSizeBytes"],
        )
        with sqlite3.connect(f"file:{database_path}?mode=ro", uri=True) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            assert connection.execute("PRAGMA application_id").fetchone() == (0x434E4844,)
        database_path.unlink()

    assert total_compressed == 78_991_543
    assert total_uncompressed == 822_198_272
