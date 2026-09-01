"""End-to-end Candidate build for complete official LOINC Chinese packages."""

import hashlib
import json
import os
import platform
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from zipfile import ZipFile

import polars as pl
import rfc8785
import zstandard
from ucumvert import __version__ as ucumvert_version  # type: ignore[import-untyped]

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
from cn_health_compiler.core.diff import compare_sqlite_tables, enforce_relative_record_count
from cn_health_compiler.core.manifest import validate_manifest, write_json_atomic
from cn_health_compiler.core.source import SourceSnapshot, hash_file, snapshot_local_source
from cn_health_compiler.sources.loinc.adapter import read_loinc_package
from cn_health_compiler.sources.loinc.layout import LoincLayout
from cn_health_compiler.sources.loinc.sqlite import build_loinc_sqlite
from cn_health_compiler.sources.loinc.validation import (
    LoincValidationRules,
    SourceMemberReport,
)

_TABLES = (
    (
        "loinc",
        "loinc.parquet",
        ("code",),
        (
            "source_row",
            "translation_source_row",
            "source_version",
            "core_source_sha256",
            "translation_source_sha256",
        ),
    ),
    (
        "loinc_unit",
        "loinc-units.parquet",
        ("loinc_code", "unit_kind", "source_member", "source_row", "unit_ordinal"),
        ("source_member", "source_row", "source_sha256"),
    ),
    (
        "loinc_specimen",
        "loinc-specimens.parquet",
        ("loinc_code", "part_number", "link_type"),
        ("source_member", "source_row", "source_sha256"),
    ),
    (
        "loinc_panel_member",
        "loinc-panel-members.parquet",
        ("parent_id", "member_id"),
        ("source_member", "source_row", "source_sha256"),
    ),
)


