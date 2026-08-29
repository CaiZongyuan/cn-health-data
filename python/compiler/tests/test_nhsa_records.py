from hashlib import sha256
from pathlib import Path

import pytest
from cn_health_compiler.core.source import SourceSnapshot
from cn_health_compiler.sources.nhsa_drugs.records import (
    SOURCE_HEADERS,
    RawDrugRow,
    RecordNormalizationError,
    iter_raw_drug_rows,
    normalize_raw_drug_row,
)
from cn_health_compiler.sources.nhsa_drugs.validation import (
    DrugRecordValidator,
    DrugValidationError,
    DrugValidationRules,
)
from cn_health_compiler.sources.nhsa_drugs.workbook import (
    NhsaDrugWorkbookConfig,
    WorkbookInspection,
)
from openpyxl import Workbook


def _source_values(*, code: str = "XA01") -> list[str | None]:
    return [
        code,
        "第一批",
        "测试药品",
        "无",
        "片剂",
        "片剂",
        "0.5g",
        "0.5g",
        "铝塑",
        "10",
        "片",
        "盒",
        "测试药品企业",
        None,
        "测试生产企业",
        "国药准字TEST",
        None,
        "86900000000000",
        None,
        "上市",
        "测试药品",
        "乙",
        "口服常释剂型",
        "1",
        None,
        "OLD01",
    ]


def _raw_row(*, source_row: int = 2, code: str = "XA01") -> RawDrugRow:
    return RawDrugRow.from_values(source_row, _source_values(code=code))


def _rules(*, baseline: int = 2) -> DrugValidationRules:
    return DrugValidationRules.model_validate(
        {
            "source": {
                "sha256": "a" * 64,
                "worksheet": "总表",
                "header_columns": 26,
                "formula_cells": 0,
            },
            "record_count": {
                "baseline": baseline,
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
        }
    )


def test_iter_raw_drug_rows_maps_the_declared_columns(tmp_path: Path) -> None:
    source_path = tmp_path / "drugs.xlsx"
    workbook = Workbook()
    total = workbook.active
    total.title = "总表"
    total.append(SOURCE_HEADERS)
    total.append(_source_values())
    workbook.save(source_path)
    source_sha256 = sha256(source_path.read_bytes()).hexdigest()
    snapshot = SourceSnapshot(
        path=source_path,
        sha256=source_sha256,
        size_bytes=source_path.stat().st_size,
        original_filename=source_path.name,
    )
    config = NhsaDrugWorkbookConfig.model_validate(
        {
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
                "expected_zip_entries": 0,
                "expected_uncompressed_size_bytes": 0,
                "max_uncompressed_size_bytes": 0,
                "reject_macros": True,
            },
            "sheet": {
                "dimension": "A1:Z2",
                "header_row": 1,
                "first_data_row": 2,
                "expected_data_rows": 1,
                "expected_formula_cells": 0,
                "headers": SOURCE_HEADERS,
            },
        }
    )
    inspection = WorkbookInspection(
        snapshot=snapshot,
        sheet_names=("总表",),
        dimension="A1:Z2",
        headers=SOURCE_HEADERS,
        data_rows=1,
        formula_cells=0,
    )

    records = list(iter_raw_drug_rows(inspection, config))

    assert len(records) == 1
    assert records[0].source_row == 2
    assert records[0].code == "XA01"
    assert records[0].registered_name == "测试药品"
    assert records[0].former_code == "OLD01"


def test_normalize_raw_drug_row_preserves_literals_and_normalizes_text() -> None:
    values = _source_values(code="  XA01\t")
    values[2] = "  Cafe\u0301  "
    values[13] = "   "
    raw = RawDrugRow.from_values(2, values)

    record = normalize_raw_drug_row(raw, source_version="2026-01-09", source_sha256="a" * 64)

    assert record.code == "XA01"
    assert record.registered_name == "Café"
    assert record.trade_name == "无"
    assert record.repackaging_company is None
    assert record.source_row == 2
    assert record.source_version == "2026-01-09"


def test_normalize_raw_drug_row_rejects_missing_required_text() -> None:
    values = _source_values()
    values[2] = " "

    with pytest.raises(RecordNormalizationError, match="registered_name is required"):
        normalize_raw_drug_row(
            RawDrugRow.from_values(2, values),
            source_version="2026-01-09",
            source_sha256="a" * 64,
        )


def test_streaming_validator_accepts_valid_records() -> None:
    validator = DrugRecordValidator(_rules())
    records = [
        normalize_raw_drug_row(_raw_row(code="XA01"), "2026-01-09", "a" * 64),
        normalize_raw_drug_row(_raw_row(source_row=3, code="XA02"), "2026-01-09", "a" * 64),
    ]

    for record in records:
        validator.consume(record)
    report = validator.finish()

    assert report.record_count == 2
    assert report.unique_codes == 2
    assert dict(report.market_status_counts) == {"上市": 2}


def test_streaming_validator_rejects_duplicate_code() -> None:
    validator = DrugRecordValidator(_rules())
    validator.consume(normalize_raw_drug_row(_raw_row(code="XA01"), "2026-01-09", "a" * 64))

    with pytest.raises(DrugValidationError, match="duplicate code XA01"):
        validator.consume(
            normalize_raw_drug_row(_raw_row(source_row=3, code="XA01"), "2026-01-09", "a" * 64)
        )


def test_streaming_validator_rejects_invalid_code_and_record_count() -> None:
    validator = DrugRecordValidator(_rules())

    with pytest.raises(DrugValidationError, match="invalid code"):
        validator.consume(normalize_raw_drug_row(_raw_row(code="xa01"), "2026-01-09", "a" * 64))

    with pytest.raises(DrugValidationError, match="record count"):
        DrugRecordValidator(_rules(baseline=2)).finish()
