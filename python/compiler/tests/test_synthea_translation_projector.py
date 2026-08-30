from typing import Any

from cn_health_compiler.synthetic.translation.projector import project_bundle


class _Lookup:
    def __init__(self, translations: dict[tuple[str, str | None, str, str], str]) -> None:
        self.translations = translations

    def lookup(
        self, system: str, version: str | None, code: str, source_display: str
    ) -> str | None:
        return self.translations.get((system, version, code, source_display))


def _coding(code: str, display: str, *, version: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"system": "http://snomed.info/sct", "code": code, "display": display}
    if version is not None:
        result["version"] = version
    return result


def test_projects_allowlisted_displays_without_mutating_source() -> None:
    source: dict[str, Any] = {
        "resourceType": "Bundle",
        "meta": {"tag": [{"system": "other", "code": "keep"}]},
        "entry": [
            {
                "fullUrl": "urn:uuid:obs",
                "resource": {
                    "resourceType": "Observation",
                    "id": "obs",
                    "status": "final",
                    "effectiveDateTime": "2026-08-30T12:00:00Z",
                    "code": {
                        "coding": [_coding("1", "Blood pressure", version="v1")],
                        "text": "Blood pressure",
                    },
                    "valueQuantity": {
                        "value": 120,
                        "unit": "mmHg",
                        "system": "http://unitsofmeasure.org",
                        "code": "mm[Hg]",
                    },
                    "component": [{"code": {"coding": [_coding("2", "Systolic pressure")]}}],
                },
            }
        ],
    }
    lookup = _Lookup(
        {
            ("http://snomed.info/sct", "v1", "1", "Blood pressure"): "血压",
            ("http://snomed.info/sct", None, "2", "Systolic pressure"): "收缩压",
        }
    )

    result = project_bundle(source, lookup, release_id="zh@r1", content_hash="abc123")

    observation = result.bundle["entry"][0]["resource"]
    assert observation["code"] == {
        "coding": [
            {"system": "http://snomed.info/sct", "version": "v1", "code": "1", "display": "血压"}
        ],
        "text": "血压",
    }
    assert observation["component"][0]["code"]["text"] == "收缩压"
    assert observation["valueQuantity"] == source["entry"][0]["resource"]["valueQuantity"]
    assert observation["effectiveDateTime"] == "2026-08-30T12:00:00Z"
    assert source["entry"][0]["resource"]["code"]["text"] == "Blood pressure"
    assert result.bundle["meta"]["tag"][-1] == {
        "system": "urn:cn-health-data:synthea-translation",
        "code": "zh@r1",
        "display": "abc123",
    }
    assert result.gaps == ()


def test_missing_translation_preserves_english_and_reports_deterministic_gap() -> None:
    source = {
        "resourceType": "Bundle",
        "entry": [
            {
                "resource": {
                    "resourceType": "Condition",
                    "id": "c1",
                    "code": {
                        "coding": [_coding("404", "Untranslated disease")],
                        "text": "Untranslated disease",
                    },
                }
            }
        ],
    }

    first = project_bundle(source, _Lookup({}), release_id="r", content_hash="h")
    second = project_bundle(source, _Lookup({}), release_id="r", content_hash="h")

    assert first == second
    assert (
        first.bundle["entry"][0]["resource"]["code"]["coding"][0]["display"]
        == "Untranslated disease"
    )
    assert first.bundle["entry"][0]["resource"]["code"]["text"] == "Untranslated disease"
    assert [(gap.resource_type, gap.path, gap.code) for gap in first.gaps] == [
        ("Condition", "code.coding[0]", "404")
    ]


def test_already_chinese_display_is_covered_without_lookup() -> None:
    source = {
        "resourceType": "Bundle",
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "p",
                    "communication": [
                        {
                            "language": {
                                "coding": [
                                    {
                                        "system": "urn:ietf:bcp:47",
                                        "code": "zh-CN",
                                        "display": "简体中文",
                                    }
                                ]
                            }
                        }
                    ],
                }
            }
        ],
    }

    result = project_bundle(source, _Lookup({}), release_id="r", content_hash="h")

    assert result.gaps == ()
    language = result.bundle["entry"][0]["resource"]["communication"][0]["language"]
    assert language["text"] == "简体中文"


