"""Canonical validation and reporting for complete LOINC packages."""

from collections import Counter
from dataclasses import asdict
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from cn_health_compiler.sources.loinc.records import LoincPackageRecords


class RecordCountChangeRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_relative_decrease: float = Field(ge=0)
    max_relative_increase: float = Field(ge=0)


class LoincValidationRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_loinc_count: int = Field(ge=1)
    expected_unit_count: int = Field(ge=0)
    expected_specimen_count: int = Field(ge=0)
    expected_panel_member_count: int = Field(ge=0)
    expected_source_member_rows: dict[str, int]
    allowed_statuses: tuple[str, ...] = Field(min_length=1)
    allowed_order_obs: tuple[str, ...] = Field(min_length=1)
    allowed_unit_kinds: tuple[str, ...] = Field(min_length=1)
    allowed_specimen_link_types: tuple[str, ...] = Field(min_length=1)
    allowed_panel_relationships: tuple[str, ...] = Field(min_length=1)
    record_count: RecordCountChangeRules | None = None


class CoverageReport(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        frozen=True,
    )

    numerator: int
    denominator: int
    ratio: str


class SourceMemberReport(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        frozen=True,
    )

    role: str
    archive_role: str
    member: str
    uncompressed_sha256: str
    uncompressed_size_bytes: int
    row_count: int


class LoincValidationReport(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        frozen=True,
    )

    record_count: int
    source_version: str
    loinc_count: int
    translated_count: int
    untranslated_count: int
    translation_coverage: CoverageReport
    status_counts: dict[str, int]
    class_count: int
    panel_count: int
    panel_member_count: int
    unit_count: int
    loinc_with_unit_count: int
    unit_coverage: CoverageReport
    specimen_link_count: int
    loinc_with_specimen_count: int
    source_members: tuple[SourceMemberReport, ...]


def validate_loinc_package(
    records: LoincPackageRecords,
    rules: LoincValidationRules,
) -> LoincValidationReport:
    concepts = records.concepts
    codes = {record.code for record in concepts}
    if len(codes) != len(concepts):
        raise ValueError("LOINC codes are not unique")
    if len(concepts) != rules.expected_loinc_count:
        raise ValueError(
            f"LOINC count changed: expected {rules.expected_loinc_count}, found {len(concepts)}"
        )
    source_versions = {record.source_version for record in concepts}
    if len(source_versions) != 1:
        raise ValueError("LOINC records contain inconsistent source versions")
    source_version = next(iter(source_versions))

    allowed_statuses = set(rules.allowed_statuses)
    unexpected_statuses = {record.status for record in concepts} - allowed_statuses
    if unexpected_statuses:
        raise ValueError(f"unknown LOINC statuses: {sorted(unexpected_statuses)}")
    allowed_order_obs = set(rules.allowed_order_obs)
    unexpected_order_obs = {
        record.order_obs
        for record in concepts
        if record.order_obs is not None and record.order_obs not in allowed_order_obs
    }
    if unexpected_order_obs:
        raise ValueError(f"unknown LOINC ORDER_OBS values: {sorted(unexpected_order_obs)}")

    _validate_units(records, rules, codes)
    _validate_specimens(records, rules, codes)
    _validate_panels(records, rules, codes)
    source_members = _validate_source_members(records, rules)

    translated_count = sum(record.zh_display is not None for record in concepts)
    loinc_with_units = {record.loinc_code for record in records.units}
    loinc_with_specimens = {record.loinc_code for record in records.specimens}
    panel_codes = {record.panel_code for record in records.panel_members}
    status_counts = dict(sorted(Counter(record.status for record in concepts).items()))
    total_count = (
        len(concepts) + len(records.units) + len(records.specimens) + len(records.panel_members)
    )
    return LoincValidationReport(
        record_count=total_count,
        source_version=source_version,
        loinc_count=len(concepts),
        translated_count=translated_count,
        untranslated_count=len(concepts) - translated_count,
        translation_coverage=_coverage(translated_count, len(concepts)),
        status_counts=status_counts,
        class_count=len(
            {record.class_name for record in concepts if record.class_name is not None}
        ),
        panel_count=len(panel_codes),
        panel_member_count=len(records.panel_members),
        unit_count=len(records.units),
        loinc_with_unit_count=len(loinc_with_units),
        unit_coverage=_coverage(len(loinc_with_units), len(concepts)),
        specimen_link_count=len(records.specimens),
        loinc_with_specimen_count=len(loinc_with_specimens),
        source_members=source_members,
    )


