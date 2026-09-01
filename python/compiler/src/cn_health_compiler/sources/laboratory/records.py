"""Parse the project-authored laboratory runtime and panel catalogs."""

import csv
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from cn_health_compiler.sources.nhc_lab.records import NHCLaboratoryTestRecord

_RUNTIME_HEADERS = (
    "code",
    "unit_display",
    "unit_ucum",
    "precision",
    "healthy_strategy",
    "loinc_code",
    "sex",
    "reference_kind",
    "low_value",
    "high_value",
    "normal_value",
    "simulation_low",
    "simulation_high",
    "source_type",
    "source_standard",
    "source_version",
    "source_location",
    "notes",
)
_PANEL_HEADERS = (
    "panel_code",
    "panel_name",
    "specimen",
    "evidence_source_row",
    "notes",
    "test_code",
    "sort_order",
)
_LOINC_CODE = re.compile(r"^\d{1,5}-\d$")
_PANEL_CODE = re.compile(r"^CN-LAB-[A-Z0-9-]+$")
_SCALE_RESULT_KIND = {
    "A": "quantity",
    "B": "qualitative",
    "C": "named",
    "D": "ordinal",
}

type ResultKind = Literal["quantity", "qualitative", "ordinal", "named"]
type HealthyStrategy = Literal["uniform", "fixed-normal"]
type Sex = Literal["all", "male", "female"]
type ReferenceKind = Literal["range", "upper-bound", "lower-bound", "coded", "ordinal"]
type SourceType = Literal["national-standard", "project-curated"]


class LaboratoryCatalogFormatError(ValueError):
    """Raised when a project laboratory catalog violates its pinned format."""


@dataclass(frozen=True, slots=True)
class LaboratoryConceptRecord:
    """Legacy schema v1 record retained for historical translation tooling."""

    code: str
    system: str
    terminology_version: str
    display_zh: str
    category: str
    specimen: str
    result_type: str
    ucum_unit: str | None
    status: str
    source_note: str
    source_row: int
    source_version: str
    source_sha256: str


@dataclass(frozen=True, slots=True)
class LaboratoryTestRecord:
    code: str
    name: str
    category: str
    analyte: str
    specimen: str
    scale: str
    result_kind: ResultKind
    unit_display: str | None
    unit_ucum: str | None
    precision: int
    healthy_strategy: HealthyStrategy
    loinc_code: str | None
    status: Literal["active", "inactive"]
    source_version: str


@dataclass(frozen=True, slots=True)
class LaboratoryReferenceRecord:
    test_code: str
    sex: Sex
    reference_kind: ReferenceKind
    low_value: float | None
    high_value: float | None
    normal_value: str | None
    simulation_low: float | None
    simulation_high: float | None
    source_type: SourceType
    source_standard: str
    source_version: str
    source_location: str
    notes: str


@dataclass(frozen=True, slots=True)
class LaboratoryPanelRecord:
    code: str
    name: str
    specimen: str
    status: Literal["active", "inactive"]
    source_type: Literal["project-authored"]
    source_location: str
    notes: str


@dataclass(frozen=True, slots=True)
class LaboratoryPanelMemberRecord:
    panel_code: str
    test_code: str
    sort_order: int


@dataclass(frozen=True, slots=True)
class LaboratoryCatalog:
    tests: tuple[LaboratoryTestRecord, ...]
    references: tuple[LaboratoryReferenceRecord, ...]
    panels: tuple[LaboratoryPanelRecord, ...]
    panel_members: tuple[LaboratoryPanelMemberRecord, ...]


