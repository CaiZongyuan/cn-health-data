"""Canonical records produced from a pinned official LOINC package."""

from dataclasses import dataclass


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
    short_name: str | None
    consumer_name: str | None
    class_name: str | None
    class_type: int | None
    order_obs: str | None
    status: str
    status_reason: str | None
    status_text: str | None
    change_type: str | None
    definition_description: str | None
    version_first_released: str | None
    version_last_changed: str | None
    panel_type: str | None
    zh_display: str | None
    source_metadata_json: str
    translation_metadata_json: str
    source_row: int
    translation_source_row: int | None
    source_version: str
    core_source_sha256: str
    translation_source_sha256: str


@dataclass(frozen=True, slots=True)
class LoincUnitRecord:
    loinc_code: str
    ucum_unit: str
    unit_kind: str
    unit_ordinal: int
    source_member: str
    source_row: int
    source_sha256: str


@dataclass(frozen=True, slots=True)
class LoincSpecimenRecord:
    loinc_code: str
    part_number: str
    part_name: str
    part_display_name: str | None
    link_type: str
    source_member: str
    source_row: int
    source_sha256: str


@dataclass(frozen=True, slots=True)
class LoincPanelMemberRecord:
    parent_id: str
    member_id: str
    panel_code: str
    member_code: str
    member_order: int
    relationship: str
    source_metadata_json: str
    source_member: str
    source_row: int
    source_sha256: str


@dataclass(frozen=True, slots=True)
class SourceMemberInspection:
    role: str
    archive_role: str
    member: str
    uncompressed_sha256: str
    uncompressed_size_bytes: int
    row_count: int


@dataclass(frozen=True, slots=True)
class LoincPackageRecords:
    concepts: tuple[LoincRecord, ...]
    units: tuple[LoincUnitRecord, ...]
    specimens: tuple[LoincSpecimenRecord, ...]
    panel_members: tuple[LoincPanelMemberRecord, ...]
    source_members: tuple[SourceMemberInspection, ...]
