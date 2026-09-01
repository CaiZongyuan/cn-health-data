"""Versioned source-layout contract for official LOINC packages."""

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ArchiveRole = Literal["core", "linguistic-variant"]
_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class ArchiveLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    maximum_entry_count: int = Field(ge=1)
    maximum_total_uncompressed_bytes: int = Field(ge=1)
    maximum_member_uncompressed_bytes: int = Field(ge=1)
    maximum_compression_ratio: float = Field(ge=1)
    allowed_compression: tuple[Literal["stored", "deflate"], ...] = Field(min_length=1)


class ArchiveMember(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    archive: ArchiveRole
    member: str
    uncompressed_sha256: str = Field(pattern=_SHA256_PATTERN)
    uncompressed_size_bytes: int = Field(ge=1)

    @field_validator("member")
    @classmethod
    def validate_member(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            not value
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in value
            or "\x00" in value
            or path.as_posix() != value
        ):
            raise ValueError(f"unsafe ZIP member path {value!r}")
        return value


class CsvMember(ArchiveMember):
    encoding: Literal["utf-8", "utf-8-sig"]
    delimiter: str = Field(min_length=1, max_length=1)
    headers: tuple[str, ...] = Field(min_length=1)

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not header for header in value):
            raise ValueError("CSV headers must not be empty")
        if len(set(value)) != len(value):
            raise ValueError("CSV headers must be unique")
        return value


