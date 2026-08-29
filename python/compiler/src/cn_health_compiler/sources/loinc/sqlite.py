"""SQLite artifact construction for LOINC records."""

from collections.abc import Iterable
from dataclasses import astuple, fields
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from cn_health_compiler.core.sqlite import SQLiteArtifact, build_sqlite_artifact
from cn_health_compiler.sources.loinc.adapter import LoincRecord


class LoincValidationError(ValueError):
    pass


class LoincValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    record_count: int
    unique_codes: int


class LoincValidator:
    def __init__(self, expected_count: int) -> None:
        self._expected_count = expected_count
        self._seen: set[str] = set()

    def consume(self, record: LoincRecord) -> None:
        if record.code in self._seen:
            raise LoincValidationError(f"duplicate LOINC code {record.code}")
        self._seen.add(record.code)

    def finish(self) -> LoincValidationReport:
        if len(self._seen) != self._expected_count:
            raise LoincValidationError(
                f"record count changed: expected {self._expected_count}, found {len(self._seen)}"
            )
        return LoincValidationReport(record_count=len(self._seen), unique_codes=len(self._seen))


_COLUMNS = tuple(field.name for field in fields(LoincRecord))
_POST_INSERT_SQL = (
    """
    INSERT INTO loinc_fts(rowid, long_common_name, zh_display)
    SELECT rowid, long_common_name, zh_display FROM loinc ORDER BY code
    """,
    """
    WITH RECURSIVE searchable(code, text) AS (
        SELECT code, long_common_name FROM loinc
        UNION ALL SELECT code, zh_display FROM loinc WHERE zh_display IS NOT NULL
    ), grams(code, text, position) AS (
        SELECT code, text, 1 FROM searchable WHERE length(text) >= 2
        UNION ALL
        SELECT code, text, position + 1 FROM grams WHERE position < length(text) - 1
    )
    INSERT OR IGNORE INTO loinc_search_bigram(term, code)
    SELECT substr(text, position, 2), code FROM grams ORDER BY 1, 2
    """,
    "INSERT INTO loinc_fts(loinc_fts) VALUES('optimize')",
)


def build_loinc_sqlite(
    records: Iterable[LoincRecord],
    schema_path: Path,
    output_path: Path,
    *,
    expected_count: int,
) -> SQLiteArtifact[LoincValidationReport]:
    return build_sqlite_artifact(
        records,
        LoincValidator(expected_count),
        astuple,
        _COLUMNS,
        schema_path,
        output_path,
        table="loinc",
        staging_table="loinc_staging",
        post_insert_sql=_POST_INSERT_SQL,
    )
