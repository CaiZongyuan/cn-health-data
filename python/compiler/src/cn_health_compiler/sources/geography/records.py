"""Streaming GeoNames records for Chinese geography data."""

import csv
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from io import TextIOWrapper
from pathlib import Path
from typing import Literal
from zipfile import BadZipFile, ZipFile

_PLACE_COLUMN_COUNT = 19
_POSTAL_COLUMN_COUNT = 12
_CHINESE_NAME = re.compile(r"[\u3400-\u9fff]+")
_AREA_CITY_FIELDS = (
    "id",
    "pid",
    "deep",
    "name",
    "pinyin_prefix",
    "pinyin",
    "ext_id",
    "ext_name",
)
_AREA_CODE_LENGTHS = {0: {2}, 1: {4, 6}, 2: {6, 9}}


class GeoNamesFormatError(ValueError):
    """Raised when a GeoNames archive violates the declared source format."""


@dataclass(frozen=True, slots=True)
class GeographyPlaceRecord:
    code: str
    geoname_id: int
    name_zh: str
    name_ascii: str
    alternate_names_zh: str
    kind: Literal["administrative-division", "populated-place"]
    feature_code: str
    country_code: str
    admin1_code: str
    admin2_code: str
    admin3_code: str
    admin4_code: str
    latitude: float
    longitude: float
    population: int
    timezone: str
    modified_on: str
    source_row: int
    source_version: str
    source_sha256: str


@dataclass(frozen=True, slots=True)
class GeographyPostalAreaRecord:
    code: str
    postal_code: str
    place_name: str
    admin1_name: str
    admin1_code: str
    admin2_name: str
    admin2_code: str
    admin3_name: str
    admin3_code: str
    latitude: float
    longitude: float
    accuracy: int | None
    source_row: int
    source_version: str
    source_sha256: str


@dataclass(frozen=True, slots=True)
class AdministrativeDivisionRecord:
    code: str
    parent_code: str | None
    level: int
    name_zh: str
    short_name_zh: str
    pinyin: str
    pinyin_prefix: str
    external_code: str
    source_row: int
    source_version: str
    source_sha256: str


def _member_rows(path: Path) -> Iterator[tuple[int, list[str]]]:
    try:
        with ZipFile(path) as archive:
            members = [member for member in archive.infolist() if member.filename == "CN.txt"]
            if len(members) != 1:
                raise GeoNamesFormatError("GeoNames ZIP must contain exactly one CN.txt member")
            with TextIOWrapper(archive.open(members[0]), encoding="utf-8", newline="") as stream:
                rows = csv.reader(stream, delimiter="\t", quoting=csv.QUOTE_NONE)
                yield from enumerate(rows, start=1)
    except BadZipFile as error:
        raise GeoNamesFormatError(f"invalid GeoNames ZIP: {path}") from error


def _number(value: str, label: str, row_number: int) -> float:
    try:
        return float(value)
    except ValueError as error:
        raise GeoNamesFormatError(f"row {row_number} has invalid {label}") from error


def _integer(value: str, label: str, row_number: int) -> int:
    try:
        return int(value)
    except ValueError as error:
        raise GeoNamesFormatError(f"row {row_number} has invalid {label}") from error


def _coordinates(latitude: str, longitude: str, row_number: int) -> tuple[float, float]:
    parsed_latitude = _number(latitude, "latitude", row_number)
    parsed_longitude = _number(longitude, "longitude", row_number)
    if not -90 <= parsed_latitude <= 90 or not -180 <= parsed_longitude <= 180:
        raise GeoNamesFormatError(f"row {row_number} has out-of-range coordinates")
    return parsed_latitude, parsed_longitude


def _chinese_names(name: str, alternates: str) -> tuple[str, str]:
    candidates: list[str] = []
    for candidate in (name, *alternates.split(",")):
        stripped = candidate.strip()
        if _CHINESE_NAME.fullmatch(stripped) is not None and stripped not in candidates:
            candidates.append(stripped)
    if not candidates:
        return name, ""
    base = candidates[0]
    related = [candidate for candidate in candidates if candidate.startswith(base)]
    display = max(related, key=len, default=base)
    return display, "|".join(candidates)


