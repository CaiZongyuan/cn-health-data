"""Strict adapter for pinned official LOINC ZIP/CSV packages."""

import csv
import hashlib
import io
import re
import stat
import unicodedata
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from functools import cache
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile

import rfc8785
from ucumvert import InvalidUcumError, parse_ucum  # type: ignore[import-untyped]

from cn_health_compiler.sources.loinc.layout import (
    CsvMember,
    LinguisticVariantMember,
    LoincLayout,
    PanelMember,
    PartMember,
    SpecimenLinkMember,
    UnitMember,
)
from cn_health_compiler.sources.loinc.records import (
    LoincPackageRecords,
    LoincPanelMemberRecord,
    LoincRecord,
    LoincSpecimenRecord,
    LoincUnitRecord,
    SourceMemberInspection,
)

_LOINC_CODE = re.compile(r"^[0-9]+-[0-9]$")
_DRIVE_PATH = re.compile(r"^[A-Za-z]:")
_COMPRESSION_METHODS = {"stored": ZIP_STORED, "deflate": ZIP_DEFLATED}


class LoincAdapterError(ValueError):
    """Raised when a LOINC source package violates its explicit contract."""


@dataclass(frozen=True, slots=True)
class _Translation:
    display: str | None
    metadata_json: str
    source_row: int


@dataclass(frozen=True, slots=True)
class _Part:
    number: str
    name: str
    display_name: str | None


def read_loinc_package(
    core_archive_path: Path,
    linguistic_variant_archive_path: Path | None,
    layout: LoincLayout,
    *,
    source_version: str,
    core_source_sha256: str,
    translation_source_sha256: str,
) -> LoincPackageRecords:
    """Read and join one fully pinned LOINC source set."""
    source_version = _required(source_version, "source_version")
    core_source_sha256 = _source_hash(core_source_sha256, "core_source_sha256")
    translation_source_sha256 = _source_hash(translation_source_sha256, "translation_source_sha256")
    with _open_archives(core_archive_path, linguistic_variant_archive_path, layout) as archives:
        _verify_declared_members(archives, layout)
        translations, translation_codes, translation_count = _read_translations(
            archives[layout.linguistic_variant.archive], layout.linguistic_variant
        )
        concepts, concept_codes, core_count = _read_concepts(
            archives[layout.core.archive],
            layout,
            translations,
            source_version,
            core_source_sha256,
            translation_source_sha256,
        )
        unknown_translations = translation_codes - concept_codes
        if unknown_translations:
            raise LoincAdapterError(
                f"Chinese variant references unknown LOINC codes: {sorted(unknown_translations)}"
            )

        units: list[LoincUnitRecord] = []
        inspections = [
            _inspection("core", layout.core, core_count),
            _inspection("linguistic-variant", layout.linguistic_variant, translation_count),
        ]
        for unit_member in layout.units:
            member_records, row_count = _read_units(
                archives[unit_member.archive],
                unit_member,
                concept_codes,
                core_source_sha256,
            )
            units.extend(member_records)
            inspections.append(_inspection(f"unit:{unit_member.unit_kind}", unit_member, row_count))
        parts, part_count = _read_parts(archives[layout.parts.archive], layout.parts)
        specimens, specimen_link_count = _read_specimens(
            archives[layout.specimen_links.archive],
            layout.specimen_links,
            parts,
            concept_codes,
            core_source_sha256,
        )
        panels, panel_count = _read_panels(
            archives[layout.panel_members.archive],
            layout.panel_members,
            concept_codes,
            core_source_sha256,
        )
        inspections.extend(
            (
                _inspection("parts", layout.parts, part_count),
                _inspection("specimen-links", layout.specimen_links, specimen_link_count),
                _inspection("panel-members", layout.panel_members, panel_count),
            )
        )
        return LoincPackageRecords(
            concepts=tuple(sorted(concepts, key=lambda record: record.code)),
            units=tuple(
                sorted(
                    units,
                    key=lambda record: (
                        record.loinc_code,
                        record.unit_kind,
                        record.source_member,
                        record.source_row,
                        record.unit_ordinal,
                    ),
                )
            ),
            specimens=tuple(
                sorted(
                    specimens,
                    key=lambda record: (record.loinc_code, record.part_number, record.link_type),
                )
            ),
            panel_members=tuple(
                sorted(
                    panels,
                    key=lambda record: (
                        record.parent_id,
                        record.member_id,
                    ),
                )
            ),
            source_members=tuple(sorted(inspections, key=lambda item: (item.role, item.member))),
        )


