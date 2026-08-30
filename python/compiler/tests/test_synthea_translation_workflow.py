import json
from pathlib import Path

import pytest
from cn_health_compiler.synthetic.translation.catalog import load_catalog
from cn_health_compiler.synthetic.translation.inventory import (
    FieldClassification,
    InventoryConflict,
    InventoryRecord,
    SourceContext,
    TranslationInventory,
)
from cn_health_compiler.synthetic.translation.workflow import (
    batches_from_inventory,
    merge_draft_responses,
    merge_translation_responses,
    write_catalog_jsonl,
)


def _inventory() -> TranslationInventory:
    context = SourceContext("module", "condition.json", "/codes/0", "condition.json", "Condition")
    record = InventoryRecord(
        "SNOMED-CT",
        None,
        "1",
        "Example disorder",
        FieldClassification.DISPLAY_LOOKUP,
        1,
        (context,),
    )
    return TranslationInventory(
        (record,),
        (InventoryConflict("SNOMED-CT", None, "1", ("Example disorder", "Example disease")),),
        (),
        1,
        1,
    )


def test_draft_responses_are_exact_and_conflicts_require_review(tmp_path: Path) -> None:
    inventory = _inventory()
    batches = batches_from_inventory(inventory, prompt_version="v1", max_records=30)
    batch = batches[0]
    response = {
        "schemaVersion": 1,
        "batchId": batch.batch_id,
        "inputHash": batch.input_hash,
        "records": [
            {
                "translationId": batch.records[0].translation_id,
                "displayZh": "示例疾病",
                "needsReview": False,
                "notes": None,
            }
        ],
    }

    catalog = merge_draft_responses(
        batches,
        {batch.batch_id: response},
        model_id="fixture-model",
        conflicts=frozenset({("SNOMED-CT", None, "1")}),
    )
    record = catalog.records[0]
    assert record.needs_review is True
    assert record.review_status == "machine-draft"
    assert record.model == "fixture-model"

    output = tmp_path / "catalog.jsonl"
    write_catalog_jsonl(output, catalog)
    assert load_catalog(output).records == catalog.records


def test_draft_merge_fails_on_missing_or_extra_batch() -> None:
    batches = batches_from_inventory(_inventory(), prompt_version="v1")

    with pytest.raises(ValueError, match="missing translation response"):
        merge_draft_responses(batches, {}, model_id="fixture-model")
    with pytest.raises(ValueError, match="unexpected translation responses"):
        merge_draft_responses((), {"extra": json.loads("{}")}, model_id="fixture-model")


def test_checked_response_records_review_stage() -> None:
    inventory = _inventory()
    batches = batches_from_inventory(inventory, prompt_version="v1")
    batch = batches[0]
    response = {
        "schemaVersion": 1,
        "batchId": batch.batch_id,
        "inputHash": batch.input_hash,
        "records": [
            {
                "translationId": batch.records[0].translation_id,
                "displayZh": "示例疾病",
                "needsReview": False,
                "notes": None,
            }
        ],
    }

    catalog = merge_translation_responses(
        batches,
        {batch.batch_id: response},
        model_id="review-model",
        method="machine-checked",
        review_status="machine-checked",
        prompt_version="review-v1",
    )

    assert catalog.records[0].review_status == "machine-checked"
    assert catalog.records[0].prompt_version == "review-v1"
