import json
from pathlib import Path

import pytest
from cn_health_compiler.sources.laboratory.records import iter_laboratory_records
from cn_health_compiler.synthetic.translation.catalog import (
    CatalogDisplayLookup,
    TranslationCatalog,
    TranslationCatalogError,
    TranslationRecord,
    catalog_sha256,
    load_catalog,
    load_glossary,
    merge_catalogs,
    project_laboratory_record,
    translation_id,
)
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[3]


def _record(**changes: object) -> TranslationRecord:
    values: dict[str, object] = {
        "sourceSystem": "http://loinc.org",
        "sourceVersion": "2.83",
        "sourceCode": "4548-4",
        "sourceDisplay": "Hemoglobin A1c",
        "displayZh": "糖化血红蛋白",
        "domains": ["laboratory"],
        "method": "machine",
        "reviewStatus": "machine-draft",
        "needsReview": True,
        "provenanceId": "batch-1",
        "translationId": translation_id("http://loinc.org", "2.83", "4548-4"),
    }
    values.update(changes)
    return TranslationRecord.model_validate(values)


def test_exact_lookup_includes_nullable_version() -> None:
    versionless = _record(
        sourceVersion=None,
        translationId=translation_id("http://loinc.org", None, "4548-4"),
    )
    catalog = TranslationCatalog([versionless])
    assert catalog.lookup("http://loinc.org", None, "4548-4") == versionless
    assert catalog.lookup("http://loinc.org", "2.83", "4548-4") is None


def test_catalog_display_lookup_normalizes_fhir_system_and_review_policy() -> None:
    draft = _record(
        sourceVersion=None,
        translationId=translation_id("http://loinc.org", None, "4548-4"),
    )
    catalog = TranslationCatalog([draft])

    strict = CatalogDisplayLookup(catalog)
    preview = CatalogDisplayLookup(catalog, accepted_review_statuses=frozenset({"machine-draft"}))

    assert strict.lookup("http://loinc.org", None, "4548-4", draft.source_display) is None
    assert (
        preview.lookup("http://loinc.org", None, "4548-4", draft.source_display) == draft.display_zh
    )
    assert (
        preview.review_status("http://loinc.org", None, "4548-4", draft.source_display)
        == "machine-draft"
    )


def test_machine_output_cannot_claim_approval() -> None:
    with pytest.raises(ValidationError, match="machine output"):
        _record(reviewStatus="approved", needsReview=False)


def test_duplicate_and_equal_precedence_conflicts_fail(tmp_path: Path) -> None:
    record = _record()
    path = tmp_path / "catalog.jsonl"
    line = json.dumps(record.model_dump(mode="json", by_alias=True), ensure_ascii=False)
    path.write_text(f"{line}\n{line}\n", encoding="utf-8")
    with pytest.raises(TranslationCatalogError, match="duplicate translationId"):
        load_catalog(path)
    with pytest.raises(TranslationCatalogError, match="conflicting"):
        merge_catalogs([record], [_record(displayZh="糖化血红蛋白检测")])


def test_approved_manual_override_has_precedence() -> None:
    override = _record(
        method="manual-override",
        reviewStatus="approved",
        needsReview=False,
        displayZh="糖化血红蛋白（人工）",
        provenanceId="override-1",
    )
    assert merge_catalogs([_record()], [override]).records == (override,)


def test_override_cannot_hide_source_display_conflict() -> None:
    override = _record(
        method="manual-override",
        reviewStatus="approved",
        needsReview=False,
        sourceDisplay="HbA1c assay",
        provenanceId="override-1",
    )
    with pytest.raises(TranslationCatalogError, match="source display"):
        merge_catalogs([_record()], [override])


def test_hash_is_deterministic_across_input_order() -> None:
    other = _record(
        sourceCode="8310-5",
        sourceDisplay="Body temperature",
        displayZh="体温",
        translationId=translation_id("http://loinc.org", "2.83", "8310-5"),
    )
    assert catalog_sha256([_record(), other]) == catalog_sha256([other, _record()])


def test_glossary_rejects_duplicate_sources(tmp_path: Path) -> None:
    path = tmp_path / "glossary.yaml"
    path.write_text(
        "schemaVersion: 1\nentries:\n"
        "  - {source: Blood, target: 血液}\n"
        "  - {source: Blood, target: 血}\n",
        encoding="utf-8",
    )
    with pytest.raises(TranslationCatalogError, match="duplicate glossary"):
        load_glossary(path)


def test_laboratory_catalog_projects_to_approved_translation() -> None:
    source = REPO_ROOT / "datasets/laboratory-cn/catalog.csv"
    record = next(
        iter_laboratory_records(source, source_version="2026-08-30", source_sha256="a" * 64)
    )
    projected = project_laboratory_record(
        record,
        provenance_id="laboratory-cn@2026-08-30.r1",
        source_display="Hematocrit [Volume Fraction] of Blood by calculation",
    )
    assert projected.review_status == "approved"
    assert projected.key == ("LOINC", None, record.code)
    assert projected.notes == "Chinese display curated against LOINC 2.83"
