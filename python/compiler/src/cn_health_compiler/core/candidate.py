"""Shared provenance and packaging for local Dataset Candidates."""

import hashlib
import os
import platform
import re
import shutil
import sqlite3
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import mkdtemp
from typing import Any, cast

import rfc8785
import zstandard

from cn_health_compiler import __version__
from cn_health_compiler.core.dataset import load_yaml_mapping
from cn_health_compiler.core.manifest import validate_manifest, write_json_atomic
from cn_health_compiler.core.source import hash_file, snapshot_local_source
from cn_health_compiler.core.sqlite import RecordCountReport, SQLiteArtifact
from cn_health_compiler.core.workbook import WorkbookConfig, WorkbookInspection, inspect_workbook

_GIT_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_SQL_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class DirtyRepositoryError(RuntimeError):
    """Raised when build provenance cannot identify all compiler inputs."""


@dataclass(frozen=True, slots=True)
class CandidateBuild:
    release_dir: Path
    manifest_path: Path
    manifest: dict[str, Any]


@dataclass(frozen=True, slots=True)
class XlsxCandidateAdapter[RecordT, RulesT, ReportT: RecordCountReport]:
    dataset_id: str
    source_version_field: str
    table: str
    iter_records: Callable[[WorkbookInspection, WorkbookConfig, str, str], Iterable[RecordT]]
    load_rules: Callable[[Path], RulesT]
    build_sqlite: Callable[[Iterable[RecordT], RulesT, Path, Path], SQLiteArtifact[ReportT]]
    validation_payload: Callable[[ReportT], dict[str, object]]


def build_xlsx_candidate[RecordT, RulesT, ReportT: RecordCountReport](
    adapter: XlsxCandidateAdapter[RecordT, RulesT, ReportT],
    repo_root: Path,
    source_path: Path,
    output_root: Path,
    *,
    build_revision: int = 1,
    sequence: int = 1,
    git_commit: str | None = None,
    created_at: datetime | None = None,
) -> CandidateBuild:
    repo_root = repo_root.resolve(strict=True)
    dataset_dir = repo_root / "datasets" / adapter.dataset_id
    contract_path = dataset_dir / "dataset.yaml"
    workbook_path = dataset_dir / "workbook.yaml"
    schema_path = dataset_dir / "schema.sql"
    lock_path = repo_root / "uv.lock"
    contract = load_yaml_mapping(contract_path)
    source_config = cast(dict[str, Any], contract["source"])
    source_version = str(source_config[adapter.source_version_field])
    storage_key = f"{source_version}.r{build_revision}"
    release_id = f"{adapter.dataset_id}@{storage_key}"
    resolved_commit = resolve_git_commit(repo_root, git_commit)
    created_at = created_at or datetime.now(UTC)
    if created_at.tzinfo is None:
        raise ValueError("created_at must be timezone-aware")

    releases_dir = output_root / adapter.dataset_id / "releases"
    release_dir = releases_dir / storage_key
    if release_dir.exists():
        raise FileExistsError(f"refusing to overwrite Candidate: {release_dir}")
    releases_dir.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(mkdtemp(prefix=f".{storage_key}-", dir=releases_dir))
    try:
        workbook_config = WorkbookConfig.load(workbook_path)
        snapshot = snapshot_local_source(
            source_path,
            str(source_config["sha256"]),
            repo_root / ".work" / "sources",
        )
        inspection = inspect_workbook(snapshot, workbook_config)
        sqlite_artifact = adapter.build_sqlite(
            adapter.iter_records(inspection, workbook_config, source_version, snapshot.sha256),
            adapter.load_rules(contract_path),
            schema_path,
            temporary_dir / "data.sqlite",
        )
        canonical_sha256, canonical_count = canonical_table_hash(
            sqlite_artifact.path, adapter.table
        )
        if canonical_count != sqlite_artifact.record_count:
            raise RuntimeError("canonical hash row count differs from SQLite validation")
        compressed_sha256, compressed_size = compress_sqlite(
            sqlite_artifact.path, temporary_dir / "data.sqlite.zst"
        )
        validation_sha256, _ = write_json_atomic(
            temporary_dir / "validation.json",
            {
                "schemaVersion": 1,
                "passed": True,
                **adapter.validation_payload(sqlite_artifact.validation),
            },
        )
        diff_sha256, _ = write_json_atomic(
            temporary_dir / "diff.json",
            {
                "schemaVersion": 1,
                "baseRelease": None,
                "targetRelease": release_id,
                "baseSourceSha256": None,
                "targetSourceSha256": snapshot.sha256,
                "added": sqlite_artifact.record_count,
                "removed": 0,
                "modified": 0,
                "unchanged": 0,
            },
        )
        manifest = build_xlsx_manifest(
            contract=contract,
            workbook_config=workbook_config,
            inspection=inspection,
            sqlite_artifact=sqlite_artifact,
            compressed_sha256=compressed_sha256,
            compressed_size=compressed_size,
            validation_sha256=validation_sha256,
            diff_sha256=diff_sha256,
            canonical_sha256=canonical_sha256,
            release_id=release_id,
            storage_key=storage_key,
            source_version=source_version,
            build_revision=build_revision,
            sequence=sequence,
            created_at=created_at,
            git_commit=resolved_commit,
            contract_path=contract_path,
            workbook_path=workbook_path,
            schema_path=schema_path,
            lock_path=lock_path,
        )
        validate_manifest(manifest, repo_root / "schemas" / "manifest.schema.json")
        write_json_atomic(temporary_dir / "manifest.json", manifest)
        sync_directory(temporary_dir)
        os.replace(temporary_dir, release_dir)
        sync_directory(releases_dir)
        return CandidateBuild(release_dir, release_dir / "manifest.json", manifest)
    finally:
        if temporary_dir.exists():
            shutil.rmtree(temporary_dir)


