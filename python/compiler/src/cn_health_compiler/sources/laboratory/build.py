"""Build the schema v2 adult laboratory runtime from pinned multi-source inputs."""

import hashlib
import platform
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import polars as pl
import rfc8785
import zstandard

from cn_health_compiler import __version__
from cn_health_compiler.core.candidate import (
    CandidateBuild,
    build_candidate_manifest,
    candidate_staging_directory,
    canonical_table_hash,
    compress_sqlite,
    resolve_git_commit,
    write_parquet,
)
from cn_health_compiler.core.dataset import load_yaml_mapping
from cn_health_compiler.core.manifest import validate_manifest, write_json_atomic
from cn_health_compiler.core.source import hash_file, snapshot_local_source
from cn_health_compiler.core.sqlite import SQLiteArtifact
from cn_health_compiler.sources.laboratory.evidence import inspect_panel_evidence
from cn_health_compiler.sources.laboratory.records import load_laboratory_catalog
from cn_health_compiler.sources.laboratory.sqlite import build_laboratory_sqlite
from cn_health_compiler.sources.laboratory.validation import (
    LaboratoryValidationReport,
    LaboratoryValidationRules,
)
from cn_health_compiler.sources.nhc_lab.records import iter_nhc_laboratory_records

_TABLES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("laboratory_test", ("code",), "laboratory-tests.parquet"),
    ("laboratory_reference", ("test_code", "sex"), "laboratory-references.parquet"),
    ("laboratory_panel", ("code",), "laboratory-panels.parquet"),
    (
        "laboratory_panel_member",
        ("panel_code", "sort_order"),
        "laboratory-panel-members.parquet",
    ),
)
_PREVIOUS_RELEASE = "laboratory-cn@2026-08-30.r2"
_PREVIOUS_SOURCE_SHA256 = "0ce998b45c921a06f2b1e016610afc83ea2886fc68c7ce7c5a69c8be6da43d2b"


