import sqlite3
from pathlib import Path

import pytest
from cn_health_compiler.sources.names.records import (
    FakerNamesFormatError,
    parse_faker_name_components,
)
from cn_health_compiler.sources.names.sqlite import build_names_sqlite
from cn_health_compiler.sources.names.validation import NamesValidationRules

REPO_ROOT = Path(__file__).resolve().parents[3]


def _provider_source(path: Path, *, dynamic_surnames: bool = False) -> None:
    surname_value = (
        "load_surnames()" if dynamic_surnames else 'OrderedDict((("王", 7.17), ("欧阳", 0.068)))'
    )
    path.write_text(
        "from collections import OrderedDict\n\n"
        "class Provider:\n"
        '    first_names_male = ["伟", "安宁"]\n'
        '    first_names_female = ["芳", "安宁"]\n'
        "    first_names = first_names_male + first_names_female\n"
        f"    last_names = {surname_value}\n",
        encoding="utf-8",
    )


def test_faker_provider_builds_weighted_searchable_name_components(tmp_path: Path) -> None:
    source = tmp_path / "faker-person.py"
    _provider_source(source)

    records = list(
        parse_faker_name_components(
            source,
            source_version="40.37.0",
            source_sha256="a" * 64,
        )
    )

    assert [(record.kind, record.gender, record.text) for record in records] == [
        ("surname", "any", "王"),
        ("surname", "any", "欧阳"),
        ("given-name", "male", "伟"),
        ("given-name", "male", "安宁"),
        ("given-name", "female", "芳"),
        ("given-name", "female", "安宁"),
    ]
    assert records[0].weight == 7.17
    assert records[1].is_compound is True

    artifact = build_names_sqlite(
        records,
        NamesValidationRules(
            min_surname_count=2,
            min_male_given_count=2,
            min_female_given_count=2,
        ),
        REPO_ROOT / "datasets/names-cn/schema.sql",
        tmp_path / "data.sqlite",
    )

    assert artifact.validation.record_count == 6
    assert artifact.validation.deduplicated_surname_count == 0
    connection = sqlite3.connect(f"file:{artifact.path}?mode=ro", uri=True)
    try:
        assert connection.execute(
            "SELECT text, weight FROM surname WHERE text = '王'"
        ).fetchone() == ("王", 7.17)
        assert connection.execute(
            "SELECT gender FROM given_name WHERE text = '安宁' ORDER BY gender"
        ).fetchall() == [("female",), ("male",)]
    finally:
        connection.close()


def test_faker_provider_rejects_dynamic_name_data(tmp_path: Path) -> None:
    source = tmp_path / "faker-person.py"
    _provider_source(source, dynamic_surnames=True)

    with pytest.raises(FakerNamesFormatError, match="literal OrderedDict"):
        list(
            parse_faker_name_components(
                source,
                source_version="40.37.0",
                source_sha256="a" * 64,
            )
        )


def test_faker_provider_matches_ordered_dict_duplicate_semantics(tmp_path: Path) -> None:
    source = tmp_path / "faker-person.py"
    source.write_text(
        "from collections import OrderedDict\n\n"
        "class Provider:\n"
        '    first_names_male = ["伟"]\n'
        '    first_names_female = ["芳"]\n'
        '    last_names = OrderedDict((("于", 0.48), ("王", 7.17), ("于", 0.0074)))\n',
        encoding="utf-8",
    )

    records = list(
        parse_faker_name_components(
            source,
            source_version="40.37.0",
            source_sha256="a" * 64,
        )
    )

    assert [(record.text, record.weight) for record in records[:2]] == [
        ("于", 0.0074),
        ("王", 7.17),
    ]
    assert records[0].source_duplicate is True