def build_loinc_candidate(
    repo_root: Path,
    core_source_path: Path,
    translation_source_path: Path | None,
    output_root: Path,
    *,
    build_revision: int = 1,
    sequence: int = 1,
    git_commit: str | None = None,
    created_at: datetime | None = None,
    base_release_dir: Path | None = None,
) -> CandidateBuild:
    repo_root = repo_root.resolve(strict=True)
    dataset_dir = repo_root / "datasets/loinc-zh-cn"
    contract_path = dataset_dir / "dataset.yaml"
    layout_path = dataset_dir / "layout.yaml"
    schema_path = dataset_dir / "schema.sql"
    lock_path = repo_root / "uv.lock"
    contract = load_yaml_mapping(contract_path)
    _validate_ready_contract(contract, layout_path)
    layout = LoincLayout.load(layout_path)
    source = cast(dict[str, Any], contract["source"])
    if source["package_mode"] != layout.package_mode:
        raise ValueError("LOINC package mode differs between Dataset Contract and layout")
    source_version = str(source["declared_version"])
    storage_key = f"{source_version}.r{build_revision}"
    release_id = f"loinc-zh-cn@{storage_key}"
    resolved_commit = resolve_git_commit(repo_root, git_commit)
    timestamp = created_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise ValueError("created_at must be timezone-aware")

    releases_dir = output_root / "loinc-zh-cn/releases"
    with candidate_staging_directory(releases_dir, storage_key) as (temporary_dir, release_dir):
        snapshots_dir = repo_root / ".work/sources"
        core_config = _source_config(contract, "core")
        core_snapshot = _snapshot(core_source_path, core_config, snapshots_dir)
        if str(core_config["declared_version"]) != source_version:
            raise ValueError("LOINC core version differs from the source-set version")

        if layout.package_mode == "split":
            if translation_source_path is None:
                raise ValueError("split LOINC source set requires --translation-source")
            translation_config = _source_config(contract, "linguistic_variant")
            translation_snapshot = _snapshot(
                translation_source_path, translation_config, snapshots_dir
            )
            if str(translation_config["target_version"]) != source_version:
                raise ValueError("LOINC linguistic-variant target version differs from core")
        else:
            if translation_source_path is not None:
                raise ValueError("combined LOINC source set does not accept --translation-source")
            translation_config = _source_config(contract, "linguistic_variant")
            _validate_combined_source_configs(core_config, translation_config)
            translation_snapshot = core_snapshot
            if str(translation_config["target_version"]) != source_version:
                raise ValueError("LOINC linguistic-variant target version differs from core")

        records = read_loinc_package(
            core_snapshot.path,
            translation_snapshot.path if layout.package_mode == "split" else None,
            layout,
            source_version=source_version,
            core_source_sha256=core_snapshot.sha256,
            translation_source_sha256=translation_snapshot.sha256,
        )
        rules = LoincValidationRules.model_validate(contract["validation"])
        sqlite_artifact = build_loinc_sqlite(
            records,
            rules,
            schema_path,
            temporary_dir / "data.sqlite",
        )
        canonical_sha256, canonical_count, canonical_tables = _canonical_identity(
            sqlite_artifact.path
        )
        if canonical_count != sqlite_artifact.validation.record_count:
            raise RuntimeError("canonical hash row count differs from LOINC validation")
        compressed_sha256, compressed_size = compress_sqlite(
            sqlite_artifact.path, temporary_dir / "data.sqlite.zst"
        )
        license_artifacts, short_license_sha256 = _write_license_artifacts(
            core_snapshot,
            layout,
            dataset_dir / "LOINC_short_license.txt",
            temporary_dir,
        )

        rights = cast(dict[str, Any], contract["rights"])
        allowed_artifacts = set(cast(list[str], rights["allowed_artifact_types"]))
        parquet_artifacts: list[dict[str, object]] = []
        if "parquet" in allowed_artifacts:
            for table, filename, key_fields, _ in _TABLES:
                parquet_sha256, parquet_size = write_parquet(
                    sqlite_artifact.path,
                    table,
                    temporary_dir / filename,
                    order_by=key_fields,
                )
                parquet_artifacts.append(
                    _artifact(
                        filename,
                        "application/vnd.apache.parquet",
                        parquet_sha256,
                        parquet_size,
                    )
                )
        validation_sha256, _ = write_json_atomic(
            temporary_dir / "validation.json",
            {
                "schemaVersion": 1,
                "passed": True,
                **sqlite_artifact.validation.model_dump(mode="json", by_alias=True),
            },
        )
        source_hashes = {
            "core": core_snapshot.sha256,
            "linguistic-variant": translation_snapshot.sha256,
        }
        source_set_sha256 = _source_set_sha256(source_hashes)
        diff_payload, supersedes = _build_diff(
            database_path=sqlite_artifact.path,
            release_id=release_id,
            source_set_sha256=source_set_sha256,
            target_count=canonical_count,
            target_loinc_count=sqlite_artifact.validation.loinc_count,
            rules=rules,
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
                    "sourceSetSha256": source_set_sha256,
                    "datasetContractSha256": contract_sha256,
                    "datasetSchemaSha256": schema_sha256,
                    "configSha256": layout_sha256,
                    "shortLicenseSha256": short_license_sha256,
                    "lockSha256": lock_sha256,
                    "gitCommit": resolved_commit,
                    "adapterVersion": layout.version,
                }
            )
        ).hexdigest()
        sources = _source_manifests(
            contract,
            layout,
            core_snapshot,
            translation_snapshot,
            sqlite_artifact.validation.source_members,
            source_version,
        )
        compiler: dict[str, object] = {
            "name": "cn-health-compiler",
            "version": __version__,
            "adapter": "loinc-zh-cn",
            "adapterVersion": layout.version,
            "gitCommit": resolved_commit,
            "lockSha256": lock_sha256,
            "configSha256": layout_sha256,
            "datasetContractSha256": contract_sha256,
            "datasetSchemaSha256": schema_sha256,
            "buildInputSha256": build_input_sha256,
            "pythonVersion": platform.python_version(),
            "sqliteVersion": sqlite3.sqlite_version,
            "polarsVersion": pl.__version__,
            "zstandardVersion": zstandard.__version__,
            "ucumvertVersion": ucumvert_version,
        }
        canonical: dict[str, object] = {
            "serialization": "canonical-table-hashes-v1",
            "recordCount": canonical_count,
            "sha256": canonical_sha256,
            "tables": canonical_tables,
        }
        artifacts: list[dict[str, object]] = [
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
            *license_artifacts,
        ]
        manifest = build_candidate_manifest(
            contract=contract,
            dataset_id="loinc-zh-cn",
            source_version=source_version,
            release_id=release_id,
            storage_key=storage_key,
            build_revision=build_revision,
            sequence=sequence,
            created_at=timestamp,
            supersedes=supersedes,
            sources=sources,
            compiler=compiler,
            canonical=canonical,
            artifacts=artifacts,
            validation_sha256=validation_sha256,
            diff_sha256=diff_sha256,
        )
        validate_manifest(manifest, repo_root / "schemas/manifest.schema.json")
        write_json_atomic(temporary_dir / "manifest.json", manifest)
        return CandidateBuild(release_dir, release_dir / "manifest.json")