def _validate_units(
    records: LoincPackageRecords,
    rules: LoincValidationRules,
    codes: set[str],
) -> None:
    if len(records.units) != rules.expected_unit_count:
        raise ValueError(
            f"LOINC unit count changed: expected {rules.expected_unit_count}, "
            f"found {len(records.units)}"
        )
    if any(record.loinc_code not in codes for record in records.units):
        raise ValueError("LOINC unit references an unknown code")
    unknown_kinds = {record.unit_kind for record in records.units} - set(rules.allowed_unit_kinds)
    if unknown_kinds:
        raise ValueError(f"unknown LOINC unit kinds: {sorted(unknown_kinds)}")


def _validate_specimens(
    records: LoincPackageRecords,
    rules: LoincValidationRules,
    codes: set[str],
) -> None:
    if len(records.specimens) != rules.expected_specimen_count:
        raise ValueError(
            f"LOINC specimen count changed: expected {rules.expected_specimen_count}, "
            f"found {len(records.specimens)}"
        )
    if any(record.loinc_code not in codes for record in records.specimens):
        raise ValueError("LOINC specimen link references an unknown code")
    unknown_types = {record.link_type for record in records.specimens} - set(
        rules.allowed_specimen_link_types
    )
    if unknown_types:
        raise ValueError(f"unknown LOINC specimen link types: {sorted(unknown_types)}")


def _validate_panels(
    records: LoincPackageRecords,
    rules: LoincValidationRules,
    codes: set[str],
) -> None:
    if len(records.panel_members) != rules.expected_panel_member_count:
        raise ValueError(
            f"LOINC panel-member count changed: expected {rules.expected_panel_member_count}, "
            f"found {len(records.panel_members)}"
        )
    if any(
        record.panel_code not in codes or record.member_code not in codes
        for record in records.panel_members
    ):
        raise ValueError("LOINC panel edge references an unknown code")
    unknown_relationships = {record.relationship for record in records.panel_members} - set(
        rules.allowed_panel_relationships
    )
    if unknown_relationships:
        raise ValueError(f"unknown LOINC panel relationships: {sorted(unknown_relationships)}")


def _validate_source_members(
    records: LoincPackageRecords,
    rules: LoincValidationRules,
) -> tuple[SourceMemberReport, ...]:
    by_role = {inspection.role: inspection for inspection in records.source_members}
    if len(by_role) != len(records.source_members):
        raise ValueError("LOINC source-member roles are not unique")
    expected_roles = set(rules.expected_source_member_rows)
    if set(by_role) != expected_roles:
        raise ValueError(
            "LOINC source-member roles changed: "
            f"expected {sorted(expected_roles)}, found {sorted(by_role)}"
        )
    for role, expected_count in rules.expected_source_member_rows.items():
        actual = by_role[role].row_count
        if actual != expected_count:
            raise ValueError(
                f"LOINC source member {role!r} row count changed: "
                f"expected {expected_count}, found {actual}"
            )
    return tuple(
        SourceMemberReport.model_validate(asdict(inspection))
        for inspection in records.source_members
    )


def _coverage(numerator: int, denominator: int) -> CoverageReport:
    ratio = Decimal(numerator) / Decimal(denominator) if denominator else Decimal(0)
    return CoverageReport(numerator=numerator, denominator=denominator, ratio=f"{ratio:.6f}")
