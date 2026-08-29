import json
from pathlib import Path

from cn_health_compiler.core.validation import validate_dataset_contracts
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_json_schemas_are_valid_draft_2020_12() -> None:
    schema_paths = sorted((REPO_ROOT / "schemas").glob("*.schema.json"))

    assert len(schema_paths) == 5
    for schema_path in schema_paths:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)


def test_dataset_contracts_validate() -> None:
    validated = validate_dataset_contracts(REPO_ROOT)

    assert [path.parent.name for path in validated] == [
        "geography-cn",
        "loinc-zh-cn",
        "names-cn",
        "nhc-icd10-clinical",
        "nhc-procedure-clinical",
        "nhsa-drugs",
    ]
