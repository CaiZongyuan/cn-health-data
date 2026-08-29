import hashlib
import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

import polars as pl
import yaml
import zstandard
from cn_health_compiler.sources.nhc_icd10.build import build_diagnosis_candidate
from cn_health_compiler.sources.nhc_icd10.records import SOURCE_HEADERS
from jsonschema import Draft202012Validator, FormatChecker
from openpyxl import Workbook

REPO_ROOT = Path(__file__).resolve().parents[3]


def _fixture_repository(root: Path) -> Path:
    dataset_dir = root / "datasets" / "nhc-icd10-clinical"
    schema_dir = root / "schemas"
    source_dir = root / "tmp"
    dataset_dir.mkdir(parents=True)
    schema_dir.mkdir()
    source_dir.mkdir()
    shutil.copyfile(
        REPO_ROOT / "datasets/nhc-icd10-clinical/schema.sql", dataset_dir / "schema.sql"
    )
    shutil.copyfile(REPO_ROOT / "schemas/manifest.schema.json", schema_dir / "manifest.schema.json")
    (root / "uv.lock").write_text("fixture lock\n", encoding="utf-8")

    source_path = source_dir / "diagnosis.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "总表"
    sheet.append(SOURCE_HEADERS)
    sheet.append(("A00.000", None, "霍乱"))
    sheet.append(("A01.001†", "K77.0*", "伤寒性肝炎"))
    sheet.append((None, "M80000/0", "良性肿瘤"))
    workbook.save(source_path)
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    with ZipFile(source_path) as archive:
        entries = archive.infolist()
        uncompressed_size = sum(item.file_size for item in entries)

    contract = {
        "id": "nhc-icd10-clinical",
        "title": "测试疾病分类",
        "description": "Synthetic diagnosis fixture.",
        "status": "experimental",
        "authority": {
            "name": "测试机构",
            "role": "original-authority",
            "verification": "fixture",
        },
        "source": {
            "type": "xlsx",
            "acquisition": "manual-local",
            "path_hint": "tmp/diagnosis.xlsx",
            "worksheet": "总表",
            "declared_version": "2022",
            "sha256": source_sha256,
            "size_bytes": source_path.stat().st_size,
            "upstream_sync": False,
        },
        "versioning": {"strategy": "declared-source-version"},
        "output": {"primary": "sqlite"},
        "runtime": {"searchable": True, "minimum_sqlite_version": "3.34.0"},
        "rights": {"redistribution": "review-required", "release_eligible": False},
        "validation": {
            "source": {
                "sha256": source_sha256,
                "worksheet": "总表",
                "header_columns": 3,
                "formula_cells": 0,
            },
            "record_count": {
                "baseline": 3,
                "min": 3,
                "max_relative_decrease": 0.02,
                "max_relative_increase": 0.05,
            },
            "required": ["code", "name"],
            "max_null_rate": {"code": 0, "name": 0},
            "unique": ["code"],
            "code": {
                "pattern": (
                    r"^(?:†?[A-Z][0-9]{2}(?:\.[0-9x]{1,3})?"
                    r"(?:x[0-9]{3})?[†*]?|M[0-9]{5}/[0-9])$"
                ),
                "allowed_lengths": [4, 6, 7, 8, 11],
            },
        },
    }
    workbook_config = {
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
            "dimension": "A1:C4",
            "header_row": 1,
            "first_data_row": 2,
            "expected_data_rows": 3,
            "expected_formula_cells": 0,
            "headers": SOURCE_HEADERS,
        },
    }
    (dataset_dir / "dataset.yaml").write_text(
        yaml.safe_dump(contract, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (dataset_dir / "workbook.yaml").write_text(
        yaml.safe_dump(workbook_config, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return source_path


def test_build_diagnosis_candidate_packages_manifest_and_zstd(tmp_path: Path) -> None:
    source_path = _fixture_repository(tmp_path)

    result = build_diagnosis_candidate(
        repo_root=tmp_path,
        source_path=source_path,
        output_root=tmp_path / "dist",
        git_commit="c" * 40,
        created_at=datetime(2026, 8, 29, tzinfo=UTC),
    )

    release = result.release_dir
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    schema = json.loads((tmp_path / "schemas/manifest.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(manifest)
    assert manifest["release"]["id"] == "nhc-icd10-clinical@2022.r1"
    assert manifest["canonical"]["recordCount"] == 3
    assert pl.read_parquet(release / "data.parquet").height == 3
    assert manifest["rights"]["releaseEligible"] is False
    sqlite_bytes = (release / "data.sqlite").read_bytes()
    compressed = (release / "data.sqlite.zst").read_bytes()
    assert zstandard.ZstdDecompressor().decompress(compressed) == sqlite_bytes
    connection = sqlite3.connect(f"file:{release / 'data.sqlite'}?mode=ro", uri=True)
    try:
        assert connection.execute("SELECT count(*) FROM diagnosis").fetchone() == (3,)
        assert connection.execute(
            "SELECT count(*) FROM diagnosis_fts WHERE diagnosis_fts MATCH '伤寒性肝炎'"
        ).fetchone() == (1,)
    finally:
        connection.close()

    revision = build_diagnosis_candidate(
        repo_root=tmp_path,
        source_path=source_path,
        output_root=tmp_path / "dist",
        build_revision=2,
        sequence=2,
        base_release_dir=release,
        git_commit="c" * 40,
        created_at=datetime(2026, 8, 30, tzinfo=UTC),
    )
    revision_manifest = json.loads(revision.manifest_path.read_text(encoding="utf-8"))
    revision_diff = json.loads((revision.release_dir / "diff.json").read_text(encoding="utf-8"))
    assert revision_manifest["release"]["supersedes"] == "nhc-icd10-clinical@2022.r1"
    assert revision_diff["unchanged"] == 3
    assert revision_diff["added"] == revision_diff["removed"] == 0