class CoreColumns(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    component: str | None = None
    property: str | None = None
    time_aspect: str | None = None
    system: str | None = None
    scale_type: str | None = None
    method_type: str | None = None
    long_common_name: str
    short_name: str | None = None
    consumer_name: str | None = None
    class_name: str | None = Field(default=None, alias="class")
    class_type: str | None = None
    order_obs: str | None = None
    status: str
    status_reason: str | None = None
    status_text: str | None = None
    change_type: str | None = None
    definition_description: str | None = None
    version_first_released: str | None = None
    version_last_changed: str | None = None
    panel_type: str | None = None

    def source_columns(self) -> tuple[str, ...]:
        values = self.model_dump(by_alias=True)
        return tuple(str(value) for value in values.values() if value is not None)


class CoreMember(CsvMember):
    columns: CoreColumns
    preserved_metadata: dict[str, str] = Field(default_factory=dict)
    ignored_columns: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_column_coverage(self) -> "CoreMember":
        _validate_column_coverage(
            self.headers,
            (*self.columns.source_columns(), *self.preserved_metadata.values()),
            {},
            self.ignored_columns,
        )
        if any(not key for key in self.preserved_metadata):
            raise ValueError("preserved metadata keys must not be empty")
        return self


class LinguisticVariantMember(CsvMember):
    code_column: str
    display_column: str | None = None
    display_from_columns: tuple[str, ...] = ()
    filters: dict[str, str] = Field(default_factory=dict)
    preserved_metadata: dict[str, str] = Field(default_factory=dict)
    ignored_columns: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_column_coverage(self) -> "LinguisticVariantMember":
        if (self.display_column is None) == (not self.display_from_columns):
            raise ValueError(
                "linguistic variant requires exactly one display column or display-from set"
            )
        mapped = [self.code_column, *self.preserved_metadata.values()]
        display_columns = (
            (self.display_column,) if self.display_column is not None else self.display_from_columns
        )
        mapped.extend(column for column in display_columns if column not in mapped)
        _validate_column_coverage(
            self.headers,
            mapped,
            self.filters,
            self.ignored_columns,
        )
        if any(not key for key in self.preserved_metadata):
            raise ValueError("linguistic metadata keys must not be empty")
        return self


class UnitMember(CsvMember):
    code_column: str
    unit_column: str
    unit_kind: str = Field(min_length=1)
    separator: str | None = Field(default=None, min_length=1, max_length=1)
    parser_exceptions: tuple[str, ...] = ()
    filters: dict[str, str] = Field(default_factory=dict)
    ignored_columns: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_column_coverage(self) -> "UnitMember":
        _validate_column_coverage(
            self.headers,
            (self.code_column, self.unit_column),
            self.filters,
            self.ignored_columns,
        )
        return self


class PartMember(CsvMember):
    part_number_column: str
    part_name_column: str
    part_display_name_column: str | None = None
    filters: dict[str, str] = Field(default_factory=dict)
    ignored_columns: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_column_coverage(self) -> "PartMember":
        mapped = [self.part_number_column, self.part_name_column]
        if self.part_display_name_column is not None:
            mapped.append(self.part_display_name_column)
        _validate_column_coverage(self.headers, mapped, self.filters, self.ignored_columns)
        return self


class SpecimenLinkMember(CsvMember):
    code_column: str
    part_number_column: str
    link_type_column: str
    filters: dict[str, str] = Field(default_factory=dict)
    ignored_columns: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_column_coverage(self) -> "SpecimenLinkMember":
        _validate_column_coverage(
            self.headers,
            (self.code_column, self.part_number_column, self.link_type_column),
            self.filters,
            self.ignored_columns,
        )
        return self


class PanelMember(CsvMember):
    parent_id_column: str
    member_id_column: str
    panel_code_column: str
    member_code_column: str
    member_order_column: str
    relationship_column: str | None = None
    relationship_value: str | None = None
    exclude_self_links: bool = False
    filters: dict[str, str] = Field(default_factory=dict)
    preserved_metadata: dict[str, str] = Field(default_factory=dict)
    ignored_columns: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_column_coverage(self) -> "PanelMember":
        if (self.relationship_column is None) == (self.relationship_value is None):
            raise ValueError(
                "panel member requires exactly one relationship column or constant value"
            )
        mapped = [
            self.parent_id_column,
            self.member_id_column,
            self.panel_code_column,
            self.member_code_column,
            self.member_order_column,
        ]
        if self.relationship_column is not None:
            mapped.append(self.relationship_column)
        mapped.extend(self.preserved_metadata.values())
        _validate_column_coverage(
            self.headers,
            mapped,
            self.filters,
            self.ignored_columns,
        )
        if any(not key for key in self.preserved_metadata):
            raise ValueError("panel metadata keys must not be empty")
        return self


class LoincLayout(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    package_mode: Literal["combined", "split"]
    archive_limits: ArchiveLimits
    license: ArchiveMember
    core: CoreMember
    linguistic_variant: LinguisticVariantMember
    units: tuple[UnitMember, ...] = Field(min_length=1)
    parts: PartMember
    specimen_links: SpecimenLinkMember
    panel_members: PanelMember

    @classmethod
    def load(cls, path: Path) -> "LoincLayout":
        raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls.model_validate(raw)

    @model_validator(mode="after")
    def validate_archive_roles(self) -> "LoincLayout":
        core_members = (
            self.license,
            self.core,
            *self.units,
            self.parts,
            self.specimen_links,
            self.panel_members,
        )
        if any(member.archive != "core" for member in core_members):
            raise ValueError("LOINC core and accessory members must use the core archive")
        expected_translation_archive = (
            "core" if self.package_mode == "combined" else "linguistic-variant"
        )
        if self.linguistic_variant.archive != expected_translation_archive:
            raise ValueError(
                f"{self.package_mode} LOINC layout requires the linguistic variant in "
                f"the {expected_translation_archive} archive"
            )
        return self

    def csv_members(self) -> tuple[CsvMember, ...]:
        return (
            self.core,
            self.linguistic_variant,
            *self.units,
            self.parts,
            self.specimen_links,
            self.panel_members,
        )

    def archive_members(self) -> tuple[ArchiveMember, ...]:
        return (*self.csv_members(), self.license)


def _validate_column_coverage(
    headers: tuple[str, ...],
    mapped_columns: tuple[str, ...] | list[str],
    filters: Mapping[str, str],
    ignored_columns: dict[str, str],
) -> None:
    mapped = tuple(mapped_columns)
    if len(set(mapped)) != len(mapped):
        raise ValueError("a source column is mapped more than once")
    filter_columns = set(filters)
    ignored = set(ignored_columns)
    if any(not reason.strip() for reason in ignored_columns.values()):
        raise ValueError("ignored columns require a reason")
    overlap = (set(mapped) & filter_columns) | (set(mapped) & ignored) | (filter_columns & ignored)
    if overlap:
        raise ValueError(f"source columns have conflicting roles: {sorted(overlap)}")
    accounted = set(mapped) | filter_columns | ignored
    header_set = set(headers)
    missing = accounted - header_set
    if missing:
        raise ValueError(f"configured source columns are missing from headers: {sorted(missing)}")
    unexplained = header_set - accounted
    if unexplained:
        raise ValueError(f"source columns are not mapped or ignored: {sorted(unexplained)}")
