import gzip
import sqlite3
from pathlib import Path

import pytest
from cn_health_compiler.sources.population.records import WppFormatError, iter_wpp_age_sex_records
from cn_health_compiler.sources.population.sqlite import build_population_sqlite
from cn_health_compiler.sources.population.validation import PopulationValidationRules

REPO_ROOT = Path(__file__).resolve().parents[3]

HEADERS = (
    "SortOrder,LocID,Notes,ISO3_code,ISO2_code,SDMX_code,LocTypeID,LocTypeName,"
    "ParentID,Location,VarID,Variant,Time,MidPeriod,AgeGrp,AgeGrpStart,AgeGrpSpan,"
    "PopMale,PopFemale,PopTotal"
)


def _row(age: str, start: int, span: int, male: str, female: str, total: str) -> str:
    return ",".join(
        (
            "134",
            "156",
            "5",
            "CHN",
            "CN",
            "156",
            "4",
            "Country/Area",
            "906",
            "China",
            "2",
            "Medium",
            "2026",
            "2026.5",
            age,
            str(start),
            str(span),
            male,
            female,
            total,
        )
    )


def _source(path: Path, *, inconsistent_total: bool = False) -> None:
    rows = [
        _row("0-4", 0, 5, "23.125", "21.250", "44.375"),
        _row("100+", 100, -1, "0.004", "0.048", "0.052"),
    ]
    if inconsistent_total:
        rows[0] = _row("0-4", 0, 5, "23.125", "21.250", "99.000")
    with gzip.open(path, "wt", encoding="utf-8-sig", newline="") as stream:
        stream.write(HEADERS + "\n" + "\n".join(rows) + "\n")


def test_wpp_age_sex_source_builds_population_sqlite(tmp_path: Path) -> None:
    source = tmp_path / "population.csv.gz"
    _source(source)

    records = list(
        iter_wpp_age_sex_records(
            source,
            source_version="WPP2024",
            source_sha256="a" * 64,
        )
    )

    assert [(record.age_start, record.age_end) for record in records] == [(0, 4), (100, None)]
    assert records[0].male_population == 23_125
    assert records[0].female_population == 21_250
    assert records[0].total_population == 44_375

    artifact = build_population_sqlite(
        records,
        PopulationValidationRules(
            expected_age_group_count=2,
            min_record_count=2,
            min_year_count=1,
        ),
        REPO_ROOT / "datasets/population-cn/schema.sql",
        tmp_path / "data.sqlite",
    )

    assert artifact.validation.year_count == 1
    connection = sqlite3.connect(f"file:{artifact.path}?mode=ro", uri=True)
    try:
        assert connection.execute(
            "SELECT total_population FROM population_age_sex WHERE year = 2026 AND age_start = 100"
        ).fetchone() == (52,)
    finally:
        connection.close()


def test_wpp_age_sex_source_rejects_inconsistent_total(tmp_path: Path) -> None:
    source = tmp_path / "population.csv.gz"
    _source(source, inconsistent_total=True)

    with pytest.raises(WppFormatError, match="male and female"):
        list(
            iter_wpp_age_sex_records(
                source,
                source_version="WPP2024",
                source_sha256="a" * 64,
            )
        )