def test_fail_closed_for_unknown_resource_and_unlisted_paths() -> None:
    source = {
        "resourceType": "Bundle",
        "entry": [
            {
                "resource": {
                    "resourceType": "Basic",
                    "id": "basic",
                    "code": {"coding": [_coding("1", "Basic label")]},
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": "obs",
                    "extension": [
                        {"valueCodeableConcept": {"coding": [_coding("2", "Extension label")]}}
                    ],
                }
            },
        ],
    }
    lookup = _Lookup(
        {
            ("http://snomed.info/sct", None, "1", "Basic label"): "基本",
            ("http://snomed.info/sct", None, "2", "Extension label"): "扩展",
        }
    )

    result = project_bundle(source, lookup, release_id="r", content_hash="h")

    assert result.bundle["entry"][0]["resource"]["code"]["coding"][0]["display"] == "Basic label"
    assert (
        result.bundle["entry"][1]["resource"]["extension"][0]["valueCodeableConcept"]["coding"][0][
            "display"
        ]
        == "Extension label"
    )
    assert result.gaps == ()


def test_excludes_claims_and_cascades_resources_that_reference_them() -> None:
    source = {
        "resourceType": "Bundle",
        "entry": [
            {"fullUrl": "urn:uuid:patient", "resource": {"resourceType": "Patient", "id": "p"}},
            {"fullUrl": "urn:uuid:claim", "resource": {"resourceType": "Claim", "id": "claim"}},
            {
                "fullUrl": "urn:uuid:obs",
                "resource": {
                    "resourceType": "Observation",
                    "id": "obs",
                    "derivedFrom": [{"reference": "urn:uuid:claim"}],
                },
            },
            {
                "fullUrl": "urn:uuid:report",
                "resource": {
                    "resourceType": "DiagnosticReport",
                    "id": "report",
                    "result": [{"reference": "urn:uuid:obs"}],
                },
            },
            {"resource": {"resourceType": "ExplanationOfBenefit", "id": "eob"}},
        ],
    }

    result = project_bundle(source, _Lookup({}), release_id="r", content_hash="h")

    assert [entry["resource"]["resourceType"] for entry in result.bundle["entry"]] == ["Patient"]
    assert set(result.removed_resources) == {
        "Claim/claim",
        "DiagnosticReport/report",
        "ExplanationOfBenefit/eob",
        "Observation/obs",
    }


def test_replaces_existing_translation_tag_once() -> None:
    source = {
        "resourceType": "Bundle",
        "meta": {
            "tag": [
                {"system": "urn:cn-health-data:synthea-translation", "code": "old"},
                {"system": "other", "code": "stable"},
            ]
        },
        "entry": [],
    }
    result = project_bundle(source, _Lookup({}), release_id="new", content_hash="hash")
    assert result.bundle["meta"]["tag"] == [
        {"system": "other", "code": "stable"},
        {"system": "urn:cn-health-data:synthea-translation", "code": "new", "display": "hash"},
    ]


def test_projects_common_exporter_identity_and_care_paths() -> None:
    source = {
        "resourceType": "Bundle",
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "p",
                    "maritalStatus": {"coding": [_coding("M", "Married")]},
                }
            },
            {
                "resource": {
                    "resourceType": "CareTeam",
                    "id": "team",
                    "reasonCode": [{"coding": [_coding("1", "Hypertension")]}],
                }
            },
            {
                "resource": {
                    "resourceType": "MedicationRequest",
                    "id": "med",
                    "dosageInstruction": [
                        {"doseAndRate": [{"type": {"coding": [_coding("ordered", "Ordered")]}}]}
                    ],
                }
            },
        ],
    }
    lookup = _Lookup(
        {
            ("http://snomed.info/sct", None, "M", "Married"): "已婚",
            ("http://snomed.info/sct", None, "1", "Hypertension"): "高血压",
            ("http://snomed.info/sct", None, "ordered", "Ordered"): "医嘱剂量",
        }
    )

    result = project_bundle(source, lookup, release_id="r", content_hash="h")

    assert result.gaps == ()
    assert result.bundle["entry"][0]["resource"]["maritalStatus"]["text"] == "已婚"
    assert result.bundle["entry"][1]["resource"]["reasonCode"][0]["text"] == "高血压"
    assert (
        result.bundle["entry"][2]["resource"]["dosageInstruction"][0]["doseAndRate"][0]["type"][
            "text"
        ]
        == "医嘱剂量"
    )