def build_laboratory_candidate(
    repo_root: Path,
    source_path: Path,
    output_root: Path,
    *,
    panel_source_path: Path | None = None,
    build_revision: int = 1,
    sequence: int = 3,
    git_commit: str | None = None,
    created_at: datetime | None = None,
    base_release_dir: Path | None = None,
) -> CandidateBuild:
    if panel_source_path is None:
        raise ValueError("laboratory-cn requires the explicit panel evidence workbook")
    if base_release_dir is not None:
        raise ValueError("schema v1/v2 laboratory Releases use an explicit cross-schema diff")

    root = repo_root.resolve(strict=True)
    dataset_dir = root / "datasets/laboratory-cn"
    contract_path = dataset_dir / "dataset.yaml"
    layout_path = dataset_dir / "layout.yaml"
    schema_path = dataset_dir / "schema.sql"
    lock_path = root / "uv.lock"
    runtime_path = dataset_dir / "runtime.csv"
    panel_path = dataset_dir / "panels.csv"
    contract = load_yaml_mapping(contract_path)
    source = cast(dict[str, Any], contract["source"])
    panel_source = cast(dict[str, Any], source["panel_evidence"])
    runtime_source = cast(dict[str, Any], source["runtime_catalog"])
    panel_catalog_source = cast(dict[str, Any], source["panel_catalog"])
    source_version = str(source["declared_version"])
    storage_key = f"{source_version}.r{build_revision}"
    release_id = f"laboratory-cn@{storage_key}"
    timestamp = created_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise ValueError("created_at must be timezone-aware")
    resolved_commit = resolve_git_commit(root, git_commit)

    terminology_snapshot = snapshot_local_source(
        source_path,
        str(source["sha256"]),
        root / ".work/sources",
    )
    if terminology_snapshot.size_bytes != int(source["size_bytes"]):
        raise ValueError("WS/T 886 source size does not match Dataset Contract")
    panel_snapshot = snapshot_local_source(
        panel_source_path,
        str(panel_source["sha256"]),
        root / ".work/sources",
    )
    if panel_snapshot.size_bytes != int(panel_source["size_bytes"]):
        raise ValueError("panel evidence source size does not match Dataset Contract")
    runtime_sha256, runtime_size = _verify_project_source(runtime_path, runtime_source)
    panel_sha256, panel_size = _verify_project_source(panel_path, panel_catalog_source)

    terminology_records = tuple(
        iter_nhc_laboratory_records(
            terminology_snapshot.path,
            source_version=str(source["terminology_version"]),
            source_sha256=terminology_snapshot.sha256,
        )
    )
    terminology = {record.code: record for record in terminology_records}
    if len(terminology_records) != 399 or len(terminology) != 399:
        raise ValueError("laboratory-cn requires all 399 unique WS/T 886 records")
    evidence_names = inspect_panel_evidence(
        panel_snapshot.path,
        str(panel_source["worksheet"]),
    )
    catalog = load_laboratory_catalog(
        runtime_path,
        panel_path,
        terminology,
        source_version=source_version,
    )
    rules = LaboratoryValidationRules.model_validate(contract["validation"])

    releases_dir = output_root / "laboratory-cn/releases"
    with candidate_staging_directory(releases_dir, storage_key) as (temporary_dir, release_dir):
        sqlite_artifact = build_laboratory_sqlite(
            catalog,
            rules,
            schema_path,
            temporary_dir / "data.sqlite",
            terminology_count=len(terminology),
            evidence_names=evidence_names,
        )
        table_metadata: list[dict[str, object]] = []
        parquet_metadata: list[tuple[str, str, int]] = []
        for table, order_by, filename in _TABLES:
            table_sha256, count = canonical_table_hash(
                sqlite_artifact.path,
                table,
                order_by=order_by,
            )
            table_metadata.append(
                {"table": table, "recordCount": count, "sha256": table_sha256}
            )
            parquet_sha256, parquet_size = write_parquet(
                sqlite_artifact.path,
                table,
                temporary_dir / filename,
                order_by=order_by,
            )
            parquet_metadata.append((filename, parquet_sha256, parquet_size))
        canonical_sha256 = hashlib.sha256(
            rfc8785.dumps(cast(Any, table_metadata))
        ).hexdigest()
        compressed_sha256, compressed_size = compress_sqlite(
            sqlite_artifact.path,
            temporary_dir / "data.sqlite.zst",
        )
        validation_sha256, _ = write_json_atomic(
            temporary_dir / "validation.json",
            {
                "schemaVersion": 2,
                "passed": True,
                **sqlite_artifact.validation.model_dump(mode="json"),
            },
        )
        diff_sha256, _ = write_json_atomic(
            temporary_dir / "diff.json",
            {
                "schemaVersion": 1,
                "baseRelease": _PREVIOUS_RELEASE,
                "targetRelease": release_id,
                "baseSourceSha256": _PREVIOUS_SOURCE_SHA256,
                "targetSourceSha256": runtime_sha256,
                "added": sqlite_artifact.validation.record_count,
                "removed": 18,
                "modified": 0,
                "unchanged": 0,
                "modifiedFields": {},
                "note": (
                    "Primary identity changes from LOINC in schema v1 to WS/T 886 "
                    "in schema v2."
                ),
            },
        )
        manifest = _manifest(
            contract=contract,
            source=source,
            panel_source=panel_source,
            release_id=release_id,
            storage_key=storage_key,
            build_revision=build_revision,
            sequence=sequence,
            created_at=timestamp,
            git_commit=resolved_commit,
            terminology_snapshot=(
                terminology_snapshot.original_filename,
                terminology_snapshot.sha256,
                terminology_snapshot.size_bytes,
            ),
            panel_snapshot=(
                panel_snapshot.original_filename,
                panel_snapshot.sha256,
                panel_snapshot.size_bytes,
            ),
            runtime_source=(runtime_sha256, runtime_size),
            panel_catalog_source=(panel_sha256, panel_size),
            paths=(contract_path, layout_path, schema_path, lock_path),
            sqlite_artifact=sqlite_artifact,
            compressed=(compressed_sha256, compressed_size),
            parquets=parquet_metadata,
            canonical_sha256=canonical_sha256,
            table_metadata=table_metadata,
            validation_sha256=validation_sha256,
            diff_sha256=diff_sha256,
        )
        validate_manifest(manifest, root / "schemas/manifest.schema.json")
        write_json_atomic(temporary_dir / "manifest.json", manifest)
        return CandidateBuild(release_dir, release_dir / "manifest.json")


def _verify_project_source(path: Path, config: dict[str, Any]) -> tuple[str, int]:
    sha256, size = hash_file(path)
    if sha256 != str(config["sha256"]):
        raise ValueError(f"project catalog SHA256 mismatch: {path.name}")
    return sha256, size


