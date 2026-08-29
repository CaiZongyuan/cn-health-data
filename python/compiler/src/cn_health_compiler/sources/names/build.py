"""End-to-end local Candidate build for Chinese name components."""

import hashlib
import json
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
from cn_health_compiler.core.diff import compare_sqlite_tables
from cn_health_compiler.core.manifest import validate_manifest, write_json_atomic
from cn_health_compiler.core.source import hash_file, snapshot_local_source
from cn_health_compiler.sources.names.records import parse_faker_name_components
from cn_health_compiler.sources.names.sqlite import build_names_sqlite
from cn_health_compiler.sources.names.validation import NamesValidationRules

_DIFF_EXCLUDED_FIELDS = (
    "source_line",
    "source_ordinal",
    "source_version",
    "source_sha256",
)


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


def _build_diff(
    *,
    database_path: Path,
    release_id: str,
    source_sha256: str,
    record_count: int,
    base_release_dir: Path | None,
) -> tuple[dict[str, object], str | None]:
    if base_release_dir is None:
        return (
            {
                "schemaVersion": 1,
                "baseRelease": None,
                "targetRelease": release_id,
                "baseSourceSha256": None,
                "targetSourceSha256": source_sha256,
                "added": record_count,
                "removed": 0,
                "modified": 0,
                "unchanged": 0,
                "modifiedFields": {},
            },
            None,
        )
    base_release_dir = base_release_dir.resolve(strict=True)
    base_manifest = cast(
        dict[str, Any],
        json.loads((base_release_dir / "manifest.json").read_text(encoding="utf-8")),
    )
    if cast(dict[str, Any], base_manifest["dataset"])["id"] != "names-cn":
        raise ValueError("base Release belongs to a different Dataset")
    artifacts = cast(list[dict[str, Any]], base_manifest["artifacts"])
    base_artifact = next(
        (artifact for artifact in artifacts if artifact["name"] == "data.sqlite"), None
    )
    if base_artifact is None:
        raise ValueError("base names Manifest has no SQLite artifact")
    base_database = base_release_dir / "data.sqlite"
    base_sha256, _ = hash_file(base_database)
    if base_sha256 != base_artifact["sha256"]:
        raise ValueError("base Release SQLite SHA256 does not match its Manifest")
    report = compare_sqlite_tables(
        base_database,
        database_path,
        "name_component",
        excluded_fields=_DIFF_EXCLUDED_FIELDS,
    )
    base_sources = cast(list[dict[str, Any]], base_manifest["sources"])
    if len(base_sources) != 1:
        raise ValueError("base names Manifest has an unexpected source set")
    base_release_id = str(cast(dict[str, Any], base_manifest["release"])["id"])
    return (
        {
            "schemaVersion": 1,
            "baseRelease": base_release_id,
            "targetRelease": release_id,
            "baseSourceSha256": str(base_sources[0]["sha256"]),
            "targetSourceSha256": source_sha256,
            "added": report.added,
            "removed": report.removed,
            "modified": report.modified,
            "unchanged": report.unchanged,
            "modifiedFields": dict(report.modified_fields),
        },
        base_release_id,
    )


