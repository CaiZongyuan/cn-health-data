import hashlib
import json
from pathlib import Path

from cn_health_compiler.synthetic.translation.inventory import (
    FieldClassification,
    build_translation_inventory,
    scan_fhir_bundle,
    scan_synthea_modules,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_module_inventory_is_recursive_deduplicated_and_deterministic(tmp_path: Path) -> None:
    modules = tmp_path / "modules"
    _write_json(
        modules / "zeta.json",
        {
            "name": "Zeta",
            "states": {
                "Condition": {
                    "type": "ConditionOnset",
                    "codes": [{"system": "SNOMED-CT", "code": "44054006", "display": "Diabetes"}],
                }
            },
        },
    )
    _write_json(
        modules / "nested" / "alpha.json",
        {
            "name": "Alpha",
            "states": {
                "Observation": {
                    "type": "Observation",
                    "codes": [
                        {"system": "LOINC", "code": "4548-4", "display": "Hemoglobin A1c"},
                        {"system": "SNOMED-CT", "code": "44054006", "display": "Diabetes"},
                    ],
                }
            },
        },
    )

    first = scan_synthea_modules(modules)
    second = scan_synthea_modules(modules)

    assert first.to_json_bytes() == second.to_json_bytes()
    assert first.module_count == 2
    assert first.occurrence_count == 3
    assert [(record.source_system, record.source_code) for record in first.records] == [
        ("LOINC", "4548-4"),
        ("SNOMED-CT", "44054006"),
    ]
    diabetes = first.records[1]
    assert diabetes.occurrence_count == 2
    assert len(diabetes.translation_id) == 64
    assert [context.module for context in diabetes.contexts] == ["nested/alpha.json", "zeta.json"]
    assert all(
        context.json_path.endswith("/codes/1") or context.json_path.endswith("/codes/0")
        for context in diabetes.contexts
    )
    assert first.content_hash == hashlib.sha256(first.content_bytes()).hexdigest()


def test_module_inventory_reports_display_conflicts_and_unknown_system(tmp_path: Path) -> None:
    modules = tmp_path / "modules"
    _write_json(
        modules / "conflict.json",
        {
            "states": {
                "A": {
                    "type": "ConditionOnset",
                    "codes": [
                        {"system": "SNOMED-CT", "code": "1", "display": "First"},
                        {"system": "SNOMED-CT", "code": "1", "display": "Second"},
                        {"system": "LOCAL", "code": "x", "display": "Local concept"},
                    ],
                }
            }
        },
    )

    inventory = scan_synthea_modules(modules)

    assert len(inventory.conflicts) == 1
    assert inventory.conflicts[0].source_displays == ("First", "Second")
    assert inventory.unknown_code_systems == ("LOCAL",)


def test_fhir_collector_uses_actual_paths_and_excludes_claims() -> None:
    bundle = {
        "resourceType": "Bundle",
        "entry": [
            {
                "resource": {
                    "resourceType": "Observation",
                    "code": {
                        "coding": [
                            {
                                "system": "http://loinc.org",
                                "version": "2.83",
                                "code": "4548-4",
                                "display": "Hemoglobin A1c",
                            }
                        ],
                        "text": "Hemoglobin A1c",
                    },
                }
            },
            {
                "resource": {
                    "resourceType": "Claim",
                    "type": {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/claim-type",
                                "code": "professional",
                                "display": "Professional",
                            }
                        ]
                    },
                }
            },
        ],
        "meta": {
            "tag": [
                {
                    "system": "urn:cn-health-data:synthea-profile",
                    "code": "profile",
                    "display": "hash",
                }
            ]
        },
    }

    inventory = scan_fhir_bundle(bundle, source_name="patient.json")

    assert inventory.records[0].contexts[0].json_path == "/entry/0/resource/code/coding/0"
    assert inventory.records[0].contexts[0].resource_type == "Observation"
    claim = inventory.records[1]
    assert claim.classification is FieldClassification.EXCLUDE
    assert claim.contexts[0].resource_type == "Claim"
    profile_tag = inventory.records[2]
    assert profile_tag.classification is FieldClassification.KEEP


def test_combined_inventory_merges_sources_without_reading_strings_as_json(tmp_path: Path) -> None:
    modules = tmp_path / "modules"
    _write_json(
        modules / "module.json",
        {"codes": [{"system": "LOINC", "code": "123", "display": "A test"}]},
    )
    bundle_path = tmp_path / "bundle.json"
    _write_json(
        bundle_path,
        {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "resourceType": "DiagnosticReport",
                        "code": {
                            "coding": [{"system": "LOINC", "code": "123", "display": "A test"}]
                        },
                    }
                }
            ],
        },
    )

    inventory = build_translation_inventory(module_dir=modules, fhir_bundle_paths=[bundle_path])

    assert len(inventory.records) == 1
    assert inventory.records[0].occurrence_count == 2
    assert {context.source_kind for context in inventory.records[0].contexts} == {"fhir", "module"}
