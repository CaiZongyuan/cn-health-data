"""Streaming UN World Population Prospects age/sex records for China."""

import csv
import gzip
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

_HEADERS = (
    "SortOrder",
    "LocID",
    "Notes",
    "ISO3_code",
    "ISO2_code",
    "SDMX_code",
    "LocTypeID",
    "LocTypeName",
    "ParentID",
    "Location",
    "VarID",
    "Variant",
    "Time",
    "MidPeriod",
    "AgeGrp",
    "AgeGrpStart",
    "AgeGrpSpan",
    "PopMale",
    "PopFemale",
    "PopTotal",
)
_THOUSAND = Decimal(1000)


class WppFormatError(ValueError):
    """Raised when a WPP source violates the pinned CSV contract."""


@dataclass(frozen=True, slots=True)
class PopulationAgeSexRecord:
    code: str
    country_code: str
    variant: str
    year: int
    mid_period: float
    age_group: str
    age_start: int
    age_end: int | None
    male_population: int
    female_population: int
    total_population: int
    source_row: int
    source_version: str
    source_sha256: str


def _integer(value: str, label: str, row_number: int) -> int:
    try:
        return int(value)
    except ValueError as error:
        raise WppFormatError(f"row {row_number} has invalid {label}") from error


def _decimal(value: str, label: str, row_number: int) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as error:
        raise WppFormatError(f"row {row_number} has invalid {label}") from error


def _population(value: str, label: str, row_number: int) -> int:
    population = int((_decimal(value, label, row_number) * _THOUSAND).quantize(1, ROUND_HALF_UP))
    if population < 0:
        raise WppFormatError(f"row {row_number} has negative {label}")
    return population


def iter_wpp_age_sex_records(
    path: Path,
    *,
    source_version: str,
    source_sha256: str,
) -> Iterator[PopulationAgeSexRecord]:
    try:
        stream = gzip.open(path, mode="rt", encoding="utf-8-sig", newline="")
    except OSError as error:
        raise WppFormatError("WPP source is not a readable gzip file") from error
    with stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != _HEADERS:
            raise WppFormatError("WPP CSV headers do not match the adapter contract")
        for source_row, row in enumerate(reader, start=2):
            if row["ISO3_code"] != "CHN" or row["Variant"] != "Medium":
                continue
            year = _integer(row["Time"], "year", source_row)
            age_start = _integer(row["AgeGrpStart"], "age-group start", source_row)
            age_span = _integer(row["AgeGrpSpan"], "age-group span", source_row)
            if age_start < 0 or age_span == 0 or age_span < -1:
                raise WppFormatError(f"row {source_row} has invalid age group")
            age_end = None if age_span == -1 else age_start + age_span - 1
            male = _population(row["PopMale"], "male population", source_row)
            female = _population(row["PopFemale"], "female population", source_row)
            total = _population(row["PopTotal"], "total population", source_row)
            if abs(male + female - total) > 2:
                raise WppFormatError(
                    f"row {source_row} male and female populations do not match total"
                )
            yield PopulationAgeSexRecord(
                code=f"CHN:Medium:{year}:{age_start:03d}",
                country_code="CHN",
                variant="Medium",
                year=year,
                mid_period=float(_decimal(row["MidPeriod"], "mid-period", source_row)),
                age_group=row["AgeGrp"],
                age_start=age_start,
                age_end=age_end,
                male_population=male,
                female_population=female,
                total_population=total,
                source_row=source_row,
                source_version=source_version,
                source_sha256=source_sha256,
            )