@contextmanager
def _open_archives(
    core_path: Path,
    translation_path: Path | None,
    layout: LoincLayout,
) -> Iterator[dict[str, ZipFile]]:
    if layout.package_mode == "split" and translation_path is None:
        raise LoincAdapterError("split LOINC layout requires a linguistic-variant archive")
    if layout.package_mode == "combined" and translation_path is not None:
        raise LoincAdapterError("combined LOINC layout does not accept a second archive")
    try:
        with ExitStack() as stack:
            core = stack.enter_context(ZipFile(core_path))
            archives: dict[str, ZipFile] = {"core": core, "linguistic-variant": core}
            _validate_archive(core, layout)
            if translation_path is not None:
                translation = stack.enter_context(ZipFile(translation_path))
                _validate_archive(translation, layout)
                archives["linguistic-variant"] = translation
            yield archives
    except BadZipFile as error:
        raise LoincAdapterError(f"invalid LOINC ZIP archive: {error}") from error


def _validate_archive(archive: ZipFile, layout: LoincLayout) -> None:
    limits = layout.archive_limits
    entries = archive.infolist()
    if len(entries) > limits.maximum_entry_count:
        raise LoincAdapterError("ZIP entry count exceeds configured limit")
    allowed_methods = {_COMPRESSION_METHODS[value] for value in limits.allowed_compression}
    normalized_names: set[str] = set()
    total_size = 0
    for entry in entries:
        normalized = _validated_member_name(entry.filename)
        if normalized in normalized_names:
            raise LoincAdapterError(f"duplicate normalized ZIP member {normalized!r}")
        normalized_names.add(normalized)
        if entry.flag_bits & 0x1:
            raise LoincAdapterError(f"encrypted ZIP member {entry.filename!r}")
        mode = entry.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise LoincAdapterError(f"symlink ZIP member {entry.filename!r}")
        if entry.compress_type not in allowed_methods:
            raise LoincAdapterError(f"unsupported ZIP compression for {entry.filename!r}")
        if entry.file_size > limits.maximum_member_uncompressed_bytes:
            raise LoincAdapterError(f"ZIP member exceeds size limit: {entry.filename!r}")
        total_size += entry.file_size
        if total_size > limits.maximum_total_uncompressed_bytes:
            raise LoincAdapterError("ZIP total uncompressed size exceeds configured limit")
        ratio = entry.file_size / max(entry.compress_size, 1)
        if ratio > limits.maximum_compression_ratio:
            raise LoincAdapterError(
                f"ZIP member exceeds compression-ratio limit: {entry.filename!r}"
            )
    try:
        failed_member = archive.testzip()
    except (RuntimeError, OSError) as error:
        raise LoincAdapterError(f"ZIP integrity check failed: {error}") from error
    if failed_member is not None:
        raise LoincAdapterError(f"ZIP CRC check failed for {failed_member!r}")


def _validated_member_name(value: str) -> str:
    is_directory = value.endswith("/")
    path_value = value[:-1] if is_directory else value
    path = PurePosixPath(path_value)
    normalized = path.as_posix()
    if (
        not path_value
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in value
        or "\x00" in value
        or _DRIVE_PATH.match(value)
        or normalized != path_value
    ):
        raise LoincAdapterError(f"unsafe ZIP member path {value!r}")
    return f"{normalized}/" if is_directory else normalized


