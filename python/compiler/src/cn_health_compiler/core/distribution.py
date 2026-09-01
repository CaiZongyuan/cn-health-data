"""Stage verified Candidate artifacts for public distribution."""

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from tempfile import mkdtemp
from typing import Any, cast

from cn_health_compiler.core.manifest import validate_manifest, write_json_atomic
from cn_health_compiler.core.source import hash_file

_DATASET_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_STORAGE_KEY = re.compile(r"^(?!.*\.\.)(?!.*[\\/])[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class StagedRelease:
    dataset_id: str
    release_id: str
    release_dir: Path
    manifest_path: Path


def stage_public_releases(
    manifest_paths: list[Path],
    *,
    output_root: Path,
    manifest_schema_path: Path,
) -> list[StagedRelease]:
    """Atomically stage release-eligible artifacts while omitting raw SQLite transport."""
    if not manifest_paths:
        raise ValueError("at least one Candidate Manifest is required")
    output_root = output_root.resolve()
    if output_root.exists():
        raise FileExistsError(f"refusing to replace existing distribution root: {output_root}")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(mkdtemp(prefix=f".{output_root.name}-", dir=output_root.parent))
    staged_identities: list[tuple[str, str, str]] = []
    seen_datasets: set[str] = set()
    try:
        for source_manifest_path in manifest_paths:
            source_manifest_path = source_manifest_path.resolve(strict=True)
            source_dir = source_manifest_path.parent
            manifest = cast(
                dict[str, Any], json.loads(source_manifest_path.read_text(encoding="utf-8"))
            )
            validate_manifest(manifest, manifest_schema_path)
            rights = cast(dict[str, Any], manifest["rights"])
            if rights.get("releaseEligible") is not True:
                raise ValueError(f"Manifest is not release-eligible: {source_manifest_path}")
            allowed = set(map(str, rights.get("allowedArtifactTypes", ())))
            if not allowed:
                raise ValueError(f"Manifest has no allowedArtifactTypes: {source_manifest_path}")

            dataset = cast(dict[str, Any], manifest["dataset"])
            release = cast(dict[str, Any], manifest["release"])
            dataset_id = str(dataset["id"])
            storage_key = str(release["storageKey"])
            release_id = str(release["id"])
            if _DATASET_ID.fullmatch(dataset_id) is None:
                raise ValueError(f"invalid Dataset ID: {dataset_id!r}")
            if _STORAGE_KEY.fullmatch(storage_key) is None:
                raise ValueError(f"invalid storageKey: {storage_key!r}")
            if dataset_id in seen_datasets:
                raise ValueError(f"multiple recommended Candidates supplied for {dataset_id}")
            seen_datasets.add(dataset_id)

            target_dir = temporary_root / "releases" / dataset_id / storage_key
            target_dir.mkdir(parents=True)
            public_artifacts: list[dict[str, Any]] = []
            has_compressed_sqlite = False
            for raw_artifact in cast(list[dict[str, Any]], manifest["artifacts"]):
                artifact = dict(raw_artifact)
                name = str(artifact["name"])
                url = str(artifact["url"])
                _validate_local_name(name, url)
                if name == "data.sqlite":
                    continue
                artifact_type = _artifact_type(artifact)
                if artifact_type is not None and artifact_type not in allowed:
                    raise ValueError(
                        f"artifact type {artifact_type!r} is not allowed for {release_id}"
                    )
                if name == "data.sqlite.zst":
                    has_compressed_sqlite = True
                _copy_verified(
                    source_dir / name,
                    target_dir / name,
                    expected_sha256=str(artifact["sha256"]),
                    expected_size=int(artifact["sizeBytes"]),
                )
                public_artifacts.append(artifact)
            if not has_compressed_sqlite:
                raise ValueError(f"Manifest has no public data.sqlite.zst artifact: {release_id}")

            for report_name in ("validation", "diff"):
                report = cast(dict[str, Any], manifest[report_name])
                filename = str(report["report"])
                _validate_local_name(filename, filename)
                _copy_verified(
                    source_dir / filename,
                    target_dir / filename,
                    expected_sha256=str(report["sha256"]),
                )

            manifest["artifacts"] = public_artifacts
            validate_manifest(manifest, manifest_schema_path)
            write_json_atomic(target_dir / "manifest.json", manifest)
            staged_identities.append((dataset_id, release_id, storage_key))

        os.replace(temporary_root, output_root)
        temporary_root = Path()
    finally:
        if temporary_root != Path() and temporary_root.exists():
            shutil.rmtree(temporary_root)

    return [
        StagedRelease(
            dataset_id=dataset_id,
            release_id=release_id,
            release_dir=output_root / "releases" / dataset_id / storage_key,
            manifest_path=output_root / "releases" / dataset_id / storage_key / "manifest.json",
        )
        for dataset_id, release_id, storage_key in staged_identities
    ]


def _artifact_type(artifact: dict[str, Any]) -> str | None:
    name = str(artifact["name"])
    if name == "data.sqlite.zst":
        return "sqlite-zstd"
    if name.endswith(".parquet"):
        return "parquet"
    return None


def _validate_local_name(name: str, url: str) -> None:
    path = Path(name)
    if not name or path.is_absolute() or path.name != name or url != name or ".." in path.parts:
        raise ValueError(f"unsafe local artifact path: name={name!r} url={url!r}")


def _copy_verified(
    source: Path,
    target: Path,
    *,
    expected_sha256: str,
    expected_size: int | None = None,
) -> None:
    actual_sha256, actual_size = hash_file(source)
    if actual_sha256 != expected_sha256 or (
        expected_size is not None and actual_size != expected_size
    ):
        raise ValueError(f"artifact hash or size does not match Manifest: {source}")
    shutil.copyfile(source, target)
    os.chmod(target, 0o644)
