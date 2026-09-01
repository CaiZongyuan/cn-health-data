"""Cross-table validation for the adult laboratory runtime projection."""

from collections import defaultdict

from pydantic import BaseModel, ConfigDict, Field

from cn_health_compiler.sources.laboratory.records import (
    LaboratoryCatalog,
    LaboratoryPanelMemberRecord,
    LaboratoryReferenceRecord,
)


class LaboratoryValidationRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum_test_count: int = Field(ge=1)
    minimum_panel_count: int = Field(ge=1)
    allowed_sexes: list[str] = Field(min_length=1)
    allowed_reference_kinds: list[str] = Field(min_length=1)
    allowed_result_kinds: list[str] = Field(min_length=1)
    allowed_strategies: list[str] = Field(min_length=1)
    allowed_source_types: list[str] = Field(min_length=1)
    maximum_precision: int = Field(ge=0)
    required_test_codes: list[str] = Field(min_length=1)
    required_panel_codes: list[str] = Field(min_length=1)


class LaboratoryValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    record_count: int
    reference_count: int
    national_standard_reference_count: int
    panel_count: int
    panel_member_count: int
    quantity_count: int
    fixed_normal_count: int
    source_terminology_count: int
    panel_evidence_row_count: int


def validate_laboratory_catalog(
    catalog: LaboratoryCatalog,
    rules: LaboratoryValidationRules,
    *,
    terminology_count: int,
    evidence_names: dict[int, str],
) -> LaboratoryValidationReport:
    tests = {record.code: record for record in catalog.tests}
    if len(tests) != len(catalog.tests):
        raise ValueError("duplicate laboratory test code")
    if len(tests) < rules.minimum_test_count:
        raise ValueError("laboratory simulation-ready test count is below the minimum")
    missing_tests = sorted(set(rules.required_test_codes) - tests.keys())
    if missing_tests:
        raise ValueError(f"required laboratory tests are missing: {', '.join(missing_tests)}")

    references_by_test: dict[str, list[LaboratoryReferenceRecord]] = defaultdict(list)
    reference_keys: set[tuple[str, str]] = set()
    for reference in catalog.references:
        test = tests.get(reference.test_code)
        if test is None:
            raise ValueError(f"reference has unknown test: {reference.test_code}")
        key = (reference.test_code, reference.sex)
        if key in reference_keys:
            raise ValueError(
                f"duplicate laboratory reference: {reference.test_code}/{reference.sex}"
            )
        reference_keys.add(key)
        references_by_test[reference.test_code].append(reference)
        if reference.sex not in rules.allowed_sexes:
            raise ValueError(f"invalid reference sex: {reference.test_code}")
        if reference.reference_kind not in rules.allowed_reference_kinds:
            raise ValueError(f"invalid reference kind: {reference.test_code}")
        if reference.source_type not in rules.allowed_source_types:
            raise ValueError(f"invalid reference source type: {reference.test_code}")
        provenance = (
            reference.source_standard,
            reference.source_version,
            reference.source_location,
            reference.notes,
        )
        if not all(provenance):
            raise ValueError(f"reference provenance is incomplete: {reference.test_code}")
        _validate_reference_values(reference)

    for test in catalog.tests:
        if test.result_kind not in rules.allowed_result_kinds:
            raise ValueError(f"invalid result kind: {test.code}")
        if test.healthy_strategy not in rules.allowed_strategies:
            raise ValueError(f"invalid healthy strategy: {test.code}")
        if not 0 <= test.precision <= rules.maximum_precision:
            raise ValueError(f"invalid precision: {test.code}")
        references = references_by_test.get(test.code, [])
        if not references:
            raise ValueError(f"laboratory test has no adult reference: {test.code}")
        sexes = {reference.sex for reference in references}
        if "all" in sexes and len(sexes) != 1:
            raise ValueError(f"sex=all cannot be mixed with sex-specific references: {test.code}")
        if "all" not in sexes and sexes != {"male", "female"}:
            raise ValueError(f"sex-specific references must include male and female: {test.code}")
        if test.result_kind == "quantity":
            if not test.unit_display or not test.unit_ucum or test.healthy_strategy != "uniform":
                raise ValueError(f"quantity test is missing unit or uniform strategy: {test.code}")
            for reference in references:
                if reference.reference_kind not in {"range", "upper-bound", "lower-bound"}:
                    raise ValueError(f"quantity test has a non-numeric reference: {test.code}")
                if reference.simulation_low is None or reference.simulation_high is None:
                    raise ValueError(f"quantity test has no simulation range: {test.code}")
        else:
            if test.unit_display or test.unit_ucum or test.healthy_strategy != "fixed-normal":
                raise ValueError(f"coded test has unit or non-fixed strategy: {test.code}")
            for reference in references:
                if reference.normal_value is None:
                    raise ValueError(f"coded test has no normal value: {test.code}")

    panels = {record.code: record for record in catalog.panels}
    if len(panels) != len(catalog.panels):
        raise ValueError("duplicate laboratory panel code")
    if len(panels) < rules.minimum_panel_count:
        raise ValueError("laboratory panel count is below the minimum")
    missing_panels = sorted(set(rules.required_panel_codes) - panels.keys())
    if missing_panels:
        raise ValueError(f"required laboratory panels are missing: {', '.join(missing_panels)}")

    members_by_panel: dict[str, list[LaboratoryPanelMemberRecord]] = defaultdict(list)
    member_keys: set[tuple[str, str]] = set()
    order_keys: set[tuple[str, int]] = set()
    for member in catalog.panel_members:
        if member.panel_code not in panels:
            raise ValueError(f"member has unknown panel: {member.panel_code}")
        if member.test_code not in tests:
            raise ValueError(f"panel member has unknown test: {member.test_code}")
        member_key = (member.panel_code, member.test_code)
        order_key = (member.panel_code, member.sort_order)
        if member_key in member_keys:
            raise ValueError(f"duplicate panel member: {member.panel_code}/{member.test_code}")
        if order_key in order_keys:
            raise ValueError(f"duplicate panel sort order: {member.panel_code}/{member.sort_order}")
        member_keys.add(member_key)
        order_keys.add(order_key)
        members_by_panel[member.panel_code].append(member)

    for panel in catalog.panels:
        members = members_by_panel.get(panel.code, [])
        if not members:
            raise ValueError(f"laboratory panel is empty: {panel.code}")
        orders = sorted(member.sort_order for member in members)
        if orders != list(range(1, len(members) + 1)):
            raise ValueError(f"laboratory panel sort order is not contiguous: {panel.code}")
        evidence_row = int(panel.source_location.rsplit(" ", 1)[1])
        if evidence_row not in evidence_names:
            raise ValueError(f"laboratory panel evidence row is unknown: {panel.code}")

    return LaboratoryValidationReport(
        record_count=len(tests),
        reference_count=len(catalog.references),
        national_standard_reference_count=sum(
            reference.source_type == "national-standard" for reference in catalog.references
        ),
        panel_count=len(panels),
        panel_member_count=len(catalog.panel_members),
        quantity_count=sum(test.result_kind == "quantity" for test in catalog.tests),
        fixed_normal_count=sum(test.healthy_strategy == "fixed-normal" for test in catalog.tests),
        source_terminology_count=terminology_count,
        panel_evidence_row_count=len(evidence_names),
    )


