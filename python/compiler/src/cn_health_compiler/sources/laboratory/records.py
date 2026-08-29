"""Parse the project-authored Chinese laboratory catalog."""

import csv
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

_HEADERS = (
    "code",
    "display_zh",
    "category",
    "specimen",
    "result_type",
    "ucum_unit",
    "loinc_version",
    "status",
    "source_note",
)
_LOINC_CODE = re.compile(r"^\d{1,5}-\d$")
_CHINESE = re.compile(r"[\u3400-\u9fff]")

type LaboratoryCategory = Literal["chemistry", "hematology", "vital-sign"]
type LaboratorySpecimen = Literal["blood", "body"]
type LaboratoryResultType = Literal["panel", "quantity"]


class LaboratoryCatalogFormatError(ValueError):
    """Raised when the curated catalog violates its pinned CSV contract."""


@dataclass(frozen=True, slots=True)
class LaboratoryConceptRecord:
    code: str
    system: str
    terminology_version: str
    display_zh: str
    category: LaboratoryCategory
    specimen: LaboratorySpecimen
    result_type: LaboratoryResultType
    ucum_unit: str | None
    status: Literal["active", "inactive"]
    source_note: str
    source_row: int
    source_version: str
    source_sha256: str


def _literal(
    value: str,
    allowed: tuple[str, ...],
    label: str,
    source_row: int,
) -> str:
    if value not in allowed:
        raise LaboratoryCatalogFormatError(f"row {source_row} has invalid {label}")
    return value


def iter_laboratory_records(
    path: Path,
    *,
    source_version: str,
    source_sha256: str,
) -> Iterator[LaboratoryConceptRecord]:
    try:
        stream = path.open(encoding="utf-8-sig", newline="")
    except OSError as error:
        raise LaboratoryCatalogFormatError("laboratory catalog is unreadable") from error
    with stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != _HEADERS:
            raise LaboratoryCatalogFormatError("laboratory catalog headers do not match")
        for source_row, row in enumerate(reader, start=2):
            code = row["code"].strip()
            display_zh = row["display_zh"].strip()
            result_type = cast(
                LaboratoryResultType,
                _literal(
                    row["result_type"].strip(),
                    ("panel", "quantity"),
                    "result type",
                    source_row,
                ),
            )
            unit = row["ucum_unit"].strip() or None
            if _LOINC_CODE.fullmatch(code) is None:
                raise LaboratoryCatalogFormatError(f"row {source_row} has invalid LOINC code")
            if not display_zh or _CHINESE.search(display_zh) is None:
                raise LaboratoryCatalogFormatError(f"row {source_row} has invalid Chinese display")
            if (result_type == "panel") != (unit is None):
                raise LaboratoryCatalogFormatError(
                    f"row {source_row} result type and UCUM unit do not match"
                )
            source_note = row["source_note"].strip()
            if not source_note:
                raise LaboratoryCatalogFormatError(f"row {source_row} has no source note")
            yield LaboratoryConceptRecord(
                code=code,
                system="http://loinc.org",
                terminology_version=row["loinc_version"].strip(),
                display_zh=display_zh,
                category=cast(
                    LaboratoryCategory,
                    _literal(
                        row["category"].strip(),
                        ("chemistry", "hematology", "vital-sign"),
                        "category",
                        source_row,
                    ),
                ),
                specimen=cast(
                    LaboratorySpecimen,
                    _literal(
                        row["specimen"].strip(),
                        ("blood", "body"),
                        "specimen",
                        source_row,
                    ),
                ),
                result_type=result_type,
                ucum_unit=unit,
                status=cast(
                    Literal["active", "inactive"],
                    _literal(
                        row["status"].strip(),
                        ("active", "inactive"),
                        "status",
                        source_row,
                    ),
                ),
                source_note=source_note,
                source_row=source_row,
                source_version=source_version,
                source_sha256=source_sha256,
            )
