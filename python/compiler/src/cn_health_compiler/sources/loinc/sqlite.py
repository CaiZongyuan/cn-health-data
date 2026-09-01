"""Deterministic multi-table SQLite construction for complete LOINC packages."""

import sqlite3
from dataclasses import astuple
from pathlib import Path

from cn_health_compiler.core.sqlite import SQLiteArtifact, build_sqlite_database
from cn_health_compiler.sources.loinc.records import LoincPackageRecords, LoincRecord
from cn_health_compiler.sources.loinc.validation import (
    LoincValidationReport,
    LoincValidationRules,
    validate_loinc_package,
)


def build_loinc_sqlite(
    records: LoincPackageRecords,
    rules: LoincValidationRules,
    schema_path: Path,
    output_path: Path,
) -> SQLiteArtifact[LoincValidationReport]:
    report = validate_loinc_package(records, rules)

    def populate(connection: sqlite3.Connection) -> LoincValidationReport:
        connection.executemany(
            """INSERT INTO loinc (
                code, component, property, time_aspect, system, scale_type, method_type,
                long_common_name, short_name, consumer_name, class, class_type, order_obs,
                status, status_reason, status_text, change_type, definition_description,
                version_first_released, version_last_changed, panel_type, zh_display,
                source_metadata_json, translation_metadata_json, source_row,
                translation_source_row, source_version,
                core_source_sha256, translation_source_sha256
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?
            )""",
            (_concept_values(record) for record in records.concepts),
        )
        connection.executemany(
            """INSERT INTO loinc_unit (
                loinc_code, ucum_unit, unit_kind, unit_ordinal, source_member,
                source_row, source_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (astuple(record) for record in records.units),
        )
        connection.executemany(
            """INSERT INTO loinc_specimen (
                loinc_code, part_number, part_name, part_display_name, link_type,
                source_member, source_row, source_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (astuple(record) for record in records.specimens),
        )
        connection.executemany(
            """INSERT INTO loinc_panel_member (
                parent_id, member_id, panel_code, member_code, member_order, relationship,
                source_metadata_json, source_member, source_row, source_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (astuple(record) for record in records.panel_members),
        )
        connection.execute(
            """INSERT INTO loinc_fts(rowid, long_common_name, zh_display)
            SELECT rowid, long_common_name, zh_display FROM loinc ORDER BY code"""
        )
        connection.execute(
            """WITH RECURSIVE searchable(code, text) AS (
                SELECT code, long_common_name FROM loinc
                UNION ALL SELECT code, zh_display FROM loinc WHERE zh_display IS NOT NULL
            ), grams(code, text, position) AS (
                SELECT code, text, 1 FROM searchable WHERE length(text) >= 2
                UNION ALL
                SELECT code, text, position + 1 FROM grams WHERE position < length(text) - 1
            )
            INSERT OR IGNORE INTO loinc_search_bigram(term, code)
            SELECT substr(text, position, 2), code FROM grams ORDER BY 1, 2"""
        )
        connection.execute("INSERT INTO loinc_fts(loinc_fts) VALUES('optimize')")
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            raise RuntimeError(f"SQLite foreign_key_check failed: {foreign_key_errors!r}")
        return report

    return build_sqlite_database(
        schema_path,
        output_path,
        populate,
        user_version=2,
    )


def _concept_values(record: LoincRecord) -> tuple[object, ...]:
    return (
        record.code,
        record.component,
        record.property,
        record.time_aspect,
        record.system,
        record.scale_type,
        record.method_type,
        record.long_common_name,
        record.short_name,
        record.consumer_name,
        record.class_name,
        record.class_type,
        record.order_obs,
        record.status,
        record.status_reason,
        record.status_text,
        record.change_type,
        record.definition_description,
        record.version_first_released,
        record.version_last_changed,
        record.panel_type,
        record.zh_display,
        record.source_metadata_json,
        record.translation_metadata_json,
        record.source_row,
        record.translation_source_row,
        record.source_version,
        record.core_source_sha256,
        record.translation_source_sha256,
    )