def _verify_declared_members(archives: dict[str, ZipFile], layout: LoincLayout) -> None:
    verified: dict[tuple[str, str], tuple[str, int]] = {}
    for member in layout.archive_members():
        key = (member.archive, member.member)
        fingerprint = (member.uncompressed_sha256, member.uncompressed_size_bytes)
        previous = verified.get(key)
        if previous is not None:
            if previous != fingerprint:
                raise LoincAdapterError(
                    f"conflicting fingerprints for ZIP member {member.member!r}"
                )
            continue
        archive = archives[member.archive]
        try:
            info = archive.getinfo(member.member)
        except KeyError as error:
            raise LoincAdapterError(f"required ZIP member is missing: {member.member!r}") from error
        if info.is_dir():
            raise LoincAdapterError(f"configured CSV member is a directory: {member.member!r}")
        if info.file_size != member.uncompressed_size_bytes:
            raise LoincAdapterError(f"ZIP member size mismatch: {member.member!r}")
        digest = hashlib.sha256()
        with archive.open(info) as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != member.uncompressed_sha256:
            raise LoincAdapterError(f"ZIP member SHA256 mismatch: {member.member!r}")
        verified[key] = fingerprint


def _read_translations(
    archive: ZipFile,
    config: LinguisticVariantMember,
) -> tuple[dict[str, _Translation], set[str], int]:
    translations: dict[str, _Translation] = {}
    seen: set[str] = set()
    row_count = 0
    for source_row, row in _iter_rows(archive, config):
        row_count += 1
        if not _matches_filters(row, config.filters):
            continue
        code = _loinc_code(row.get(config.code_column), config.code_column)
        if code in seen:
            raise LoincAdapterError(f"duplicate Chinese LOINC translation {code}")
        seen.add(code)
        display = _translation_display(row, config)
        translations[code] = _Translation(
            display=display,
            metadata_json=_metadata_json(row, config.preserved_metadata),
            source_row=source_row,
        )
    return translations, seen, row_count


def _read_concepts(
    archive: ZipFile,
    layout: LoincLayout,
    translations: dict[str, _Translation],
    source_version: str,
    core_source_sha256: str,
    translation_source_sha256: str,
) -> tuple[list[LoincRecord], set[str], int]:
    config = layout.core
    records: list[LoincRecord] = []
    seen: set[str] = set()
    columns = config.columns
    row_count = 0
    for source_row, row in _iter_rows(archive, config):
        row_count += 1
        code = _loinc_code(row.get(columns.code), columns.code)
        if code in seen:
            raise LoincAdapterError(f"duplicate LOINC code {code}")
        seen.add(code)
        translation = translations.get(code)
        records.append(
            LoincRecord(
                code=code,
                component=_column(row, columns.component),
                property=_column(row, columns.property),
                time_aspect=_column(row, columns.time_aspect),
                system=_column(row, columns.system),
                scale_type=_column(row, columns.scale_type),
                method_type=_column(row, columns.method_type),
                long_common_name=_required(
                    row.get(columns.long_common_name), columns.long_common_name
                ),
                short_name=_column(row, columns.short_name),
                consumer_name=_column(row, columns.consumer_name),
                class_name=_column(row, columns.class_name),
                class_type=_optional_integer(row, columns.class_type),
                order_obs=_column(row, columns.order_obs),
                status=_required(row.get(columns.status), columns.status),
                status_reason=_column(row, columns.status_reason),
                status_text=_column(row, columns.status_text),
                change_type=_column(row, columns.change_type),
                definition_description=_column(row, columns.definition_description),
                version_first_released=_column(row, columns.version_first_released),
                version_last_changed=_column(row, columns.version_last_changed),
                panel_type=_column(row, columns.panel_type),
                zh_display=translation.display if translation is not None else None,
                source_metadata_json=_metadata_json(row, config.preserved_metadata),
                translation_metadata_json=(
                    translation.metadata_json if translation is not None else "{}"
                ),
                source_row=source_row,
                translation_source_row=(
                    translation.source_row if translation is not None else None
                ),
                source_version=source_version,
                core_source_sha256=core_source_sha256,
                translation_source_sha256=translation_source_sha256,
            )
        )
    return records, seen, row_count