def _validate_ready_contract(contract: dict[str, Any], layout_path: Path) -> None:
    if contract.get("status") == "planned" or not layout_path.is_file():
        raise ValueError(
            "loinc-zh-cn source intake is incomplete: official version, layout, hashes, "
            "counts, and rights must be pinned before building"
        )
    if int(contract.get("dataset_schema_version", 0)) != 2:
        raise ValueError("loinc-zh-cn requires dataset_schema_version 2")
    source = cast(dict[str, Any], contract["source"])
    required_source_fields = {"package_mode", "declared_version", "core", "linguistic_variant"}
    missing_source_fields = required_source_fields - set(source)
    if missing_source_fields:
        raise ValueError(f"LOINC source contract is incomplete: {sorted(missing_source_fields)}")
    rights = cast(dict[str, Any], contract["rights"])
    required_rights = {
        "basis",
        "evidence",
        "attribution",
        "reviewed_by",
        "reviewed_at",
        "allowed_artifact_types",
    }
    missing_rights = required_rights - set(rights)
    if missing_rights:
        raise ValueError(f"LOINC rights review is incomplete: {sorted(missing_rights)}")
    allowed_artifacts = set(cast(list[str], rights["allowed_artifact_types"]))
    if not {"sqlite", "sqlite-zstd"}.issubset(allowed_artifacts):
        raise ValueError("LOINC Candidate requires local sqlite and sqlite-zstd artifact types")


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


def _write_license_artifacts(
    core_snapshot: SourceSnapshot,
    layout: LoincLayout,
    short_license_path: Path,
    output_dir: Path,
) -> tuple[list[dict[str, object]], str]:
    with ZipFile(core_snapshot.path) as archive:
        license_bytes = archive.read(layout.license.member)
    if len(license_bytes) != layout.license.uncompressed_size_bytes:
        raise ValueError("LOINC license member size changed")
    license_sha256 = hashlib.sha256(license_bytes).hexdigest()
    if license_sha256 != layout.license.uncompressed_sha256:
        raise ValueError("LOINC license member SHA256 changed")
    license_output = output_dir / "license.txt"
    license_output.write_bytes(license_bytes)
    _sync_file(license_output)

    short_license_output = output_dir / "LOINC_short_license.txt"
    shutil.copyfile(short_license_path, short_license_output)
    _sync_file(short_license_output)
    short_license_sha256, short_license_size = hash_file(short_license_output)
    return (
        [
            _artifact(
                "license.txt",
                "text/plain; charset=utf-8",
                license_sha256,
                len(license_bytes),
            ),
            _artifact(
                "LOINC_short_license.txt",
                "text/plain; charset=utf-8",
                short_license_sha256,
                short_license_size,
            ),
        ],
        short_license_sha256,
    )


