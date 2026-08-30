import hashlib

import pytest
from cn_health_compiler.synthetic.translation.api import (
    load_cached_translation_response,
    translate_batch,
    write_translation_response,
)
from cn_health_compiler.synthetic.translation.batches import (
    TranslationBatchRecord,
    make_translation_batches,
)


def _record(identifier: str, system: str, code: str, display: str) -> TranslationBatchRecord:
    return TranslationBatchRecord(
        translationId=identifier,
        sourceSystem=system,
        sourceCode=code,
        sourceDisplay=display,
        domains=("condition",),
    )


def test_batches_are_bounded_grouped_and_deterministic() -> None:
    records = [
        _record("c", "SNOMED-CT", "3", "Third disorder"),
        _record("a", "LOINC", "1", "First test"),
        _record("b", "SNOMED-CT", "2", "Second disorder"),
    ]
    arguments = {
        "inventory_hash": hashlib.sha256(b"inventory").hexdigest(),
        "prompt_version": "clinical-display-zh-v1",
        "glossary": {"disorder": "疾病"},
        "max_records": 1,
    }

    first = make_translation_batches(records, **arguments)
    repeated = make_translation_batches(reversed(records), **arguments)

    assert first == repeated
    assert [batch.records[0].translation_id for batch in first] == ["a", "b", "c"]
    assert all(len(batch.records) == 1 for batch in first)
    assert all(batch.batch_id.startswith("batch-") for batch in first)


class _Provider:
    model_id = "fixture-model"

    def translate(self, payload: dict[str, object]) -> dict[str, object]:
        records = payload["records"]
        assert isinstance(records, list)
        return {
            "schemaVersion": 1,
            "batchId": payload["batchId"],
            "inputHash": payload["inputHash"],
            "records": [
                {
                    "translationId": record["translationId"],
                    "displayZh": "测试译名",
                    "needsReview": False,
                    "notes": None,
                }
                for record in records
            ],
        }


def test_provider_response_is_exact_and_cache_is_verified(tmp_path) -> None:
    batch = make_translation_batches(
        [_record("a", "LOINC", "1", "First test")],
        inventory_hash=hashlib.sha256(b"inventory").hexdigest(),
        prompt_version="v1",
    )[0]

    response = translate_batch(_Provider(), batch)
    output = tmp_path / "batch.json"
    write_translation_response(output, response)

    assert load_cached_translation_response(output, batch) == response
    assert response.response_hash is not None


class _IncompleteProvider(_Provider):
    def translate(self, payload: dict[str, object]) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "batchId": payload["batchId"],
            "inputHash": payload["inputHash"],
            "records": [],
        }


def test_provider_response_fails_closed_on_missing_records() -> None:
    batch = make_translation_batches(
        [_record("a", "LOINC", "1", "First test")],
        inventory_hash=hashlib.sha256(b"inventory").hexdigest(),
        prompt_version="v1",
    )[0]

    with pytest.raises(ValueError):
        translate_batch(_IncompleteProvider(), batch)


class _ChangedNumberProvider(_Provider):
    def translate(self, payload: dict[str, object]) -> dict[str, object]:
        response = super().translate(payload)
        records = response["records"]
        assert isinstance(records, list)
        records[0]["displayZh"] = "每日两次"
        return response


def test_provider_response_preserves_standalone_numeric_tokens() -> None:
    batch = make_translation_batches(
        [_record("a", "RxNorm", "1", "Take 2 times daily")],
        inventory_hash=hashlib.sha256(b"inventory").hexdigest(),
        prompt_version="v1",
    )[0]

    with pytest.raises(ValueError, match="numeric tokens"):
        translate_batch(_ChangedNumberProvider(), batch)