def _read_units(
    archive: ZipFile,
    config: UnitMember,
    concept_codes: set[str],
    source_sha256: str,
) -> tuple[list[LoincUnitRecord], int]:
    records: list[LoincUnitRecord] = []
    row_count = 0
    for source_row, row in _iter_rows(archive, config):
        row_count += 1
        if not _matches_filters(row, config.filters):
            continue
        raw_units = _optional(row.get(config.unit_column))
        if raw_units is None:
            continue
        code = _loinc_code(row.get(config.code_column), config.code_column)
        if code not in concept_codes:
            raise LoincAdapterError(f"unit references unknown LOINC code {code}")
        values = [raw_units] if config.separator is None else raw_units.split(config.separator)
        for unit_ordinal, value in enumerate(values, start=1):
            unit = _optional(value)
            if unit is None:
                raise LoincAdapterError(f"empty UCUM unit segment for LOINC code {code}")
            if not _valid_ucum(unit) and unit not in config.parser_exceptions:
                raise LoincAdapterError(f"invalid UCUM unit {unit!r} for LOINC code {code}")
            records.append(
                LoincUnitRecord(
                    loinc_code=code,
                    ucum_unit=unit,
                    unit_kind=config.unit_kind,
                    unit_ordinal=unit_ordinal,
                    source_member=config.member,
                    source_row=source_row,
                    source_sha256=source_sha256,
                )
            )
    return records, row_count


def _read_parts(archive: ZipFile, config: PartMember) -> tuple[dict[str, _Part], int]:
    parts: dict[str, _Part] = {}
    row_count = 0
    for _, row in _iter_rows(archive, config):
        row_count += 1
        if not _matches_filters(row, config.filters):
            continue
        number = _required(row.get(config.part_number_column), config.part_number_column)
        if number in parts:
            raise LoincAdapterError(f"duplicate LOINC SYSTEM part {number}")
        parts[number] = _Part(
            number=number,
            name=_required(row.get(config.part_name_column), config.part_name_column),
            display_name=_column(row, config.part_display_name_column),
        )
    return parts, row_count


def _read_specimens(
    archive: ZipFile,
    config: SpecimenLinkMember,
    parts: dict[str, _Part],
    concept_codes: set[str],
    source_sha256: str,
) -> tuple[list[LoincSpecimenRecord], int]:
    records: list[LoincSpecimenRecord] = []
    seen: set[tuple[str, str, str]] = set()
    row_count = 0
    for source_row, row in _iter_rows(archive, config):
        row_count += 1
        if not _matches_filters(row, config.filters):
            continue
        code = _loinc_code(row.get(config.code_column), config.code_column)
        if code not in concept_codes:
            raise LoincAdapterError(f"specimen link references unknown LOINC code {code}")
        part_number = _required(row.get(config.part_number_column), config.part_number_column)
        try:
            part = parts[part_number]
        except KeyError as error:
            raise LoincAdapterError(
                f"specimen link references unknown SYSTEM part {part_number}"
            ) from error
        link_type = _required(row.get(config.link_type_column), config.link_type_column)
        key = (code, part_number, link_type)
        if key in seen:
            raise LoincAdapterError(f"duplicate LOINC specimen link {key}")
        seen.add(key)
        records.append(
            LoincSpecimenRecord(
                loinc_code=code,
                part_number=part.number,
                part_name=part.name,
                part_display_name=part.display_name,
                link_type=link_type,
                source_member=config.member,
                source_row=source_row,
                source_sha256=source_sha256,
            )
        )
    return records, row_count


def _read_panels(
    archive: ZipFile,
    config: PanelMember,
    concept_codes: set[str],
    source_sha256: str,
) -> tuple[list[LoincPanelMemberRecord], int]:
    records: list[LoincPanelMemberRecord] = []
    seen: set[tuple[str, str]] = set()
    row_count = 0
    for source_row, row in _iter_rows(archive, config):
        row_count += 1
        if not _matches_filters(row, config.filters):
            continue
        panel_code = _loinc_code(row.get(config.panel_code_column), config.panel_code_column)
        member_code = _loinc_code(row.get(config.member_code_column), config.member_code_column)
        if config.exclude_self_links and panel_code == member_code:
            continue
        if panel_code not in concept_codes or member_code not in concept_codes:
            raise LoincAdapterError(
                f"panel edge references unknown LOINC code {panel_code} -> {member_code}"
            )
        if panel_code == member_code:
            raise LoincAdapterError(f"LOINC panel cannot reference itself: {panel_code}")
        member_order = _required_integer(
            row.get(config.member_order_column), config.member_order_column
        )
        if member_order < 0:
            raise LoincAdapterError(f"negative panel member order for {panel_code}")
        parent_id = _required(row.get(config.parent_id_column), config.parent_id_column)
        member_id = _required(row.get(config.member_id_column), config.member_id_column)
        relationship = (
            _required(row.get(config.relationship_column), config.relationship_column)
            if config.relationship_column is not None
            else _required(config.relationship_value, "relationship_value")
        )
        key = (parent_id, member_id)
        if key in seen:
            raise LoincAdapterError(f"duplicate LOINC panel edge {key}")
        seen.add(key)
        records.append(
            LoincPanelMemberRecord(
                parent_id=parent_id,
                member_id=member_id,
                panel_code=panel_code,
                member_code=member_code,
                member_order=member_order,
                relationship=relationship,
                source_metadata_json=_metadata_json(row, config.preserved_metadata),
                source_member=config.member,
                source_row=source_row,
                source_sha256=source_sha256,
            )
        )
    return records, row_count