def _sync_file(path: Path) -> None:
    with path.open("rb") as artifact:
        os.fsync(artifact.fileno())


def _canonical_identity(database_path: Path) -> tuple[str, int, list[dict[str, str | int]]]:
    tables: list[dict[str, str | int]] = []
    total_count = 0
    for table, _, key_fields, _ in _TABLES:
        sha256, count = canonical_table_hash(database_path, table, order_by=key_fields)
        tables.append({"table": table, "recordCount": count, "sha256": sha256})
        total_count += count
    digest = hashlib.sha256(rfc8785.dumps({"tables": tables})).hexdigest()
    return digest, total_count, tables


def _source_set_sha256(source_hashes: dict[str, str]) -> str:
    return hashlib.sha256(rfc8785.dumps(source_hashes)).hexdigest()


def _manifest_source_set_sha256(manifest: dict[str, Any]) -> str:
    source_hashes: dict[str, str] = {}
    for source in cast(list[dict[str, Any]], manifest["sources"]):
        for role in cast(list[str], source["roles"]):
            source_hashes[role] = str(source["sha256"])
    expected_roles = {"core", "linguistic-variant"}
    if set(source_hashes) != expected_roles:
        raise ValueError("base LOINC Manifest has an unexpected source set")
    return _source_set_sha256(source_hashes)


def _build_diff(
    *,
    database_path: Path,
    release_id: str,
    source_set_sha256: str,
    target_count: int,
    target_loinc_count: int,
    rules: LoincValidationRules,
    base_release_dir: Path | None,
) -> tuple[dict[str, object], str | None]:
    if base_release_dir is None:
        return (
            {
                "schemaVersion": 1,
                "baseRelease": None,
                "targetRelease": release_id,
                "baseSourceSha256": None,
                "targetSourceSha256": source_set_sha256,
                "added": target_count,
                "removed": 0,
                "modified": 0,
                "unchanged": 0,
                "modifiedFields": {},
                "tables": [
                    {
                        "table": table,
                        "added": _table_count(database_path, table),
                        "removed": 0,
                        "modified": 0,
                        "unchanged": 0,
                    }
                    for table, _, _, _ in _TABLES
                ],
            },
            None,
        )

    base_release_dir = base_release_dir.resolve(strict=True)
    base_manifest = cast(
        dict[str, Any],
        json.loads((base_release_dir / "manifest.json").read_text(encoding="utf-8")),
    )
    dataset = cast(dict[str, Any], base_manifest["dataset"])
    if dataset["id"] != "loinc-zh-cn":
        raise ValueError("base Release belongs to a different Dataset")
    if dataset["datasetSchemaVersion"] != 2:
        raise ValueError("cross-schema LOINC Diff is not supported")
    artifacts = cast(list[dict[str, Any]], base_manifest["artifacts"])
    base_artifact = next(
        (artifact for artifact in artifacts if artifact["name"] == "data.sqlite"), None
    )
    if base_artifact is None:
        raise ValueError("base LOINC Manifest has no SQLite artifact")
    base_database = base_release_dir / "data.sqlite"
    base_sha256, _ = hash_file(base_database)
    if base_sha256 != base_artifact["sha256"]:
        raise ValueError("base Release SQLite SHA256 does not match its Manifest")

    totals = {"added": 0, "removed": 0, "modified": 0, "unchanged": 0}
    modified_fields: dict[str, int] = {}
    table_reports: list[dict[str, object]] = []
    base_loinc_count = 0
    for table, _, key_fields, excluded_fields in _TABLES:
        report = compare_sqlite_tables(
            base_database,
            database_path,
            table,
            key_fields=key_fields,
            excluded_fields=excluded_fields,
        )
        if table == "loinc":
            base_loinc_count = report.base_count
        for key in totals:
            totals[key] += getattr(report, key)
        modified_fields.update(
            {f"{table}.{field}": count for field, count in report.modified_fields}
        )
        table_reports.append(
            {
                "table": table,
                "added": report.added,
                "removed": report.removed,
                "modified": report.modified,
                "unchanged": report.unchanged,
            }
        )
    if rules.record_count is not None:
        enforce_relative_record_count(
            base_loinc_count,
            target_loinc_count,
            max_decrease=rules.record_count.max_relative_decrease,
            max_increase=rules.record_count.max_relative_increase,
        )
    release = cast(dict[str, Any], base_manifest["release"])
    base_release_id = str(release["id"])
    return (
        {
            "schemaVersion": 1,
            "baseRelease": base_release_id,
            "targetRelease": release_id,
            "baseSourceSha256": _manifest_source_set_sha256(base_manifest),
            "targetSourceSha256": source_set_sha256,
            **totals,
            "modifiedFields": modified_fields,
            "tables": table_reports,
        },
        base_release_id,
    )


