import hashlib
import sqlite3
from pathlib import Path

import pytest
from cn_health_compiler.core.source import SourceSnapshot
from cn_health_compiler.core.workbook import WorkbookConfig, WorkbookInspection
from cn_health_compiler.sources.nhc_icd10.records import (
    SOURCE_HEADERS,
    RawDiagnosisRow,
    iter_raw_diagnosis_rows,
    normalize_raw_diagnosis_row,
)
from cn_health_compiler.sources.nhc_icd10.sqlite import build_diagnosis_sqlite
from cn_health_compiler.sources.nhc_icd10.validation import (
    DiagnosisRecordValidator,
    DiagnosisValidationError,
    DiagnosisValidationRules,
)
from openpyxl import Workbook

REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE_SHA256 = "b" * 64
CODE_PATTERN = r"^(?:†?[A-Z][0-9]{2}(?:\.[0-9x]{1,3})?(?:x[0-9]{3})?[†*]?|M[0-9]{5}/[0-9])$"


def _raw_row(
    source_row: int,
    main_code: str | None,
    additional_code: str | None,
    name: str,
) -> RawDiagnosisRow:
    return RawDiagnosisRow.from_values(source_row, [main_code, additional_code, name])


def _record(
    source_row: int,
    main_code: str | None,
    additional_code: str | None,
    name: str,
):
    return normalize_raw_diagnosis_row(
        _raw_row(source_row, main_code, additional_code, name),
        source_version="2022",
        source_sha256=SOURCE_SHA256,
    )


def _rules() -> DiagnosisValidationRules:
    return DiagnosisValidationRules.model_validate(
        {
            "source": {
                "sha256": SOURCE_SHA256,
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
                "pattern": CODE_PATTERN,
                "allowed_lengths": [4, 6, 7, 8, 11],
            },
        }
    )


def test_diagnosis_normalization_uses_main_or_additional_code() -> None:
    main = _record(2, " A01.001† ", "K77.0*", " 伤寒性肝炎 ")
    additional_only = _record(3, None, " B95.000 ", "A族链球菌感染")

    assert main.code == "A01.001†"
    assert main.main_code == "A01.001†"
    assert main.additional_code == "K77.0*"
    assert main.name == "伤寒性肝炎"
    assert additional_only.code == "B95.000"
    assert additional_only.main_code is None


def test_diagnosis_validator_and_sqlite_support_all_code_forms(tmp_path: Path) -> None:
    records = [
        _record(2, "A00.000", None, "霍乱"),
        _record(3, "A01.001†", "K77.0*", "伤寒性肝炎"),
        _record(4, None, "M80000/0", "良性肿瘤"),
    ]
    output = tmp_path / "diagnosis.sqlite"

    artifact = build_diagnosis_sqlite(
        records,
        _rules(),
        REPO_ROOT / "datasets/nhc-icd10-clinical/schema.sql",
        output,
    )

    assert artifact.validation.record_count == 3
    connection = sqlite3.connect(f"file:{output}?mode=ro", uri=True)
    try:
        assert connection.execute("SELECT code FROM diagnosis ORDER BY rowid").fetchall() == [
            ("A00.000",),
            ("A01.001†",),
            ("M80000/0",),
        ]
        assert connection.execute(
            "SELECT count(*) FROM diagnosis_fts WHERE diagnosis_fts MATCH '伤寒性肝炎'"
        ).fetchone() == (1,)
    finally:
        connection.close()


def test_diagnosis_validator_rejects_duplicate_effective_code() -> None:
    validator = DiagnosisRecordValidator(_rules())
    validator.consume(_record(2, "A00.000", None, "霍乱"))

    with pytest.raises(DiagnosisValidationError, match="duplicate code A00.000"):
        validator.consume(_record(3, None, "A00.000", "重复霍乱"))


def test_iter_raw_diagnosis_rows_streams_three_columns(tmp_path: Path) -> None:
    source = tmp_path / "diagnosis.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "总表"
    sheet.append(SOURCE_HEADERS)
    sheet.append(("A00.000", None, "霍乱"))
    workbook.save(source)
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    snapshot = SourceSnapshot(source, source_sha256, source.stat().st_size, source.name)
    config = WorkbookConfig.model_validate(
        {
            "version": 1,
            "source": {"filename": source.name, "sha256": source_sha256, "size_bytes": 1},
            "workbook": {
                "required_sheets": ["总表"],
                "canonical_sheet": "总表",
                "resolve_external_links": False,
            },
            "container": {
                "expected_zip_entries": 0,
                "expected_uncompressed_size_bytes": 0,
                "max_uncompressed_size_bytes": 0,
                "reject_macros": True,
            },
            "sheet": {
                "dimension": "A1:C2",
                "header_row": 1,
                "first_data_row": 2,
                "expected_data_rows": 1,
                "expected_formula_cells": 0,
                "headers": SOURCE_HEADERS,
            },
        }
    )
    inspection = WorkbookInspection(snapshot, ("总表",), "A1:C2", SOURCE_HEADERS, 1, 0)

    rows = list(iter_raw_diagnosis_rows(inspection, config))

    assert rows == [_raw_row(2, "A00.000", None, "霍乱")]
