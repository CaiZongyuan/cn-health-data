from typing import Any

import pytest
from cn_health_compiler.synthetic.translation.catalog import (
    TranslationCatalog,
    TranslationRecord,
    translation_id,
)
from cn_health_compiler.synthetic.translation.inventory import (
    FieldClassification,
    InventoryRecord,
    SourceContext,
    TranslationInventory,
)
from cn_health_compiler.synthetic.translation.projector import project_bundle
from cn_health_compiler.synthetic.translation.validation import (
    ProjectionValidationError,
    validate_inventory_coverage,
    validate_projection,
)


class _Catalog:
    def lookup(
        self, system: str, version: str | None, code: str, source_display: str
    ) -> str | None:
        return {"1": "血压", "2": "收缩压"}.get(code)

    def review_status(
        self, system: str, version: str | None, code: str, source_display: str
    ) -> str | None:
        return {"1": "approved", "2": "machine-checked"}.get(code)


def _bundle() -> dict[str, Any]:
    def coding(code: str, display: str) -> dict[str, str]:
        return {
            "system": "http://loinc.org",
            "version": "2.83",
            "code": code,
            "display": display,
        }

    return {
        "resourceType": "Bundle",
        "entry": [
            {"fullUrl": "urn:uuid:p", "resource": {"resourceType": "Patient", "id": "p"}},
            {
                "fullUrl": "urn:uuid:o",
                "resource": {
                    "resourceType": "Observation",
                    "id": "o",
                    "status": "final",
                    "effectiveDateTime": "2026-08-30T00:00:00Z",
                    "code": {"coding": [coding("1", "Blood pressure")]},
                    "component": [{"code": {"coding": [coding("2", "Systolic pressure")]}}],
                    "valueQuantity": {
                        "value": 120,
                        "unit": "mmHg",
                        "system": "http://unitsofmeasure.org",
                        "code": "mm[Hg]",
                    },
                    "subject": {"reference": "urn:uuid:p"},
                },
            },
            {"fullUrl": "urn:uuid:claim", "resource": {"resourceType": "Claim", "id": "c"}},
            {
                "fullUrl": "urn:uuid:dependent",
                "resource": {
                    "resourceType": "Basic",
                    "id": "b",
                    "subject": {"reference": "urn:uuid:claim"},
                },
            },
        ],
    }


def test_validates_invariants_and_reports_deterministic_coverage() -> None:
    source = _bundle()
    projected = project_bundle(source, _Catalog(), release_id="r1", content_hash="hash").bundle

    report = validate_projection(source, projected, review_lookup=_Catalog())

    assert (report.total, report.translated, report.gap) == (2, 2, 0)
    assert [(row.dimension, row.key, row.translated, row.gap) for row in report.coverage] == [
        ("code-system", "http://loinc.org", 2, 0),
        ("resource-type", "Observation", 2, 0),
    ]
    assert [(item.review_status, item.count) for item in report.review_statuses] == [
        ("approved", 1),
        ("machine-checked", 1),
    ]
    assert report.removed_resources == ("Basic/b", "Claim/c")


@pytest.mark.parametrize(
    ("path", "bad_value"),
    [
        (("status",), "amended"),
        (("effectiveDateTime",), "2027-01-01T00:00:00Z"),
        (("valueQuantity", "value"), 121),
        (("valueQuantity", "unit"), "kPa"),
        (("valueQuantity", "code"), "kPa"),
        (("subject", "reference"), "Patient/other"),
        (("code", "coding", 0, "code"), "changed"),
        (("code", "coding", 0, "system"), "http://example.invalid"),
        (("code", "coding", 0, "version"), "old"),
    ],
)
def test_rejects_machine_value_changes(path: tuple[str | int, ...], bad_value: Any) -> None:
    source = _bundle()
    projected = project_bundle(source, _Catalog(), release_id="r1", content_hash="hash").bundle
    target: Any = projected["entry"][1]["resource"]
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = bad_value

    with pytest.raises(ProjectionValidationError, match="outside the display allowlist"):
        validate_projection(source, projected)


def test_rejects_translation_on_unknown_path() -> None:
    source = _bundle()
    source["entry"][1]["resource"]["extension"] = [{"valueString": "English"}]
    projected = project_bundle(source, _Catalog(), release_id="r1", content_hash="hash").bundle
    projected["entry"][1]["resource"]["extension"][0]["valueString"] = "中文"

    with pytest.raises(ProjectionValidationError, match="outside the display allowlist"):
        validate_projection(source, projected)


def test_rejects_removed_coding_display() -> None:
    source = _bundle()
    projected = project_bundle(source, _Catalog(), release_id="r1", content_hash="hash").bundle
    del projected["entry"][1]["resource"]["code"]["coding"][0]["display"]

    with pytest.raises(ProjectionValidationError, match="removed a required Coding.display"):
        validate_projection(source, projected)


def test_reports_untranslated_concept_as_gap() -> None:
    source = _bundle()
    source["entry"][1]["resource"]["component"].append(
        {
            "code": {
                "coding": [{"system": "http://snomed.info/sct", "code": "3", "display": "Unknown"}]
            }
        }
    )
    projected = project_bundle(source, _Catalog(), release_id="r1", content_hash="hash").bundle

    report = validate_projection(source, projected, review_lookup=_Catalog())

    assert (report.total, report.translated, report.gap) == (3, 2, 1)
    assert report.coverage[-1].key == "Observation"
    assert (report.coverage[-1].translated, report.coverage[-1].gap) == (2, 1)


def test_rejects_unexpected_resource_removal_or_reordering() -> None:
    source = _bundle()
    projected = project_bundle(source, _Catalog(), release_id="r1", content_hash="hash").bundle
    projected["entry"].reverse()

    with pytest.raises(ProjectionValidationError, match="fullUrl changed"):
        validate_projection(source, projected)


def test_static_inventory_coverage_does_not_depend_on_generated_paths() -> None:
    source = InventoryRecord(
        "LOINC",
        None,
        "1",
        "Example test",
        FieldClassification.DISPLAY_LOOKUP,
        1,
        (SourceContext("module", "test.json", "/codes/0"),),
    )
    inventory = TranslationInventory((source,), (), (), 1, 1)
    translated = TranslationRecord(
        translation_id=translation_id("LOINC", None, "1"),
        source_system="LOINC",
        source_version=None,
        source_code="1",
        source_display="Example test",
        display_zh="示例检验",
        domains=("laboratory",),
        method="machine-checked",
        review_status="machine-checked",
        needs_review=False,
        provenance_id="batch-1",
    )

    report = validate_inventory_coverage(
        inventory,
        TranslationCatalog([translated]),
        accepted_review_statuses=frozenset({"machine-checked"}),
    )

    assert (report.total, report.covered, report.gap, report.needs_review) == (1, 1, 0, 0)
    assert report.missing_translation_ids == ()