def build_xlsx_manifest[ReportT: RecordCountReport](
    *,
    contract: dict[str, Any],
    workbook_config: WorkbookConfig,
    inspection: WorkbookInspection,
    sqlite_artifact: SQLiteArtifact[ReportT],
    compressed_sha256: str,
    compressed_size: int,
    validation_sha256: str,
    diff_sha256: str,
    canonical_sha256: str,
    release_id: str,
    storage_key: str,
    source_version: str,
    build_revision: int,
    sequence: int,
    created_at: datetime,
    git_commit: str,
    contract_path: Path,
    workbook_path: Path,
    schema_path: Path,
    lock_path: Path,
) -> dict[str, Any]:
    contract_sha256, _ = hash_file(contract_path)
    config_sha256, _ = hash_file(workbook_path)
    schema_sha256, _ = hash_file(schema_path)
    lock_sha256, _ = hash_file(lock_path)
    authority = cast(dict[str, Any], contract["authority"])
    source = cast(dict[str, Any], contract["source"])
    rights = cast(dict[str, Any], contract["rights"])
    runtime = cast(dict[str, Any], contract["runtime"])
    build_input_sha256 = hashlib.sha256(
        rfc8785.dumps(
            {
                "sourceSha256": inspection.snapshot.sha256,
                "datasetContractSha256": contract_sha256,
                "datasetSchemaSha256": schema_sha256,
                "configSha256": config_sha256,
                "lockSha256": lock_sha256,
                "gitCommit": git_commit,
                "adapterVersion": workbook_config.version,
            }
        )
    ).hexdigest()
    created_at_text = (
        created_at.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    authority_verification = str(authority["verification"])
    return {
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
            "id": str(contract["id"]),
            "sourceVersion": source_version,
            "datasetSchemaVersion": 1,
            "status": str(contract["status"]),
        },
        "sources": [
            {
                "authority": str(authority["name"]),
                "authorityRole": str(authority["role"]),
                "authorityVerified": not authority_verification.startswith("pending"),
                "format": str(source["type"]),
                "acquisition": str(source["acquisition"]),
                "originalFilename": inspection.snapshot.original_filename,
                "sourceUrl": None,
                "acquiredAt": None,
                "publishedAt": None,
                "dataAsOf": source_version,
                "sha256": inspection.snapshot.sha256,
                "sizeBytes": inspection.snapshot.size_bytes,
                "worksheet": workbook_config.workbook.canonical_sheet,
                "recordCount": inspection.data_rows,
                "columnCount": len(inspection.headers),
                "containerMetadata": {
                    "zipEntryCount": workbook_config.container.expected_zip_entries,
                    "uncompressedSizeBytes": (
                        workbook_config.container.expected_uncompressed_size_bytes
                    ),
                },
                "retention": "private-content-addressed",
                "sourceReacquirable": False,
                "reproducibleFromSource": True,
            }
        ],
        "compiler": {
            "name": "cn-health-compiler",
            "version": __version__,
            "adapter": str(contract["id"]),
            "adapterVersion": workbook_config.version,
            "gitCommit": git_commit,
            "lockSha256": lock_sha256,
            "configSha256": config_sha256,
            "datasetContractSha256": contract_sha256,
            "datasetSchemaSha256": schema_sha256,
            "buildInputSha256": build_input_sha256,
            "pythonVersion": platform.python_version(),
            "sqliteVersion": sqlite3.sqlite_version,
            "zstandardVersion": zstandard.__version__,
        },
        "canonical": {
            "serialization": "canonical-ndjson-v1",
            "recordCount": sqlite_artifact.record_count,
            "sha256": canonical_sha256,
        },
        "artifacts": [
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
                "sha256": compressed_sha256,
                "sizeBytes": compressed_size,
                "uncompressedName": "data.sqlite",
                "uncompressedSha256": sqlite_artifact.sha256,
                "uncompressedSizeBytes": sqlite_artifact.size_bytes,
            },
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


def canonical_table_hash(database_path: Path, table: str) -> tuple[str, int]:
    if _SQL_IDENTIFIER_PATTERN.fullmatch(table) is None:
        raise ValueError(f"unsafe SQLite table name: {table!r}")
    digest = hashlib.sha256()
    connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    try:
        columns = tuple(row[1] for row in connection.execute(f"PRAGMA table_info({table})"))
        column_list = ", ".join(columns)
        record_count = 0
        for row in connection.execute(f"SELECT {column_list} FROM {table} ORDER BY code"):
            digest.update(rfc8785.dumps(dict(zip(columns, row, strict=True))))
            digest.update(b"\n")
            record_count += 1
        return digest.hexdigest(), record_count
    finally:
        connection.close()


def compress_sqlite(source_path: Path, output_path: Path) -> tuple[str, int]:
    compressor = zstandard.ZstdCompressor(
        level=19, threads=0, write_checksum=True, write_content_size=True
    )
    with source_path.open("rb") as source, output_path.open("wb") as output:
        compressor.copy_stream(source, output, size=source_path.stat().st_size)
        output.flush()
        os.fsync(output.fileno())
    return hash_file(output_path)


def resolve_git_commit(repo_root: Path, supplied_commit: str | None) -> str:
    if supplied_commit is not None:
        if _GIT_COMMIT_PATTERN.fullmatch(supplied_commit) is None:
            raise ValueError("git_commit must be a full lowercase commit SHA")
        return supplied_commit
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    if status.stdout:
        raise DirtyRepositoryError("refusing to build from a dirty Git worktree")
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()


def sync_directory(path: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        return
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