def iter_laboratory_records(
    path: Path,
    *,
    source_version: str,
    source_sha256: str,
) -> Iterator[LaboratoryConceptRecord]:
    """Read the immutable schema v1 catalog used by historical Releases."""
    headers = (
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
    rows = _read_rows(path, headers)
    for source_row, row in enumerate(rows, start=2):
        code = row["code"].strip()
        if _LOINC_CODE.fullmatch(code) is None:
            raise LaboratoryCatalogFormatError(f"row {source_row} has invalid LOINC code")
        result_type = _literal(
            row["result_type"].strip(), {"panel", "quantity"}, "result type", source_row
        )
        unit = row["ucum_unit"].strip() or None
        if (result_type == "panel") != (unit is None):
            raise LaboratoryCatalogFormatError(
                f"row {source_row} result type and UCUM unit do not match"
            )
        values = (
            row["display_zh"].strip(),
            row["category"].strip(),
            row["specimen"].strip(),
            row["loinc_version"].strip(),
            row["status"].strip(),
            row["source_note"].strip(),
        )
        if not all(values):
            raise LaboratoryCatalogFormatError(f"row {source_row} has an empty required field")
        yield LaboratoryConceptRecord(
            code=code,
            system="http://loinc.org",
            terminology_version=row["loinc_version"].strip(),
            display_zh=row["display_zh"].strip(),
            category=row["category"].strip(),
            specimen=row["specimen"].strip(),
            result_type=result_type,
            ucum_unit=unit,
            status=row["status"].strip(),
            source_note=row["source_note"].strip(),
            source_row=source_row,
            source_version=source_version,
            source_sha256=source_sha256,
        )


def _read_rows(path: Path, headers: tuple[str, ...]) -> list[dict[str, str]]:
    try:
        stream = path.open(encoding="utf-8-sig", newline="")
    except OSError as error:
        raise LaboratoryCatalogFormatError(f"catalog is unreadable: {path}") from error
    with stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != headers:
            raise LaboratoryCatalogFormatError(f"catalog headers do not match: {path.name}")
        rows = list(reader)
    if not rows:
        raise LaboratoryCatalogFormatError(f"catalog is empty: {path.name}")
    return rows


def _literal(value: str, allowed: set[str], label: str, source_row: int) -> str:
    if value not in allowed:
        raise LaboratoryCatalogFormatError(f"row {source_row} has invalid {label}: {value!r}")
    return value


def _integer(value: str, label: str, source_row: int) -> int:
    try:
        return int(value)
    except ValueError as error:
        raise LaboratoryCatalogFormatError(f"row {source_row} has invalid {label}") from error


def _number(value: str, label: str, source_row: int) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError as error:
        raise LaboratoryCatalogFormatError(f"row {source_row} has invalid {label}") from error


def load_laboratory_catalog(
    runtime_path: Path,
    panel_path: Path,
    terminology: dict[str, NHCLaboratoryTestRecord],
    *,
    source_version: str,
) -> LaboratoryCatalog:
    runtime_rows = _read_rows(runtime_path, _RUNTIME_HEADERS)
    tests: dict[str, LaboratoryTestRecord] = {}
    references: list[LaboratoryReferenceRecord] = []
    for source_row, row in enumerate(runtime_rows, start=2):
        code = row["code"].strip()
        authority = terminology.get(code)
        if authority is None:
            raise LaboratoryCatalogFormatError(f"row {source_row} has unknown WS/T 886 code")
        precision = _integer(row["precision"].strip(), "precision", source_row)
        strategy = cast(
            HealthyStrategy,
            _literal(
                row["healthy_strategy"].strip(), {"uniform", "fixed-normal"}, "strategy", source_row
            ),
        )
        loinc_code = row["loinc_code"].strip() or None
        if loinc_code is not None and _LOINC_CODE.fullmatch(loinc_code) is None:
            raise LaboratoryCatalogFormatError(f"row {source_row} has invalid LOINC code")
        result_kind = cast(ResultKind, _SCALE_RESULT_KIND[authority.scale_code])
        test = LaboratoryTestRecord(
            code=code,
            name=authority.name,
            category=authority.category_name,
            analyte=authority.analyte,
            specimen=authority.specimen_name,
            scale=authority.scale_name,
            result_kind=result_kind,
            unit_display=row["unit_display"].strip() or None,
            unit_ucum=row["unit_ucum"].strip() or None,
            precision=precision,
            healthy_strategy=strategy,
            loinc_code=loinc_code,
            status="active",
            source_version=source_version,
        )
        existing = tests.setdefault(code, test)
        if existing != test:
            raise LaboratoryCatalogFormatError(
                f"runtime annotations differ between references for {code}"
            )
        references.append(
            LaboratoryReferenceRecord(
                test_code=code,
                sex=cast(
                    Sex,
                    _literal(row["sex"].strip(), {"all", "male", "female"}, "sex", source_row),
                ),
                reference_kind=cast(
                    ReferenceKind,
                    _literal(
                        row["reference_kind"].strip(),
                        {"range", "upper-bound", "lower-bound", "coded", "ordinal"},
                        "reference kind",
                        source_row,
                    ),
                ),
                low_value=_number(row["low_value"].strip(), "low value", source_row),
                high_value=_number(row["high_value"].strip(), "high value", source_row),
                normal_value=row["normal_value"].strip() or None,
                simulation_low=_number(
                    row["simulation_low"].strip(), "simulation low", source_row
                ),
                simulation_high=_number(
                    row["simulation_high"].strip(), "simulation high", source_row
                ),
                source_type=cast(
                    SourceType,
                    _literal(
                        row["source_type"].strip(),
                        {"national-standard", "project-curated"},
                        "source type",
                        source_row,
                    ),
                ),
                source_standard=row["source_standard"].strip(),
                source_version=row["source_version"].strip(),
                source_location=row["source_location"].strip(),
                notes=row["notes"].strip(),
            )
        )

    panel_rows = _read_rows(panel_path, _PANEL_HEADERS)
    panels: dict[str, LaboratoryPanelRecord] = {}
    panel_members: list[LaboratoryPanelMemberRecord] = []
    for source_row, row in enumerate(panel_rows, start=2):
        code = row["panel_code"].strip()
        if _PANEL_CODE.fullmatch(code) is None:
            raise LaboratoryCatalogFormatError(f"row {source_row} has invalid panel code")
        evidence_row = _integer(
            row["evidence_source_row"].strip(), "evidence source row", source_row
        )
        panel = LaboratoryPanelRecord(
            code=code,
            name=row["panel_name"].strip(),
            specimen=row["specimen"].strip(),
            status="active",
            source_type="project-authored",
            source_location=f"检验类医疗服务价格项目立项指南映射关系表.xlsx/row {evidence_row}",
            notes=row["notes"].strip(),
        )
        existing_panel = panels.setdefault(code, panel)
        if existing_panel != panel:
            raise LaboratoryCatalogFormatError(f"panel metadata differs for {code}")
        panel_members.append(
            LaboratoryPanelMemberRecord(
                panel_code=code,
                test_code=row["test_code"].strip(),
                sort_order=_integer(row["sort_order"].strip(), "sort order", source_row),
            )
        )

    return LaboratoryCatalog(
        tests=tuple(sorted(tests.values(), key=lambda item: item.code)),
        references=tuple(sorted(references, key=lambda item: (item.test_code, item.sex))),
        panels=tuple(sorted(panels.values(), key=lambda item: item.code)),
        panel_members=tuple(
            sorted(panel_members, key=lambda item: (item.panel_code, item.sort_order))
        ),
    )