def _table_count(database_path: Path, table: str) -> int:
    connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    try:
        row = connection.execute(f"SELECT count(*) FROM {table}").fetchone()
        if row is None:
            raise RuntimeError(f"failed to count {table}")
        return int(row[0])
    finally:
        connection.close()


def _source_manifests(
    contract: dict[str, Any],
    layout: LoincLayout,
    core_snapshot: SourceSnapshot,
    translation_snapshot: SourceSnapshot,
    source_members: tuple[SourceMemberReport, ...],
    source_version: str,
) -> list[dict[str, object]]:
    serialized_members = [
        member.model_dump(mode="json", by_alias=True) for member in source_members
    ]
    if layout.package_mode == "combined":
        return [
            _source_manifest(
                contract,
                _source_config(contract, "core"),
                core_snapshot,
                ["core", "linguistic-variant"],
                serialized_members,
                source_version,
            )
        ]
    return [
        _source_manifest(
            contract,
            _source_config(contract, "core"),
            core_snapshot,
            ["core"],
            [
                member.model_dump(mode="json", by_alias=True)
                for member in source_members
                if member.archive_role == "core"
            ],
            source_version,
        ),
        _source_manifest(
            contract,
            _source_config(contract, "linguistic_variant"),
            translation_snapshot,
            ["linguistic-variant"],
            [
                member.model_dump(mode="json", by_alias=True)
                for member in source_members
                if member.archive_role == "linguistic-variant"
            ],
            source_version,
        ),
    ]


def _source_manifest(
    contract: dict[str, Any],
    config: dict[str, Any],
    snapshot: SourceSnapshot,
    roles: list[str],
    members: list[dict[str, object]],
    source_version: str,
) -> dict[str, object]:
    authority = cast(dict[str, Any], contract["authority"])
    source = cast(dict[str, Any], contract["source"])
    return {
        "authority": str(config.get("authority", authority["name"])),
        "authorityRole": str(config.get("authority_role", authority["role"])),
        "authorityVerified": not str(authority["verification"]).startswith("pending"),
        "roles": roles,
        "format": str(config.get("format", "zip")),
        "acquisition": str(config.get("acquisition", source["acquisition"])),
        "originalFilename": snapshot.original_filename,
        "sourceUrl": config.get("source_url"),
        "dataAsOf": source_version,
        "sha256": snapshot.sha256,
        "sizeBytes": snapshot.size_bytes,
        "members": members,
        "retention": "private-content-addressed",
        "sourceReacquirable": bool(config.get("source_reacquirable", False)),
        "reproducibleFromSource": True,
    }


def _validate_combined_source_configs(
    core_config: dict[str, Any],
    translation_config: dict[str, Any],
) -> None:
    for field in ("sha256", "size_bytes", "original_filename"):
        if translation_config.get(field) != core_config.get(field):
            raise ValueError(
                f"combined LOINC source roles disagree on physical source field {field}"
            )
