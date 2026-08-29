"""Deterministic SQLite builder for Chinese geography data."""

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from cn_health_compiler.core.sqlite import SQLiteArtifact, build_sqlite_database
from cn_health_compiler.sources.geography.records import (
    AdministrativeDivisionRecord,
    GeographyPlaceRecord,
    GeographyPostalAreaRecord,
)
from cn_health_compiler.sources.geography.validation import (
    GeographyValidationReport,
    GeographyValidationRules,
    validate_geography_records,
)


def _place_values(record: GeographyPlaceRecord) -> tuple[object, ...]:
    return (
        record.code,
        record.geoname_id,
        record.name_zh,
        record.name_ascii,
        record.alternate_names_zh,
        record.kind,
        record.feature_code,
        record.country_code,
        record.admin1_code,
        record.admin2_code,
        record.admin3_code,
        record.admin4_code,
        record.latitude,
        record.longitude,
        record.population,
        record.timezone,
        record.modified_on,
        record.source_row,
        record.source_version,
        record.source_sha256,
    )


def _division_values(record: AdministrativeDivisionRecord) -> tuple[object, ...]:
    return (
        record.code,
        record.parent_code,
        record.level,
        record.name_zh,
        record.short_name_zh,
        record.pinyin,
        record.pinyin_prefix,
        record.external_code,
        record.source_row,
        record.source_version,
        record.source_sha256,
    )


def _postal_values(record: GeographyPostalAreaRecord) -> tuple[object, ...]:
    return (
        record.code,
        record.postal_code,
        record.place_name,
        record.admin1_name,
        record.admin1_code,
        record.admin2_name,
        record.admin2_code,
        record.admin3_name,
        record.admin3_code,
        record.latitude,
        record.longitude,
        record.accuracy,
        record.source_row,
        record.source_version,
        record.source_sha256,
    )


def build_geography_sqlite(
    places: Iterable[GeographyPlaceRecord],
    postal_areas: Iterable[GeographyPostalAreaRecord],
    rules: GeographyValidationRules,
    schema_path: Path,
    output_path: Path,
    *,
    administrative_divisions: Iterable[AdministrativeDivisionRecord] = (),
) -> SQLiteArtifact[GeographyValidationReport]:
    division_records = list(administrative_divisions)
    place_records = list(places)
    postal_records = list(postal_areas)
    report = validate_geography_records(division_records, place_records, postal_records, rules)

    def populate(connection: sqlite3.Connection) -> GeographyValidationReport:
        connection.executemany(
            """INSERT INTO administrative_division (
                code, parent_code, level, name_zh, short_name_zh, pinyin,
                pinyin_prefix, external_code, source_row, source_version, source_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _division_values(record)
                for record in sorted(division_records, key=lambda item: item.code)
            ),
        )
        connection.executemany(
            """INSERT INTO place (
                code, geoname_id, name_zh, name_ascii, alternate_names_zh, kind,
                feature_code, country_code, admin1_code, admin2_code, admin3_code,
                admin4_code, latitude, longitude, population, timezone, modified_on,
                source_row, source_version, source_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (_place_values(record) for record in sorted(place_records, key=lambda item: item.code)),
        )
        connection.executemany(
            """INSERT INTO postal_area (
                code, postal_code, place_name, admin1_name, admin1_code, admin2_name,
                admin2_code, admin3_name, admin3_code, latitude, longitude, accuracy,
                source_row, source_version, source_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _postal_values(record)
                for record in sorted(postal_records, key=lambda item: item.code)
            ),
        )
        connection.execute("INSERT INTO place_fts(place_fts) VALUES('rebuild')")
        return report

    return build_sqlite_database(schema_path, output_path, populate)