def _iter_rows(archive: ZipFile, config: CsvMember) -> Iterator[tuple[int, dict[str, str]]]:
    try:
        with archive.open(config.member) as binary:
            text = io.TextIOWrapper(binary, encoding=config.encoding, newline="")
            reader = csv.DictReader(text, delimiter=config.delimiter, strict=True)
            actual_headers = tuple(reader.fieldnames or ())
            if actual_headers != config.headers:
                raise LoincAdapterError(
                    f"CSV headers changed for {config.member!r}: expected {config.headers!r}, "
                    f"found {actual_headers!r}"
                )
            for source_row, raw in enumerate(reader, start=2):
                if None in raw or any(value is None for value in raw.values()):
                    raise LoincAdapterError(
                        f"CSV column count changed at {config.member}:{source_row}"
                    )
                yield source_row, {str(key): str(value) for key, value in raw.items()}
    except (UnicodeDecodeError, csv.Error) as error:
        raise LoincAdapterError(f"invalid CSV member {config.member!r}: {error}") from error


def _inspection(role: str, config: CsvMember, row_count: int) -> SourceMemberInspection:
    return SourceMemberInspection(
        role=role,
        archive_role=config.archive,
        member=config.member,
        uncompressed_sha256=config.uncompressed_sha256,
        uncompressed_size_bytes=config.uncompressed_size_bytes,
        row_count=row_count,
    )


def _matches_filters(row: dict[str, str], filters: dict[str, str]) -> bool:
    return all(_optional(row.get(column)) == value for column, value in filters.items())


def _translation_display(
    row: dict[str, str],
    config: LinguisticVariantMember,
) -> str | None:
    if config.display_column is not None:
        return _optional(row.get(config.display_column))
    values = [
        value
        for column in config.display_from_columns
        if (value := _optional(row.get(column))) is not None
    ]
    return ":".join(values) or None


@cache
def _valid_ucum(unit: str) -> bool:
    try:
        parse_ucum(unit)
    except InvalidUcumError:
        return False
    return True


def _metadata_json(row: dict[str, str], mapping: dict[str, str]) -> str:
    metadata = {
        key: value
        for key, column in mapping.items()
        if (value := _optional(row.get(column))) is not None
    }
    return rfc8785.dumps(metadata).decode("utf-8")


def _column(row: dict[str, str], column: str | None) -> str | None:
    return None if column is None else _optional(row.get(column))


def _optional_integer(row: dict[str, str], column: str | None) -> int | None:
    if column is None:
        return None
    value = _optional(row.get(column))
    return None if value is None else _integer(value, column)


def _required_integer(value: str | None, field_name: str) -> int:
    return _integer(_required(value, field_name), field_name)


def _integer(value: str, field_name: str) -> int:
    try:
        return int(value)
    except ValueError as error:
        raise LoincAdapterError(f"{field_name} must be an integer") from error


def _loinc_code(value: str | None, field_name: str) -> str:
    code = _required(value, field_name)
    if _LOINC_CODE.fullmatch(code) is None:
        raise LoincAdapterError(f"invalid LOINC code {code!r}")
    return code


def _source_hash(value: str, field_name: str) -> str:
    value = _required(value, field_name)
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise LoincAdapterError(f"{field_name} must be a lowercase SHA256")
    return value


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
