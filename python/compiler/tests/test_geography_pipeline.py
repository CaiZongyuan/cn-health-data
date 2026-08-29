import sqlite3
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from cn_health_compiler.sources.geography.records import (
    GeoNamesFormatError,
    iter_area_city_divisions,
    iter_geonames_places,
    iter_geonames_postal_areas,
)
from cn_health_compiler.sources.geography.sqlite import build_geography_sqlite
from cn_health_compiler.sources.geography.validation import GeographyValidationRules

REPO_ROOT = Path(__file__).resolve().parents[3]


def _write_zip(path: Path, member: str, lines: list[str]) -> None:
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(member, "\n".join(lines) + "\n")


def _place_line(
    geoname_id: str,
    name: str,
    feature_class: str,
    feature_code: str,
    *,
    admin1: str = "04",
    admin2: str = "3205",
    population: str = "0",
) -> str:
    return "\t".join(
        [
            geoname_id,
            name,
            name,
            "",
            "31.865",
            "120.5389",
            feature_class,
            feature_code,
            "CN",
            "",
            admin1,
            admin2,
            "",
            "",
            population,
            "",
            "5",
            "Asia/Shanghai",
            "2026-08-29",
        ]
    )


def test_geonames_archives_build_searchable_geography_sqlite(tmp_path: Path) -> None:
    gazetteer = tmp_path / "gazetteer.zip"
    postal = tmp_path / "postal.zip"
    divisions_source = tmp_path / "area-city.csv"
    _write_zip(
        gazetteer,
        "CN.txt",
        [
            _place_line("1806260", "江苏省", "A", "ADM1", admin2=""),
            _place_line("1787331", "张家港市", "P", "PPLA3", population="1432044"),
            _place_line("9999999", "测试山", "T", "MT"),
        ],
    )
    divisions_source.write_text(
        "id,pid,deep,name,pinyin_prefix,pinyin,ext_id,ext_name\n"
        '32,0,0,"江苏","j","jiang su","320000000000","江苏省"\n'
        '3205,32,1,"苏州","s","su zhou","320500000000","苏州市"\n',
        encoding="utf-8-sig",
    )
    _write_zip(
        postal,
        "CN.txt",
        [
            "\t".join(
                [
                    "CN",
                    "215600",
                    "张家港市",
                    "江苏省",
                    "04",
                    "苏州市",
                    "3205",
                    "张家港市",
                    "",
                    "31.865",
                    "120.5389",
                    "4",
                ]
            )
        ],
    )

    places = list(
        iter_geonames_places(
            gazetteer,
            source_version="2026-08-29",
            source_sha256="a" * 64,
        )
    )
    postal_areas = list(
        iter_geonames_postal_areas(
            postal,
            source_version="2026-08-29",
            source_sha256="b" * 64,
        )
    )
    divisions = list(
        iter_area_city_divisions(
            divisions_source,
            source_version="2025.251231.260403",
            source_sha256="c" * 64,
        )
    )

    assert [place.code for place in places] == ["geonames:1806260", "geonames:1787331"]
    assert places[1].population == 1_432_044
    assert postal_areas[0].postal_code == "215600"

    artifact = build_geography_sqlite(
        places,
        postal_areas,
        GeographyValidationRules(min_place_count=2, min_postal_count=1),
        REPO_ROOT / "datasets/geography-cn/schema.sql",
        tmp_path / "data.sqlite",
        administrative_divisions=divisions,
    )

    assert artifact.validation.administrative_division_count == 2
    assert artifact.validation.place_count == 2
    assert artifact.validation.postal_count == 1
    connection = sqlite3.connect(f"file:{artifact.path}?mode=ro", uri=True)
    try:
        assert connection.execute(
            "SELECT name_zh FROM administrative_division WHERE code = ?",
            ("3205",),
        ).fetchone() == ("苏州市",)
        assert connection.execute(
            "SELECT name_zh, population FROM populated_place WHERE code = ?",
            ("geonames:1787331",),
        ).fetchone() == ("张家港市", 1_432_044)
        assert connection.execute(
            "SELECT postal_code FROM postal_area WHERE place_name = ?",
            ("张家港市",),
        ).fetchone() == ("215600",)
        assert connection.execute(
            "SELECT count(*) FROM place_fts WHERE place_fts MATCH '张家港市'"
        ).fetchone() == (1,)
    finally:
        connection.close()


def test_geonames_parser_rejects_a_non_china_record(tmp_path: Path) -> None:
    source = tmp_path / "gazetteer.zip"
    line = _place_line("1787331", "张家港市", "P", "PPLA3").replace("\tCN\t", "\tUS\t")
    _write_zip(source, "CN.txt", [line])

    with pytest.raises(GeoNamesFormatError, match="country code"):
        list(
            iter_geonames_places(
                source,
                source_version="2026-08-29",
                source_sha256="a" * 64,
            )
        )


def test_area_city_parser_removes_non_china_and_filler_divisions(tmp_path: Path) -> None:
    source = tmp_path / "area-city.csv"
    source.write_text(
        "id,pid,deep,name,pinyin_prefix,pinyin,ext_id,ext_name\n"
        '44,0,0,"广东","g","guang dong","440000000000","广东省"\n'
        '4419,44,1,"东莞","d","dong guan","441900000000","东莞市"\n'
        '441900,4419,2,"东莞","d","dong guan","441900000000","东莞市"\n'
        '91,0,0,"国外","g","guo wai","0","国外"\n',
        encoding="utf-8-sig",
    )

    records = list(
        iter_area_city_divisions(
            source,
            source_version="2025.251231.260403",
            source_sha256="c" * 64,
        )
    )

    assert [(record.code, record.parent_code, record.name_zh) for record in records] == [
        ("44", None, "广东省"),
        ("4419", "44", "东莞市"),
    ]
    assert records[1].external_code == "441900000000"


def test_area_city_parser_keeps_direct_administered_city_at_shallow_level(
    tmp_path: Path,
) -> None:
    source = tmp_path / "direct-city.csv"
    source.write_text(
        "id,pid,deep,name,pinyin_prefix,pinyin,ext_id,ext_name\n"
        '41,0,0,"河南","h","he nan","410000000000","河南省"\n'
        '419001,41,1,"济源","j","ji yuan","419001000000","济源市"\n'
        '419001000,419001,2,"济源","j","ji yuan","419001000000","济源市"\n',
        encoding="utf-8-sig",
    )

    records = list(
        iter_area_city_divisions(
            source,
            source_version="2025.251231.260403",
            source_sha256="c" * 64,
        )
    )

    assert [(record.code, record.level) for record in records] == [("41", 0), ("419001", 1)]