def _validate_reference_values(reference: LaboratoryReferenceRecord) -> None:
    kind = reference.reference_kind
    low = reference.low_value
    high = reference.high_value
    normal = reference.normal_value
    simulation_low = reference.simulation_low
    simulation_high = reference.simulation_high
    if kind == "range" and (low is None or high is None or low >= high):
        raise ValueError(f"invalid range reference: {reference.test_code}")
    if kind == "upper-bound" and (low is not None or high is None):
        raise ValueError(f"invalid upper-bound reference: {reference.test_code}")
    if kind == "lower-bound" and (low is None or high is not None):
        raise ValueError(f"invalid lower-bound reference: {reference.test_code}")
    if kind in {"coded", "ordinal"} and not normal:
        raise ValueError(f"coded or ordinal reference has no normal value: {reference.test_code}")
    if (simulation_low is None) != (simulation_high is None):
        raise ValueError(f"partial simulation range: {reference.test_code}")
    if simulation_low is not None and simulation_high is not None:
        if simulation_low >= simulation_high:
            raise ValueError(f"invalid simulation range: {reference.test_code}")
        if kind == "range":
            assert low is not None and high is not None
            if simulation_low < low or simulation_high > high:
                raise ValueError(
                    f"simulation range exceeds reference range: {reference.test_code}"
                )
        if kind == "upper-bound":
            assert high is not None
            if simulation_high > high:
                raise ValueError(f"simulation range exceeds upper bound: {reference.test_code}")
        if kind == "lower-bound":
            assert low is not None
            if simulation_low < low:
                raise ValueError(f"simulation range is below lower bound: {reference.test_code}")
