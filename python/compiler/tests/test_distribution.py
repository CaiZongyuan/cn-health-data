import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cn_health_compiler.core.distribution import stage_public_releases

REPO_ROOT = Path(__file__).resolve().parents[3]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _candidate(root: Path, *, eligible: bool = True) -> Path:
    root.mkdir()
    files = {
        "data.sqlite": b"sqlite",
        "data.sqlite.zst": b"zstd",
        "data.parquet": b"parquet",
        "license.txt": b"license",
        "validation.json": b"validation",
        "diff.json": b"diff",
    }
    for name, payload in files.items():
        (root / name).write_bytes(payload)
    artifacts = []
    for name in ("data.sqlite", "data.sqlite.zst", "data.parquet", "license.txt"):
        payload = files[name]
        artifact: dict[str, object] = {
            "name": name,
            "url": name,
            "mediaType": "application/octet-stream",
            "sha256": _sha256(payload),
            "sizeBytes": len(payload),
        }
        if name == "data.sqlite.zst":
            artifact.update(
                {
                    "compression": "zstd",
                    "uncompressedName": "data.sqlite",
                    "uncompressedSha256": _sha256(files["data.sqlite"]),
                    "uncompressedSizeBytes": len(files["data.sqlite"]),
                }
            )
        artifacts.append(artifact)
    manifest = {
        "schemaVersion": 1,
        "release": {
            "id": "example@2026.r1",
            "sequence": 1,
            "storageKey": "2026.r1",
            "buildRevision": 1,
            "createdAt": datetime(2026, 9, 1, tzinfo=UTC).isoformat(),
            "supersedes": None,
            "revoked": False,
        },
        "dataset": {
            "id": "example",
            "sourceVersion": "2026",
            "datasetSchemaVersion": 1,
            "status": "stable",
        },
        "sources": [
            {
                "authority": "Example",
                "format": "fixture",
                "acquisition": "manual-local",
                "sha256": "a" * 64,
                "sizeBytes": 1,
            }
        ],
        "compiler": {
            "name": "test",
            "version": "1",
            "adapter": "test",
            "adapterVersion": 1,
            "gitCommit": "b" * 40,
            "lockSha256": "c" * 64,
            "configSha256": "d" * 64,
            "buildInputSha256": "e" * 64,
        },
        "canonical": {
            "serialization": "fixture",
            "recordCount": 1,
            "sha256": "f" * 64,
        },
        "artifacts": artifacts,
        "validation": {
            "passed": True,
            "report": "validation.json",
            "sha256": _sha256(files["validation.json"]),
        },
        "diff": {"report": "diff.json", "sha256": _sha256(files["diff.json"])},
        "rights": {
            "redistribution": "normalized-only",
            "releaseEligible": eligible,
            "evidence": ["fixture"],
            "allowedArtifactTypes": ["sqlite", "sqlite-zstd", "parquet"],
        },
        "runtime": {"minimumCliVersion": "0.2.0", "minimumSQLiteVersion": "3.34.0"},
    }
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_stage_public_release_omits_raw_sqlite_and_copies_declared_files(tmp_path: Path) -> None:
    manifest = _candidate(tmp_path / "candidate")
    output = tmp_path / "public"

    staged = stage_public_releases(
        [manifest],
        output_root=output,
        manifest_schema_path=REPO_ROOT / "schemas/manifest.schema.json",
    )

    assert [item.release_id for item in staged] == ["example@2026.r1"]
    target = output / "releases/example/2026.r1"
    public_manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert [item["name"] for item in public_manifest["artifacts"]] == [
        "data.sqlite.zst",
        "data.parquet",
        "license.txt",
    ]
    assert not (target / "data.sqlite").exists()
    assert (target / "validation.json").read_bytes() == b"validation"
    assert (target / "diff.json").read_bytes() == b"diff"


def test_stage_public_release_rejects_ineligible_or_tampered_candidates(tmp_path: Path) -> None:
    ineligible = _candidate(tmp_path / "ineligible", eligible=False)
    with pytest.raises(ValueError, match="not release-eligible"):
        stage_public_releases(
            [ineligible],
            output_root=tmp_path / "public-ineligible",
            manifest_schema_path=REPO_ROOT / "schemas/manifest.schema.json",
        )

    tampered = _candidate(tmp_path / "tampered")
    (tampered.parent / "data.parquet").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash or size"):
        stage_public_releases(
            [tampered],
            output_root=tmp_path / "public-tampered",
            manifest_schema_path=REPO_ROOT / "schemas/manifest.schema.json",
        )
