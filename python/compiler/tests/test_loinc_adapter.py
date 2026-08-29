import sqlite3
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from cn_health_compiler.sources.loinc.adapter import (
    LoincArchiveConfig,
    iter_loinc_records,
)
from cn_health_compiler.sources.loinc.sqlite import build_loinc_sqlite

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_loinc_zip_joins_chinese_variant_and_builds_searchable_sqlite(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "loinc.zip"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as package:
        package.writestr(
            "Loinc.csv",
            "LOINC_NUM,COMPONENT,PROPERTY,TIME_ASPCT,SYSTEM,SCALE_TYP,METHOD_TYP,LONG_COMMON_NAME,STATUS\n"
            "4548-4,Hemoglobin A1c,MCnc,Pt,Bld,Qn,,"
            "Hemoglobin A1c/Hemoglobin.total in Blood,ACTIVE\n"
            "718-7,Hemoglobin,MCnc,Pt,Bld,Qn,,Hemoglobin in Blood,ACTIVE\n",
        )
        package.writestr(
            "zh.csv",
            "LOINC_NUM,DISPLAY\n4548-4,糖化血红蛋白\n",
        )
    config = LoincArchiveConfig(
        loinc_member="Loinc.csv",
        translation_member="zh.csv",
        translation_display_column="DISPLAY",
    )

    records = list(iter_loinc_records(archive, config, "fixture", "d" * 64))

    assert [record.code for record in records] == ["4548-4", "718-7"]
    assert records[0].zh_display == "糖化血红蛋白"
    assert records[1].zh_display is None
    database = tmp_path / "loinc.sqlite"
    build_loinc_sqlite(
        records,
        REPO_ROOT / "datasets/loinc-zh-cn/schema.sql",
        database,
        expected_count=2,
    )
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        assert connection.execute(
            "SELECT count(*) FROM loinc_fts WHERE loinc_fts MATCH '糖化血红蛋白'"
        ).fetchone() == (1,)
    finally:
        connection.close()
