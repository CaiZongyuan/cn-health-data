"""Deterministic SQLite builder for Chinese geography data."""

import os
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from tempfile import NamedTemporaryFile

from cn_health_compiler.core.source import hash_file
from cn_health_compiler.core.sqlite import SQLiteArtifact, apply_schema
from cn_health_compiler.sources.geography.records import (
    GeographyPlaceRecord,
    GeographyPostalAreaRecord,
)
from cn_health_compiler.sources.geography.validation import (
    GeographyValidationReport,
    GeographyValidationRules,
    validate_geography_records,
)

_APPLICATION_ID = 0x434E4844


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
) -> SQLiteArtifact[GeographyValidationReport]:
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite SQLite artifact: {output_path}")
    place_records = list(places)
    postal_records = list(postal_areas)
    report = validate_geography_records(place_records, postal_records, rules)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        dir=output_path.parent,
        prefix=f".{output_path.name}-",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        connection = sqlite3.connect(temporary_path)
        try:
            connection.execute("PRAGMA page_size = 4096")
            connection.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
            connection.execute("PRAGMA user_version = 1")
            connection.execute("PRAGMA journal_mode = DELETE")
            connection.execute("PRAGMA synchronous = FULL")
            apply_schema(connection, schema_path)
            connection.execute("BEGIN IMMEDIATE")
            connection.executemany(
                """INSERT INTO place (
                    code, geoname_id, name_zh, name_ascii, alternate_names_zh, kind,
                    feature_code, country_code, admin1_code, admin2_code, admin3_code,
                    admin4_code, latitude, longitude, population, timezone, modified_on,
                    source_row, source_version, source_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    _place_values(record)
                    for record in sorted(place_records, key=lambda item: item.code)
                ),
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
            connection.commit()
            connection.execute("ANALYZE")
            connection.execute("PRAGMA optimize")
            connection.commit()
            connection.execute("VACUUM")
            if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise RuntimeError("SQLite integrity_check failed")
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        with temporary_path.open("rb") as artifact:
            os.fsync(artifact.fileno())
        os.replace(temporary_path, output_path)
        digest, size_bytes = hash_file(output_path)
        return SQLiteArtifact(output_path, digest, size_bytes, report)
    finally:
        temporary_path.unlink(missing_ok=True)
        for suffix in ("-journal", "-wal", "-shm"):
            Path(f"{temporary_path}{suffix}").unlink(missing_ok=True)
