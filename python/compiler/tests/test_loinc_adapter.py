import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
import yaml
from _loinc import (
    PANEL_MEMBER,
    UNIT_MEMBER,
    csv_bytes,
    fixture_repository,
    source_members,
)
from cn_health_compiler.core.dataset import load_yaml_mapping
from cn_health_compiler.sources.loinc.adapter import LoincAdapterError, read_loinc_package
from cn_health_compiler.sources.loinc.layout import LoincLayout
from cn_health_compiler.sources.loinc.sqlite import build_loinc_sqlite
from cn_health_compiler.sources.loinc.validation import LoincValidationRules
from pydantic import ValidationError


def test_complete_package_joins_and_builds_canonical_sqlite(tmp_path: Path) -> None:
    fixture = fixture_repository(tmp_path)
    layout = LoincLayout.load(tmp_path / "datasets/loinc-zh-cn/layout.yaml")
    records = read_loinc_package(
        fixture.core_archive,
        fixture.translation_archive,
        layout,
        source_version="fixture-1",
        core_source_sha256=hashlib.sha256(fixture.core_archive.read_bytes()).hexdigest(),
        translation_source_sha256=hashlib.sha256(
            fixture.translation_archive.read_bytes()
        ).hexdigest(),
    )

    assert [record.code for record in records.concepts] == ["1000-0", "1001-8", "1002-6"]
    assert records.concepts[1].zh_display == "合成分析物:质量浓度:时间点:血液:定量"
    assert records.concepts[2].zh_display is None
    assert json.loads(records.concepts[1].source_metadata_json) == {"commonTestRank": "20"}
    assert json.loads(records.concepts[1].translation_metadata_json)["system"] == "血液"
    assert [record.ucum_unit for record in records.units] == [
        "mg/dL",
        "mg/dL",
        "mm[Hg]",
        "10*9/L",
    ]
    assert records.specimens[0].part_number == "LP-SYS-1"
    assert records.panel_members[0].member_code == "1001-8"

    contract = load_yaml_mapping(tmp_path / "datasets/loinc-zh-cn/dataset.yaml")
    rules = LoincValidationRules.model_validate(contract["validation"])
    database = tmp_path / "loinc.sqlite"
    artifact = build_loinc_sqlite(
        records,
        rules,
        tmp_path / "datasets/loinc-zh-cn/schema.sql",
        database,
    )

    assert artifact.validation.record_count == 9
    assert artifact.validation.translated_count == 1
    assert artifact.validation.translation_coverage.ratio == "0.333333"
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        assert connection.execute("PRAGMA user_version").fetchone() == (2,)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute(
            "SELECT code, long_common_name, zh_display FROM loinc WHERE code = '1002-6'"
        ).fetchone() == (
            "1002-6",
            "Synthetic cells in Blood by Automated count",
            None,
        )
        assert connection.execute(
            "SELECT count(*) FROM loinc_fts WHERE loinc_fts MATCH '合成分析物'"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT code FROM loinc_search_bigram WHERE term = '合成' ORDER BY code LIMIT 2"
        ).fetchall() == [("1001-8",)]
    finally:
        connection.close()


def test_layout_rejects_unexplained_source_column(tmp_path: Path) -> None:
    fixture_repository(tmp_path)
    layout_path = tmp_path / "datasets/loinc-zh-cn/layout.yaml"
    raw = yaml.safe_load(layout_path.read_text(encoding="utf-8"))
    raw["core"]["headers"].append("UNEXPLAINED")

    with pytest.raises(ValidationError, match="not mapped or ignored"):
        LoincLayout.model_validate(raw)


def test_adapter_rejects_unsafe_archive_member(tmp_path: Path) -> None:
    fixture = fixture_repository(tmp_path, extra_core_members={"../escape.csv": b"unsafe\n"})
    layout = LoincLayout.load(tmp_path / "datasets/loinc-zh-cn/layout.yaml")

    with pytest.raises(LoincAdapterError, match="unsafe ZIP member path"):
        read_loinc_package(
            fixture.core_archive,
            fixture.translation_archive,
            layout,
            source_version="fixture-1",
            core_source_sha256="a" * 64,
            translation_source_sha256="b" * 64,
        )


def test_adapter_accepts_safe_archive_directory_entry(tmp_path: Path) -> None:
    fixture = fixture_repository(tmp_path, extra_core_members={"Metadata/": b""})
    layout = LoincLayout.load(tmp_path / "datasets/loinc-zh-cn/layout.yaml")

    records = read_loinc_package(
        fixture.core_archive,
        fixture.translation_archive,
        layout,
        source_version="fixture-1",
        core_source_sha256="a" * 64,
        translation_source_sha256="b" * 64,
    )

    assert len(records.concepts) == 3


def test_adapter_rejects_invalid_ucum(tmp_path: Path) -> None:
    members = source_members()
    members[UNIT_MEMBER] = csv_bytes(
        ("LOINC_NUM", "UCUM", "SOURCE_VERSION", "NOTE"),
        [("1001-8", "not a unit", "fixture-1", "invalid")],
    )
    fixture = fixture_repository(tmp_path, member_overrides={UNIT_MEMBER: members[UNIT_MEMBER]})
    layout = LoincLayout.load(tmp_path / "datasets/loinc-zh-cn/layout.yaml")

    with pytest.raises(LoincAdapterError, match="invalid UCUM"):
        read_loinc_package(
            fixture.core_archive,
            fixture.translation_archive,
            layout,
            source_version="fixture-1",
            core_source_sha256="a" * 64,
            translation_source_sha256="b" * 64,
        )


def test_adapter_rejects_unknown_panel_member(tmp_path: Path) -> None:
    invalid_panel = csv_bytes(
        (
            "PARENT_ID",
            "MEMBER_ID",
            "PANEL_LOINC_NUM",
            "MEMBER_LOINC_NUM",
            "SEQUENCE",
            "RELATIONSHIP",
            "MEMBER_TYPE",
            "CARDINALITY",
        ),
        [
            (
                "parent-1",
                "member-1",
                "1000-0",
                "9999-9",
                "1",
                "COMPONENT",
                "LOINC",
                "1..1",
            )
        ],
    )
    fixture = fixture_repository(tmp_path, member_overrides={PANEL_MEMBER: invalid_panel})
    layout = LoincLayout.load(tmp_path / "datasets/loinc-zh-cn/layout.yaml")

    with pytest.raises(LoincAdapterError, match="unknown LOINC code"):
        read_loinc_package(
            fixture.core_archive,
            fixture.translation_archive,
            layout,
            source_version="fixture-1",
            core_source_sha256="a" * 64,
            translation_source_sha256="b" * 64,
        )
