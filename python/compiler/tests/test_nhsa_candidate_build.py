import hashlib
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path
from zipfile import ZipFile

import polars as pl
import yaml
import zstandard
from _nhsa import source_values
from cn_health_compiler.cli import app
from cn_health_compiler.sources.nhsa_drugs.records import SOURCE_HEADERS
from jsonschema import Draft202012Validator, FormatChecker
from openpyxl import Workbook
from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[3]


def _write_fixture_repository(root: Path) -> tuple[Path, str]:
    dataset_dir = root / "datasets" / "nhsa-drugs"
    schema_dir = root / "schemas"
    source_dir = root / "tmp"
    dataset_dir.mkdir(parents=True)
    schema_dir.mkdir()
    source_dir.mkdir()
    shutil.copyfile(
        REPO_ROOT / "datasets" / "nhsa-drugs" / "schema.sql",
        dataset_dir / "schema.sql",
    )
    shutil.copyfile(
        REPO_ROOT / "schemas" / "manifest.schema.json",
        schema_dir / "manifest.schema.json",
    )
    (root / "uv.lock").write_text("synthetic lock\n", encoding="utf-8")
    (root / ".gitignore").write_text("tmp/\n.work/\ndist/\n", encoding="utf-8")

    source_path = source_dir / "drugs.xlsx"
    workbook = Workbook()
    total = workbook.active
    total.title = "总表"
    total.append(SOURCE_HEADERS)
    total.append(source_values(code="XA02", registered_name="盐酸二甲双胍片"))
    total.append(source_values(code="XA01", registered_name="二甲双胍缓释片"))
    workbook.save(source_path)
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    with ZipFile(source_path) as archive:
        entries = archive.infolist()
        uncompressed_size = sum(entry.file_size for entry in entries)

    dataset_contract = {
        "id": "nhsa-drugs",
        "title": "测试药品",
        "description": "Synthetic NHSA drug fixture.",
        "status": "experimental",
        "authority": {
            "name": "测试机构",
            "role": "distribution-source",
            "verification": "fixture",
        },
        "source": {
            "type": "xlsx",
            "acquisition": "manual-local",
            "path_hint": "tmp/drugs.xlsx",
            "worksheet": "总表",
            "declared_data_as_of": "2026-01-09",
            "sha256": source_sha256,
            "size_bytes": source_path.stat().st_size,
            "upstream_sync": False,
        },
        "versioning": {"strategy": "declared-data-as-of"},
        "output": {"primary": "sqlite"},
        "runtime": {"searchable": True, "minimum_sqlite_version": "3.34.0"},
        "rights": {"redistribution": "review-required", "release_eligible": False},
        "validation": {
            "source": {
                "sha256": source_sha256,
                "worksheet": "总表",
                "header_columns": 26,
                "formula_cells": 0,
            },
            "record_count": {
                "baseline": 2,
                "min": 1,
                "max_relative_decrease": 0.05,
                "max_relative_increase": 0.10,
            },
            "required": ["code", "registered_name", "data_source", "market_status"],
            "max_null_rate": {
                "code": 0,
                "registered_name": 0,
                "data_source": 0,
                "market_status": 0,
            },
            "unique": ["code"],
            "code": {"pattern": "^[A-Z0-9]+$", "allowed_lengths": [4]},
            "allowed_values": {"market_status": ["上市", "停产", "未上市"]},
        },
    }
    workbook_contract = {
        "version": 1,
        "source": {
            "filename": source_path.name,
            "sha256": source_sha256,
            "size_bytes": source_path.stat().st_size,
        },
        "workbook": {
            "required_sheets": ["总表"],
            "canonical_sheet": "总表",
            "resolve_external_links": False,
        },
        "container": {
            "expected_zip_entries": len(entries),
            "expected_uncompressed_size_bytes": uncompressed_size,
            "max_uncompressed_size_bytes": uncompressed_size,
            "reject_macros": True,
        },
        "sheet": {
            "dimension": "A1:Z3",
            "header_row": 1,
            "first_data_row": 2,
            "expected_data_rows": 2,
            "expected_formula_cells": 0,
            "headers": SOURCE_HEADERS,
        },
    }
    (dataset_dir / "dataset.yaml").write_text(
        yaml.safe_dump(dataset_contract, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (dataset_dir / "workbook.yaml").write_text(
        yaml.safe_dump(workbook_contract, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    subprocess.run(["git", "init", "-b", "main", root], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", root, "config", "user.email", "fixture@example.invalid"], check=True
    )
    subprocess.run(["git", "-C", root, "config", "user.name", "Fixture"], check=True)
    subprocess.run(["git", "-C", root, "add", "."], check=True)
    subprocess.run(["git", "-C", root, "commit", "-m", "fixture"], check=True, capture_output=True)
    git_commit = subprocess.check_output(
        ["git", "-C", root, "rev-parse", "HEAD"], text=True
    ).strip()
    return source_path, git_commit


def test_build_command_creates_a_valid_local_candidate(tmp_path: Path) -> None:
    source_path, git_commit = _write_fixture_repository(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "build",
            "nhsa-drugs",
            "--source",
            str(source_path),
            "--repo-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    release_dir = tmp_path / "dist" / "nhsa-drugs" / "releases" / "2026-01-09.r1"
    assert sorted(path.name for path in release_dir.iterdir()) == [
        "data.parquet",
        "data.sqlite",
        "data.sqlite.zst",
        "diff.json",
        "manifest.json",
        "validation.json",
    ]
    manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
    schema = json.loads((tmp_path / "schemas" / "manifest.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(manifest)
    assert manifest["release"]["id"] == "nhsa-drugs@2026-01-09.r1"
    assert manifest["compiler"]["gitCommit"] == git_commit
    assert manifest["canonical"]["recordCount"] == 2
    assert pl.read_parquet(release_dir / "data.parquet").height == 2
    assert manifest["rights"] == {
        "redistribution": "review-required",
        "releaseEligible": False,
        "evidence": None,
    }
    assert json.loads((release_dir / "diff.json").read_text(encoding="utf-8"))["added"] == 2

    artifacts = {artifact["name"]: artifact for artifact in manifest["artifacts"]}
    sqlite_bytes = (release_dir / "data.sqlite").read_bytes()
    compressed_bytes = (release_dir / "data.sqlite.zst").read_bytes()
    assert artifacts["data.sqlite"]["sha256"] == hashlib.sha256(sqlite_bytes).hexdigest()
    assert artifacts["data.sqlite.zst"]["sha256"] == hashlib.sha256(compressed_bytes).hexdigest()
    assert zstandard.ZstdDecompressor().decompress(compressed_bytes) == sqlite_bytes

    connection = sqlite3.connect(f"file:{release_dir / 'data.sqlite'}?mode=ro", uri=True)
    try:
        assert connection.execute("SELECT code FROM drug ORDER BY rowid").fetchall() == [
            ("XA01",),
            ("XA02",),
        ]
    finally:
        connection.close()
