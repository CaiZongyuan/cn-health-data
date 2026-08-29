"""End-to-end local Candidate build for Chinese geography data."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import rfc8785

from cn_health_compiler import __version__
from cn_health_compiler.core.candidate import (
    CandidateBuild,
    candidate_staging_directory,
    canonical_table_hash,
    compress_sqlite,
    resolve_git_commit,
    write_parquet,
)
from cn_health_compiler.core.dataset import load_yaml_mapping
from cn_health_compiler.core.manifest import validate_manifest, write_json_atomic
from cn_health_compiler.core.source import SourceSnapshot, hash_file, snapshot_local_source
from cn_health_compiler.sources.geography.records import (
    iter_area_city_divisions,
    iter_geonames_places,
    iter_geonames_postal_areas,
)
from cn_health_compiler.sources.geography.sqlite import build_geography_sqlite
from cn_health_compiler.sources.geography.validation import GeographyValidationRules

_TABLE_ARTIFACTS = (
    ("administrative_division", "administrative-divisions.parquet"),
    ("place", "places.parquet"),
    ("postal_area", "postal-areas.parquet"),
)


def _source_config(contract: dict[str, Any], role: str) -> dict[str, Any]:
    source = cast(dict[str, Any], contract["source"])
    return cast(dict[str, Any], source[role])


def _snapshot(
    path: Path,
    config: dict[str, Any],
    snapshots_dir: Path,
) -> SourceSnapshot:
    snapshot = snapshot_local_source(path, str(config["sha256"]), snapshots_dir)
    if snapshot.size_bytes != int(config["size_bytes"]):
        raise ValueError(f"source size does not match Dataset Contract: {path}")
    return snapshot


def _artifact(
    name: str,
    media_type: str,
    sha256: str,
    size_bytes: int,
) -> dict[str, object]:
    return {
        "name": name,
        "url": name,
        "mediaType": media_type,
        "sha256": sha256,
        "sizeBytes": size_bytes,
    }


def _source_manifest(
    *,
    role: str,
    snapshot: SourceSnapshot,
    config: dict[str, Any],
    contract: dict[str, Any],
    source_version: str,
    record_count: int,
) -> dict[str, object]:
    authority = cast(dict[str, Any], contract["authority"])
    source = cast(dict[str, Any], contract["source"])
    return {
        "authority": str(config.get("authority", authority["name"])),
        "authorityRole": str(config.get("authority_role", authority["role"])),
        "authorityVerified": not str(authority["verification"]).startswith("pending"),
        "role": role,
        "format": str(config.get("format", snapshot.path.suffix.removeprefix("."))),
        "acquisition": str(config.get("acquisition", source["acquisition"])),
        "originalFilename": snapshot.original_filename,
        "sourceUrl": config.get("source_url"),
        "dataAsOf": source_version,
        "sha256": snapshot.sha256,
        "sizeBytes": snapshot.size_bytes,
        "recordCount": record_count,
        "retention": "private-content-addressed",
        "reproducibleFromSource": True,
    }


def _canonical_identity(database_path: Path) -> tuple[str, int, list[dict[str, str | int]]]:
    tables: list[dict[str, str | int]] = []
    total_count = 0
    for table, _ in _TABLE_ARTIFACTS:
        sha256, count = canonical_table_hash(database_path, table)
        tables.append({"table": table, "recordCount": count, "sha256": sha256})
        total_count += count
    digest = hashlib.sha256(rfc8785.dumps({"tables": tables})).hexdigest()
    return digest, total_count, tables


def build_geography_candidate(
    repo_root: Path,
    gazetteer_path: Path,
    division_path: Path,
    postal_path: Path,
    output_root: Path,
    *,
    build_revision: int = 1,
    sequence: int = 1,
    git_commit: str | None = None,
    created_at: datetime | None = None,
) -> CandidateBuild:
    repo_root = repo_root.resolve(strict=True)
    dataset_dir = repo_root / "datasets/geography-cn"
    contract_path = dataset_dir / "dataset.yaml"
    layout_path = dataset_dir / "layout.yaml"
    schema_path = dataset_dir / "schema.sql"
    lock_path = repo_root / "uv.lock"
    contract = load_yaml_mapping(contract_path)
    source = cast(dict[str, Any], contract["source"])
    source_version = str(source["declared_version"])
    storage_key = f"{source_version}.r{build_revision}"
    release_id = f"geography-cn@{storage_key}"
    resolved_commit = resolve_git_commit(repo_root, git_commit)
    timestamp = created_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise ValueError("created_at must be timezone-aware")

    releases_dir = output_root / "geography-cn/releases"
    with candidate_staging_directory(releases_dir, storage_key) as (temporary_dir, release_dir):
        snapshots_dir = repo_root / ".work/sources"
        division_snapshot = _snapshot(
            division_path, _source_config(contract, "divisions"), snapshots_dir
        )
        gazetteer_snapshot = _snapshot(
            gazetteer_path, _source_config(contract, "gazetteer"), snapshots_dir
        )
        postal_snapshot = _snapshot(postal_path, _source_config(contract, "postal"), snapshots_dir)
        divisions = list(
            iter_area_city_divisions(
                division_snapshot.path,
                source_version=source_version,
                source_sha256=division_snapshot.sha256,
            )
        )
        places = list(
            iter_geonames_places(
                gazetteer_snapshot.path,
                source_version=source_version,
                source_sha256=gazetteer_snapshot.sha256,
            )
        )
        postal_areas = list(
            iter_geonames_postal_areas(
                postal_snapshot.path,
                source_version=source_version,
                source_sha256=postal_snapshot.sha256,
            )
        )
        rules = GeographyValidationRules.model_validate(contract["validation"])
        sqlite_artifact = build_geography_sqlite(
            places,
            postal_areas,
            rules,
            schema_path,
            temporary_dir / "data.sqlite",
            administrative_divisions=divisions,
        )
        canonical_sha256, canonical_count, canonical_tables = _canonical_identity(
            sqlite_artifact.path
        )
        if canonical_count != sqlite_artifact.validation.record_count:
            raise RuntimeError("canonical hash row count differs from SQLite validation")
        compressed_sha256, compressed_size = compress_sqlite(
            sqlite_artifact.path, temporary_dir / "data.sqlite.zst"
        )
        parquet_artifacts: list[dict[str, object]] = []
        for table, filename in _TABLE_ARTIFACTS:
            parquet_sha256, parquet_size = write_parquet(
                sqlite_artifact.path, table, temporary_dir / filename
            )
            parquet_artifacts.append(
                _artifact(filename, "application/vnd.apache.parquet", parquet_sha256, parquet_size)
            )
        validation_sha256, _ = write_json_atomic(
            temporary_dir / "validation.json",
            {
                "schemaVersion": 1,
                "passed": True,
                **sqlite_artifact.validation.model_dump(mode="json", by_alias=True),
            },
        )
        source_set_sha256 = hashlib.sha256(
            rfc8785.dumps(
                {
                    "administrative-divisions": division_snapshot.sha256,
                    "gazetteer": gazetteer_snapshot.sha256,
                    "postal-areas": postal_snapshot.sha256,
                }
            )
        ).hexdigest()
        diff_sha256, _ = write_json_atomic(
            temporary_dir / "diff.json",
            {
                "schemaVersion": 1,
                "baseRelease": None,
                "targetRelease": release_id,
                "baseSourceSha256": None,
                "targetSourceSha256": source_set_sha256,
                "added": canonical_count,
                "removed": 0,
                "modified": 0,
                "unchanged": 0,
                "modifiedFields": {},
            },
        )
        contract_sha256, _ = hash_file(contract_path)
        layout_sha256, _ = hash_file(layout_path)
        schema_sha256, _ = hash_file(schema_path)
        lock_sha256, _ = hash_file(lock_path)
        build_input_sha256 = hashlib.sha256(
            rfc8785.dumps(
                {
                    "sourceSetSha256": source_set_sha256,
                    "datasetContractSha256": contract_sha256,
                    "datasetSchemaSha256": schema_sha256,
                    "configSha256": layout_sha256,
                    "lockSha256": lock_sha256,
                    "gitCommit": resolved_commit,
                    "adapterVersion": 1,
                }
            )
        ).hexdigest()
        rights = cast(dict[str, Any], contract["rights"])
        runtime = cast(dict[str, Any], contract["runtime"])
        sources = [
            _source_manifest(
                role="administrative-divisions",
                snapshot=division_snapshot,
                config=_source_config(contract, "divisions"),
                contract=contract,
                source_version=source_version,
                record_count=sqlite_artifact.validation.administrative_division_count,
            ),
            _source_manifest(
                role="gazetteer",
                snapshot=gazetteer_snapshot,
                config=_source_config(contract, "gazetteer"),
                contract=contract,
                source_version=source_version,
                record_count=sqlite_artifact.validation.place_count,
            ),
            _source_manifest(
                role="postal-areas",
                snapshot=postal_snapshot,
                config=_source_config(contract, "postal"),
                contract=contract,
                source_version=source_version,
                record_count=sqlite_artifact.validation.postal_count,
            ),
        ]
        created_at_text = (
            timestamp.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        )
        manifest = {
            "schemaVersion": 1,
            "release": {
                "id": release_id,
                "sequence": sequence,
                "storageKey": storage_key,
                "buildRevision": build_revision,
                "createdAt": created_at_text,
                "supersedes": None,
                "revoked": False,
            },
            "dataset": {
                "id": "geography-cn",
                "sourceVersion": source_version,
                "datasetSchemaVersion": 1,
                "status": str(contract["status"]),
            },
            "sources": sources,
            "compiler": {
                "name": "cn-health-compiler",
                "version": __version__,
                "adapter": "geography-cn",
                "adapterVersion": 1,
                "gitCommit": resolved_commit,
                "lockSha256": lock_sha256,
                "configSha256": layout_sha256,
                "datasetContractSha256": contract_sha256,
                "datasetSchemaSha256": schema_sha256,
                "buildInputSha256": build_input_sha256,
            },
            "canonical": {
                "serialization": "canonical-table-hashes-v1",
                "recordCount": canonical_count,
                "sha256": canonical_sha256,
                "tables": canonical_tables,
            },
            "artifacts": [
                _artifact(
                    "data.sqlite",
                    "application/vnd.sqlite3",
                    sqlite_artifact.sha256,
                    sqlite_artifact.size_bytes,
                ),
                {
                    **_artifact(
                        "data.sqlite.zst",
                        "application/zstd",
                        compressed_sha256,
                        compressed_size,
                    ),
                    "compression": "zstd",
                    "uncompressedName": "data.sqlite",
                    "uncompressedSha256": sqlite_artifact.sha256,
                    "uncompressedSizeBytes": sqlite_artifact.size_bytes,
                },
                *parquet_artifacts,
            ],
            "validation": {
                "passed": True,
                "report": "validation.json",
                "sha256": validation_sha256,
            },
            "diff": {"report": "diff.json", "sha256": diff_sha256},
            "rights": {
                "redistribution": str(rights["redistribution"]),
                "releaseEligible": bool(rights["release_eligible"]),
                "evidence": None,
            },
            "runtime": {
                "minimumCliVersion": "0.2.0",
                "minimumSQLiteVersion": str(runtime["minimum_sqlite_version"]),
            },
        }
        validate_manifest(manifest, repo_root / "schemas/manifest.schema.json")
        write_json_atomic(temporary_dir / "manifest.json", manifest)
        return CandidateBuild(release_dir, release_dir / "manifest.json")