def _manifest(
    *,
    contract: dict[str, Any],
    source: dict[str, Any],
    panel_source: dict[str, Any],
    release_id: str,
    storage_key: str,
    build_revision: int,
    sequence: int,
    created_at: datetime,
    git_commit: str,
    terminology_snapshot: tuple[str, str, int],
    panel_snapshot: tuple[str, str, int],
    runtime_source: tuple[str, int],
    panel_catalog_source: tuple[str, int],
    paths: tuple[Path, Path, Path, Path],
    sqlite_artifact: SQLiteArtifact[LaboratoryValidationReport],
    compressed: tuple[str, int],
    parquets: list[tuple[str, str, int]],
    canonical_sha256: str,
    table_metadata: list[dict[str, object]],
    validation_sha256: str,
    diff_sha256: str,
) -> dict[str, Any]:
    contract_path, layout_path, schema_path, lock_path = paths
    contract_sha256, _ = hash_file(contract_path)
    layout_sha256, _ = hash_file(layout_path)
    schema_sha256, _ = hash_file(schema_path)
    lock_sha256, _ = hash_file(lock_path)
    build_input_sha256 = hashlib.sha256(
        rfc8785.dumps(
            {
                "terminologySha256": terminology_snapshot[1],
                "panelEvidenceSha256": panel_snapshot[1],
                "runtimeCatalogSha256": runtime_source[0],
                "panelCatalogSha256": panel_catalog_source[0],
                "datasetContractSha256": contract_sha256,
                "datasetSchemaSha256": schema_sha256,
                "configSha256": layout_sha256,
                "lockSha256": lock_sha256,
                "gitCommit": git_commit,
                "adapterVersion": 2,
            }
        )
    ).hexdigest()
    sources: list[dict[str, object]] = [
        {
            "authority": "国家卫生健康委员会",
            "authorityRole": "original-authority",
            "authorityVerified": True,
            "format": "markdown",
            "acquisition": str(source["acquisition"]),
            "originalFilename": terminology_snapshot[0],
            "sourceUrl": source.get("source_url"),
            "publishedAt": source.get("published_at"),
            "dataAsOf": source.get("terminology_version"),
            "sha256": terminology_snapshot[1],
            "sizeBytes": terminology_snapshot[2],
            "recordCount": 399,
            "retention": "private-content-addressed",
            "reproducibleFromSource": True,
        },
        {
            "authority": "国家医疗保障局",
            "authorityRole": "panel-evidence-authority",
            "authorityVerified": True,
            "format": "xlsx",
            "acquisition": "manual-local",
            "originalFilename": panel_snapshot[0],
            "sourceUrl": None,
            "dataAsOf": "2026-08-13",
            "sha256": panel_snapshot[1],
            "sizeBytes": panel_snapshot[2],
            "worksheet": panel_source["worksheet"],
            "recordCount": 662,
            "retention": "private-content-addressed",
            "reproducibleFromSource": True,
        },
        {
            "authority": "CN Health Data contributors",
            "authorityRole": "project-author",
            "authorityVerified": True,
            "format": "csv",
            "acquisition": "repository",
            "originalFilename": "runtime.csv",
            "sourceUrl": "https://github.com/CaiZongyuan/cn-health-data/blob/main/datasets/laboratory-cn/runtime.csv",
            "dataAsOf": source["declared_version"],
            "sha256": runtime_source[0],
            "sizeBytes": runtime_source[1],
            "recordCount": sqlite_artifact.validation.reference_count,
            "retention": "repository",
            "reproducibleFromSource": True,
        },
        {
            "authority": "CN Health Data contributors",
            "authorityRole": "project-author",
            "authorityVerified": True,
            "format": "csv",
            "acquisition": "repository",
            "originalFilename": "panels.csv",
            "sourceUrl": "https://github.com/CaiZongyuan/cn-health-data/blob/main/datasets/laboratory-cn/panels.csv",
            "dataAsOf": source["declared_version"],
            "sha256": panel_catalog_source[0],
            "sizeBytes": panel_catalog_source[1],
            "recordCount": sqlite_artifact.validation.panel_member_count,
            "retention": "repository",
            "reproducibleFromSource": True,
        },
    ]
    compiler: dict[str, object] = {
        "name": "cn-health-compiler",
        "version": __version__,
        "adapter": "laboratory-cn",
        "adapterVersion": 2,
        "gitCommit": git_commit,
        "lockSha256": lock_sha256,
        "configSha256": layout_sha256,
        "datasetContractSha256": contract_sha256,
        "datasetSchemaSha256": schema_sha256,
        "buildInputSha256": build_input_sha256,
        "pythonVersion": platform.python_version(),
        "sqliteVersion": sqlite3.sqlite_version,
        "zstandardVersion": zstandard.__version__,
        "polarsVersion": pl.__version__,
    }
    artifacts: list[dict[str, object]] = [
        {
            "name": "data.sqlite",
            "url": "data.sqlite",
            "mediaType": "application/vnd.sqlite3",
            "sha256": sqlite_artifact.sha256,
            "sizeBytes": sqlite_artifact.size_bytes,
        },
        {
            "name": "data.sqlite.zst",
            "url": "data.sqlite.zst",
            "mediaType": "application/zstd",
            "compression": "zstd",
            "sha256": compressed[0],
            "sizeBytes": compressed[1],
            "uncompressedName": "data.sqlite",
            "uncompressedSha256": sqlite_artifact.sha256,
            "uncompressedSizeBytes": sqlite_artifact.size_bytes,
        },
    ]
    artifacts.extend(
        {
            "name": filename,
            "url": filename,
            "mediaType": "application/vnd.apache.parquet",
            "sha256": sha256,
            "sizeBytes": size,
        }
        for filename, sha256, size in parquets
    )
    manifest = build_candidate_manifest(
        contract=contract,
        dataset_id="laboratory-cn",
        source_version=str(source["declared_version"]),
        release_id=release_id,
        storage_key=storage_key,
        build_revision=build_revision,
        sequence=sequence,
        created_at=created_at,
        supersedes=_PREVIOUS_RELEASE,
        sources=sources,
        compiler=compiler,
        canonical={
            "serialization": "canonical-multitable-ndjson-v1",
            "recordCount": sqlite_artifact.validation.record_count,
            "sha256": canonical_sha256,
            "tables": table_metadata,
        },
        artifacts=artifacts,
        validation_sha256=validation_sha256,
        diff_sha256=diff_sha256,
    )
    manifest["runtime"]["minimumCliVersion"] = "0.4.0"
    return manifest
