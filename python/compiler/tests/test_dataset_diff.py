from pathlib import Path

import pytest
from _nhsa import drug_record, validation_rules
from cn_health_compiler.core.diff import (
    RecordCountChangeError,
    compare_sqlite_tables,
    enforce_relative_record_count,
)
from cn_health_compiler.sources.nhsa_drugs.sqlite import build_drug_sqlite

REPO_ROOT = Path(__file__).resolve().parents[3]
EXCLUDED_FIELDS = ("source_row", "source_version", "source_sha256")


def test_compare_sqlite_tables_reports_added_removed_and_modified_fields(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base.sqlite"
    target = tmp_path / "target.sqlite"
    schema = REPO_ROOT / "datasets/nhsa-drugs/schema.sql"
    build_drug_sqlite(
        [drug_record("XA01", 2, "旧名称"), drug_record("XA02", 3, "删除记录")],
        validation_rules(),
        schema,
        base,
    )
    build_drug_sqlite(
        [drug_record("XA01", 20, "新名称"), drug_record("XA03", 30, "新增记录")],
        validation_rules(),
        schema,
        target,
    )

    report = compare_sqlite_tables(base, target, "drug", excluded_fields=EXCLUDED_FIELDS)

    assert report.added == 1
    assert report.removed == 1
    assert report.modified == 1
    assert report.unchanged == 0
    assert dict(report.modified_fields) == {"registered_name": 1}


def test_relative_record_count_gate_fails_closed() -> None:
    with pytest.raises(RecordCountChangeError, match="decreased"):
        enforce_relative_record_count(100, 90, max_decrease=0.05, max_increase=0.10)

    with pytest.raises(RecordCountChangeError, match="increased"):
        enforce_relative_record_count(100, 120, max_decrease=0.05, max_increase=0.10)

    enforce_relative_record_count(100, 104, max_decrease=0.05, max_increase=0.10)