def build_names_candidate(
    repo_root: Path,
    source_path: Path,
    output_root: Path,
    *,
    build_revision: int = 1,
    sequence: int = 1,
    git_commit: str | None = None,
    created_at: datetime | None = None,
    base_release_dir: Path | None = None,
) -> CandidateBuild:
    repo_root = repo_root.resolve(strict=True)
    dataset_dir = repo_root / "datasets/names-cn"
    contract_path = dataset_dir / "dataset.yaml"
    layout_path = dataset_dir / "layout.yaml"
    schema_path = dataset_dir / "schema.sql"
    lock_path = repo_root / "uv.lock"
    contract = load_yaml_mapping(contract_path)
    source = cast(dict[str, Any], contract["source"])
    source_version = str(source["declared_version"])
    storage_key = f"{source_version}.r{build_revision}"
    release_id = f"names-cn@{storage_key}"
    resolved_commit = resolve_git_commit(repo_root, git_commit)
    timestamp = created_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise ValueError("created_at must be timezone-aware")

    releases_dir = output_root / "names-cn/releases"
    with candidate_staging_directory(releases_dir, storage_key) as (temporary_dir, release_dir):
        snapshot = snapshot_local_source(
            source_path,
            str(source["sha256"]),
            repo_root / ".work/sources",
        )
        if snapshot.size_bytes != int(source["size_bytes"]):
            raise ValueError("source size does not match Dataset Contract")
        rules = NamesValidationRules.model_validate(contract["validation"])
        sqlite_artifact = build_names_sqlite(
            parse_faker_name_components(
                snapshot.path,
                source_version=source_version,
                source_sha256=snapshot.sha256,
            ),
            rules,
            schema_path,
            temporary_dir / "data.sqlite",
        )
        canonical_sha256, canonical_count = canonical_table_hash(
            sqlite_artifact.path, "name_component"
        )
        if canonical_count != sqlite_artifact.validation.record_count:
            raise RuntimeError("canonical hash row count differs from SQLite validation")
        compressed_sha256, compressed_size = compress_sqlite(
            sqlite_artifact.path, temporary_dir / "data.sqlite.zst"
        )
        parquet_sha256, parquet_size = write_parquet(
            sqlite_artifact.path,
            "name_component",
            temporary_dir / "data.parquet",
        )
        validation_sha256, _ = write_json_atomic(
            temporary_dir / "validation.json",
            {
                "schemaVersion": 1,
                "passed": True,
                **sqlite_artifact.validation.model_dump(mode="json"),
            },
        )
        diff_payload, supersedes = _build_diff(
            database_path=sqlite_artifact.path,
            release_id=release_id,
            source_sha256=snapshot.sha256,
            record_count=canonical_count,
            base_release_dir=base_release_dir,
        )
        diff_sha256, _ = write_json_atomic(temporary_dir / "diff.json", diff_payload)
        contract_sha256, _ = hash_file(contract_path)
        layout_sha256, _ = hash_file(layout_path)
        schema_sha256, _ = hash_file(schema_path)
        lock_sha256, _ = hash_file(lock_path)
        build_input_sha256 = hashlib.sha256(
            rfc8785.dumps(
                {
                    "sourceSha256": snapshot.sha256,
                    "datasetContractSha256": contract_sha256,
                    "datasetSchemaSha256": schema_sha256,
                    "configSha256": layout_sha256,
                    "lockSha256": lock_sha256,
                    "gitCommit": resolved_commit,
                    "adapterVersion": 1,
                }
            )
        ).hexdigest()
        authority = cast(dict[str, Any], contract["authority"])
        rights = cast(dict[str, Any], contract["rights"])
        runtime = cast(dict[str, Any], contract["runtime"])
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
                "supersedes": supersedes,
                "revoked": False,
            },
            "dataset": {
                "id": "names-cn",
                "sourceVersion": source_version,
                "datasetSchemaVersion": 1,
                "status": str(contract["status"]),
            },
            "sources": [
                {
                    "authority": str(authority["name"]),
                    "authorityRole": str(authority["role"]),
                    "authorityVerified": not str(authority["verification"]).startswith("pending"),
                    "format": "python-source",
                    "acquisition": str(source["acquisition"]),
                    "originalFilename": snapshot.original_filename,
                    "sourceUrl": source.get("source_url"),
                    "dataAsOf": source_version,
                    "upstreamCommit": source.get("upstream_commit"),
                    "sha256": snapshot.sha256,
                    "sizeBytes": snapshot.size_bytes,
                    "recordCount": canonical_count,
                    "retention": "private-content-addressed",
                    "reproducibleFromSource": True,
                }
            ],
            "compiler": {
                "name": "cn-health-compiler",
                "version": __version__,
                "adapter": "names-cn",
                "adapterVersion": 1,
                "gitCommit": resolved_commit,
                "lockSha256": lock_sha256,
                "configSha256": layout_sha256,
                "datasetContractSha256": contract_sha256,
                "datasetSchemaSha256": schema_sha256,
                "buildInputSha256": build_input_sha256,
            },
            "canonical": {
                "serialization": "canonical-ndjson-v1",
                "recordCount": canonical_count,
                "sha256": canonical_sha256,
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
                _artifact(
                    "data.parquet",
                    "application/vnd.apache.parquet",
                    parquet_sha256,
                    parquet_size,
                ),
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
