import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cn_health_compiler.core.dataset import load_yaml_mapping
from cn_health_compiler.sources.laboratory.build import build_laboratory_candidate
from cn_health_compiler.sources.laboratory.evidence import inspect_panel_evidence
from cn_health_compiler.sources.laboratory.records import (
    LaboratoryCatalog,
    load_laboratory_catalog,
)
from cn_health_compiler.sources.laboratory.validation import (
    LaboratoryValidationRules,
    validate_laboratory_catalog,
)
from cn_health_compiler.sources.nhc_lab.records import iter_nhc_laboratory_records

REPO_ROOT = Path(__file__).resolve().parents[3]
TERMINOLOGY_SOURCE = REPO_ROOT / "tmp/WST_886—2026.md"
PANEL_SOURCE = REPO_ROOT / "tmp/检验类医疗服务价格项目立项指南映射关系表.xlsx"
HAS_REAL_SOURCES = TERMINOLOGY_SOURCE.is_file() and PANEL_SOURCE.is_file()


def _real_catalog() -> tuple[LaboratoryCatalog, dict[int, str], LaboratoryValidationRules]:
    contract = load_yaml_mapping(REPO_ROOT / "datasets/laboratory-cn/dataset.yaml")
    source = contract["source"]
    terminology_records = tuple(
        iter_nhc_laboratory_records(
            TERMINOLOGY_SOURCE,
            source_version=source["terminology_version"],
            source_sha256=source["sha256"],
        )
    )
    terminology = {record.code: record for record in terminology_records}
    catalog = load_laboratory_catalog(
        REPO_ROOT / "datasets/laboratory-cn/runtime.csv",
        REPO_ROOT / "datasets/laboratory-cn/panels.csv",
        terminology,
        source_version=source["declared_version"],
    )
    evidence = inspect_panel_evidence(PANEL_SOURCE, source["panel_evidence"]["worksheet"])
    return catalog, evidence, LaboratoryValidationRules.model_validate(contract["validation"])


@pytest.mark.skipif(not HAS_REAL_SOURCES, reason="pinned local laboratory sources unavailable")
def test_real_catalog_meets_simulation_and_panel_baselines() -> None:
    catalog, evidence, rules = _real_catalog()
    report = validate_laboratory_catalog(
        catalog,
        rules,
        terminology_count=399,
        evidence_names=evidence,
    )

    assert report.record_count == 84
    assert report.reference_count == 96
    assert report.national_standard_reference_count == 11
    assert report.panel_count == 15
    assert report.panel_member_count == 88
    assert report.quantity_count == 69
    assert report.fixed_normal_count == 15


@pytest.mark.skipif(not HAS_REAL_SOURCES, reason="pinned local laboratory sources unavailable")
def test_real_candidate_builds_all_runtime_tables(tmp_path: Path) -> None:
    result = build_laboratory_candidate(
        REPO_ROOT,
        TERMINOLOGY_SOURCE,
        tmp_path,
        panel_source_path=PANEL_SOURCE,
        git_commit="d" * 40,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["release"]["id"] == "laboratory-cn@2026-09-01.r1"
    assert manifest["release"]["supersedes"] == "laboratory-cn@2026-08-30.r2"
    assert manifest["canonical"]["recordCount"] == 84
    assert {item["table"]: item["recordCount"] for item in manifest["canonical"]["tables"]} == {
        "laboratory_test": 84,
        "laboratory_reference": 96,
        "laboratory_panel": 15,
        "laboratory_panel_member": 88,
    }
    assert len(manifest["sources"]) == 4
    assert {item["name"] for item in manifest["artifacts"]} == {
        "data.sqlite",
        "data.sqlite.zst",
        "laboratory-tests.parquet",
        "laboratory-references.parquet",
        "laboratory-panels.parquet",
        "laboratory-panel-members.parquet",
    }

    with sqlite3.connect(result.release_dir / "data.sqlite") as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA application_id").fetchone() == (0x434E4844,)
        assert connection.execute("PRAGMA user_version").fetchone() == (2,)
        assert connection.execute(
            "SELECT name, unit_ucum, precision FROM laboratory_test WHERE code = '0100101A'"
        ).fetchone() == ("白细胞计数", "10*9/L", 1)
        assert connection.execute(
            "SELECT sex, low_value, high_value FROM laboratory_reference "
            "WHERE test_code = '0100201A' ORDER BY sex"
        ).fetchall() == [("female", 3.8, 5.1), ("male", 4.3, 5.8)]
        assert connection.execute(
            "SELECT test_code FROM laboratory_panel_member "
            "WHERE panel_code = 'CN-LAB-CBC-5DIFF' ORDER BY sort_order"
        ).fetchall()[0] == ("0100101A",)


@pytest.mark.skipif(not HAS_REAL_SOURCES, reason="pinned local laboratory sources unavailable")
def test_validation_rejects_missing_quantity_simulation_range() -> None:
    catalog, evidence, rules = _real_catalog()
    target = next(
        index
        for index, reference in enumerate(catalog.references)
        if reference.test_code == "0100101A"
    )
    references = list(catalog.references)
    references[target] = replace(references[target], simulation_low=None, simulation_high=None)
    invalid = replace(catalog, references=tuple(references))

    with pytest.raises(ValueError, match="has no simulation range"):
        validate_laboratory_catalog(
            invalid,
            rules,
            terminology_count=399,
            evidence_names=evidence,
        )
