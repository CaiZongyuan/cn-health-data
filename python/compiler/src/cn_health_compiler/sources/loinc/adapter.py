"""Configurable LOINC ZIP/CSV and linguistic-variant adapter."""

import csv
import io
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from pydantic import BaseModel, ConfigDict


class LoincAdapterError(ValueError):
    """Raised when a LOINC source package violates its explicit contract."""


class LoincArchiveConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    loinc_member: str
    translation_member: str
    code_column: str = "LOINC_NUM"
    translation_code_column: str = "LOINC_NUM"
    translation_display_column: str
    long_name_column: str = "LONG_COMMON_NAME"


@dataclass(frozen=True, slots=True)
class LoincRecord:
    code: str
    component: str | None
    property: str | None
    time_aspect: str | None
    system: str | None
    scale_type: str | None
    method_type: str | None
    long_common_name: str
    status: str | None
    zh_display: str | None
    source_version: str
    source_sha256: str


def iter_loinc_records(
    archive_path: Path,
    config: LoincArchiveConfig,
    source_version: str,
    source_sha256: str,
) -> Iterator[LoincRecord]:
    """Join a LOINC table to a Chinese variant and stream canonical records."""
    _validate_member(config.loinc_member)
    _validate_member(config.translation_member)
    source_version = _required(source_version, "source_version")
    source_sha256 = _required(source_sha256, "source_sha256")
    with ZipFile(archive_path) as archive:
        translations = _translations(archive, config)
        seen: set[str] = set()
        with archive.open(config.loinc_member) as binary:
            reader = csv.DictReader(io.TextIOWrapper(binary, encoding="utf-8-sig", newline=""))
            _require_columns(reader, {config.code_column, config.long_name_column})
            for row in reader:
                code = _required(row.get(config.code_column), config.code_column)
                if code in seen:
                    raise LoincAdapterError(f"duplicate LOINC code {code}")
                seen.add(code)
                yield LoincRecord(
                    code=code,
                    component=_optional(row.get("COMPONENT")),
                    property=_optional(row.get("PROPERTY")),
                    time_aspect=_optional(row.get("TIME_ASPCT")),
                    system=_optional(row.get("SYSTEM")),
                    scale_type=_optional(row.get("SCALE_TYP")),
                    method_type=_optional(row.get("METHOD_TYP")),
                    long_common_name=_required(
                        row.get(config.long_name_column), config.long_name_column
                    ),
                    status=_optional(row.get("STATUS")),
                    zh_display=translations.get(code),
                    source_version=source_version,
                    source_sha256=source_sha256,
                )


def _translations(archive: ZipFile, config: LoincArchiveConfig) -> dict[str, str]:
    translations: dict[str, str] = {}
    with archive.open(config.translation_member) as binary:
        reader = csv.DictReader(io.TextIOWrapper(binary, encoding="utf-8-sig", newline=""))
        _require_columns(
            reader,
            {config.translation_code_column, config.translation_display_column},
        )
        for row in reader:
            code = _required(
                row.get(config.translation_code_column), config.translation_code_column
            )
            display = _required(
                row.get(config.translation_display_column), config.translation_display_column
            )
            if code in translations:
                raise LoincAdapterError(f"duplicate Chinese LOINC translation {code}")
            translations[code] = display
    return translations


def _require_columns(reader: csv.DictReader[str], required: set[str]) -> None:
    columns = set(reader.fieldnames or ())
    missing = required - columns
    if missing:
        raise LoincAdapterError(f"CSV is missing required columns: {sorted(missing)}")


def _validate_member(member: str) -> None:
    path = PurePosixPath(member)
    if path.is_absolute() or ".." in path.parts:
        raise LoincAdapterError(f"unsafe ZIP member path {member!r}")


def _required(value: str | None, field_name: str) -> str:
    normalized = _optional(value)
    if normalized is None:
        raise LoincAdapterError(f"{field_name} is required")
    return normalized


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFC", value.strip())
    return normalized or None
