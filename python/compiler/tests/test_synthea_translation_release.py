import json
from collections import Counter
from pathlib import Path

from cn_health_compiler.synthetic.translation.catalog import load_catalog, load_glossary
from jsonschema import Draft202012Validator, FormatChecker

REPO_ROOT = Path(__file__).resolve().parents[3]
TRANSLATION_ROOT = REPO_ROOT / "translations" / "synthea-zh-cn"


def test_committed_synthea_translation_catalog_matches_coverage_contract() -> None:
    catalog = load_catalog(TRANSLATION_ROOT / "catalog.jsonl")
    overrides = load_catalog(TRANSLATION_ROOT / "overrides.jsonl")
    coverage = json.loads((TRANSLATION_ROOT / "coverage.json").read_text(encoding="utf-8"))

    assert len(catalog.records) == coverage["catalogRecords"] == 2_180
    assert catalog.sha256 == coverage["catalogHash"]
    assert coverage["moduleInventory"] == {
        "moduleCount": 242,
        "records": 2_149,
        "covered": 2_149,
        "gaps": 0,
    }
    assert coverage["exporterInventory"] == {"records": 27, "covered": 27, "gaps": 0}
    assert Counter(record.review_status for record in catalog.records) == {
        "approved": 22,
        "machine-checked": 2_158,
    }
    assert sum(record.needs_review for record in catalog.records) == 0
    assert len(overrides.records) == 18
    assert all(
        catalog.lookup(*record.key) == record and record.review_status == "approved"
        for record in overrides.records
    )
    assert len(load_glossary(TRANSLATION_ROOT / "glossary.yaml")) == 12


def test_translation_review_resolutions_are_complete_and_match_catalog() -> None:
    catalog = load_catalog(TRANSLATION_ROOT / "catalog.jsonl")
    schema = json.loads(
        (REPO_ROOT / "schemas" / "translation-review-resolution.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    resolutions = [
        json.loads(line)
        for line in (TRANSLATION_ROOT / "review-resolutions.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]

    assert len(resolutions) == 51
    assert sum(record["upstreamIssue"] for record in resolutions) == 18
    assert not [error for record in resolutions for error in validator.iter_errors(record)]
    assert all(
        (translated := catalog.lookup(
            record["sourceSystem"], record["sourceVersion"], record["sourceCode"]
        ))
        is not None
        and translated.display_zh == record["finalDisplayZh"]
        and not translated.needs_review
        for record in resolutions
    )