def iter_geonames_places(
    path: Path,
    *,
    source_version: str,
    source_sha256: str,
) -> Iterator[GeographyPlaceRecord]:
    for row_number, row in _member_rows(path):
        if len(row) != _PLACE_COLUMN_COUNT:
            raise GeoNamesFormatError(
                f"row {row_number} has {len(row)} columns; expected {_PLACE_COLUMN_COUNT}"
            )
        if row[8] != "CN":
            raise GeoNamesFormatError(f"row {row_number} has unexpected country code")
        feature_class = row[6]
        population = _integer(row[14], "population", row_number)
        if population < 0:
            raise GeoNamesFormatError(f"row {row_number} has negative population")
        if feature_class != "A" and not (feature_class == "P" and population > 0):
            continue
        latitude, longitude = _coordinates(row[4], row[5], row_number)
        try:
            date.fromisoformat(row[18])
        except ValueError as error:
            raise GeoNamesFormatError(f"row {row_number} has invalid modification date") from error
        name_zh, alternate_names_zh = _chinese_names(row[1], row[3])
        geoname_id = _integer(row[0], "geoname ID", row_number)
        yield GeographyPlaceRecord(
            code=f"geonames:{geoname_id}",
            geoname_id=geoname_id,
            name_zh=name_zh,
            name_ascii=row[2],
            alternate_names_zh=alternate_names_zh,
            kind=("administrative-division" if feature_class == "A" else "populated-place"),
            feature_code=row[7],
            country_code=row[8],
            admin1_code=row[10],
            admin2_code=row[11],
            admin3_code=row[12],
            admin4_code=row[13],
            latitude=latitude,
            longitude=longitude,
            population=population,
            timezone=row[17],
            modified_on=row[18],
            source_row=row_number,
            source_version=source_version,
            source_sha256=source_sha256,
        )


def iter_geonames_postal_areas(
    path: Path,
    *,
    source_version: str,
    source_sha256: str,
) -> Iterator[GeographyPostalAreaRecord]:
    for row_number, row in _member_rows(path):
        if len(row) != _POSTAL_COLUMN_COUNT:
            raise GeoNamesFormatError(
                f"row {row_number} has {len(row)} columns; expected {_POSTAL_COLUMN_COUNT}"
            )
        if row[0] != "CN":
            raise GeoNamesFormatError(f"row {row_number} has unexpected country code")
        latitude, longitude = _coordinates(row[9], row[10], row_number)
        accuracy = None if row[11] == "" else _integer(row[11], "accuracy", row_number)
        if accuracy is not None and not 1 <= accuracy <= 6:
            raise GeoNamesFormatError(f"row {row_number} has invalid accuracy")
        identity = ":".join((row[1], row[4], row[6], row[8], row[2]))
        yield GeographyPostalAreaRecord(
            code=f"postal:{identity}",
            postal_code=row[1],
            place_name=row[2],
            admin1_name=row[3],
            admin1_code=row[4],
            admin2_name=row[5],
            admin2_code=row[6],
            admin3_name=row[7],
            admin3_code=row[8],
            latitude=latitude,
            longitude=longitude,
            accuracy=accuracy,
            source_row=row_number,
            source_version=source_version,
            source_sha256=source_sha256,
        )


def iter_area_city_divisions(
    path: Path,
    *,
    source_version: str,
    source_sha256: str,
) -> Iterator[AdministrativeDivisionRecord]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != _AREA_CITY_FIELDS:
            raise GeoNamesFormatError("AreaCity CSV headers do not match the adapter contract")
        parsed: list[AdministrativeDivisionRecord] = []
        for source_row, row in enumerate(reader, start=2):
            code = row["id"]
            parent = row["pid"]
            level = _integer(row["deep"], "administrative level", source_row)
            external_code = row["ext_id"]
            if level not in (0, 1, 2):
                raise GeoNamesFormatError(f"row {source_row} has invalid administrative level")
            if not code.isdigit() or len(code) not in _AREA_CODE_LENGTHS[level]:
                raise GeoNamesFormatError(f"row {source_row} has invalid administrative code")
            if not external_code.isdigit() or (external_code != "0" and len(external_code) != 12):
                raise GeoNamesFormatError(f"row {source_row} has invalid external code")
            parent_code = None if level == 0 else parent
            if level == 0 and parent != "0":
                raise GeoNamesFormatError(f"row {source_row} has invalid root parent")
            if parent_code is not None and (
                not parent_code.isdigit() or not code.startswith(parent_code)
            ):
                raise GeoNamesFormatError(f"row {source_row} has invalid parent code")
            if not row["name"] or not row["ext_name"] or not row["pinyin"]:
                raise GeoNamesFormatError(f"row {source_row} has missing administrative text")
            if external_code == "0":
                continue
            parsed.append(
                AdministrativeDivisionRecord(
                    code=code,
                    parent_code=parent_code,
                    level=level,
                    name_zh=row["ext_name"],
                    short_name_zh=row["name"],
                    pinyin=row["pinyin"],
                    pinyin_prefix=row["pinyin_prefix"],
                    external_code=external_code,
                    source_row=source_row,
                    source_version=source_version,
                    source_sha256=source_sha256,
                )
            )

    selected: dict[str, AdministrativeDivisionRecord] = {}
    for record in sorted(parsed, key=lambda item: (item.level, item.source_row)):
        selected.setdefault(record.external_code, record)
    yield from sorted(selected.values(), key=lambda item: item.source_row)
