"""Fail-closed provider boundary for translation batches."""

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol, Self

import rfc8785
from pydantic import BaseModel, ConfigDict, Field, model_validator

from cn_health_compiler.core.manifest import write_json_atomic
from cn_health_compiler.synthetic.translation.batches import TranslationBatch

_NUMERIC_TOKEN = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?(?![A-Za-z])")


class TranslationResponseRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    translation_id: str = Field(alias="translationId", min_length=1)
    display_zh: str = Field(alias="displayZh", min_length=1)
    needs_review: bool = Field(alias="needsReview")
    notes: str | None = None


class TranslationBatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    schema_version: int = Field(alias="schemaVersion", default=1)
    batch_id: str = Field(alias="batchId", min_length=1)
    input_hash: str = Field(alias="inputHash", pattern=r"^[0-9a-f]{64}$")
    model: str = Field(min_length=1)
    prompt_version: str = Field(alias="promptVersion", min_length=1)
    records: tuple[TranslationResponseRecord, ...] = Field(min_length=1)
    response_hash: str | None = Field(alias="responseHash", default=None)

    @model_validator(mode="after")
    def validate_unique_records(self) -> Self:
        identifiers = [record.translation_id for record in self.records]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("translation response IDs must be unique")
        return self


class TranslationProvider(Protocol):
    @property
    def model_id(self) -> str: ...

    def translate(self, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...


def translation_provider_payload(batch: TranslationBatch) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "batchId": batch.batch_id,
        "inputHash": batch.input_hash,
        "promptVersion": batch.prompt_version,
        "glossary": batch.glossary,
        "records": [record.model_dump(by_alias=True) for record in batch.records],
    }


def validate_translation_response(
    batch: TranslationBatch,
    response: Mapping[str, Any],
    *,
    model_id: str,
) -> TranslationBatchResponse:
    envelope = TranslationBatchResponse.model_validate(
        {
            **response,
            "model": model_id,
            "promptVersion": batch.prompt_version,
            "responseHash": None,
        }
    )
    if envelope.schema_version != 1:
        raise ValueError("translation response schema is unsupported")
    if (envelope.batch_id, envelope.input_hash) != (batch.batch_id, batch.input_hash):
        raise ValueError("translation response does not belong to this batch")
    expected = {record.translation_id for record in batch.records}
    actual = {record.translation_id for record in envelope.records}
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"translation response ID mismatch: missing={missing}, extra={extra}")
    source_records = {record.translation_id: record for record in batch.records}
    for record in envelope.records:
        source_numbers = _NUMERIC_TOKEN.findall(
            source_records[record.translation_id].source_display
        )
        missing_numbers = [value for value in source_numbers if value not in record.display_zh]
        if missing_numbers:
            raise ValueError(
                f"translation response changed numeric tokens for {record.translation_id}: "
                f"{missing_numbers}"
            )
    canonical = envelope.model_dump(by_alias=True, exclude={"response_hash"})
    response_hash = hashlib.sha256(rfc8785.dumps(canonical)).hexdigest()
    return envelope.model_copy(update={"response_hash": response_hash})


def translate_batch(
    provider: TranslationProvider,
    batch: TranslationBatch,
) -> TranslationBatchResponse:
    response = provider.translate(translation_provider_payload(batch))
    return validate_translation_response(batch, response, model_id=provider.model_id)


def load_cached_translation_response(
    path: Path,
    batch: TranslationBatch,
) -> TranslationBatchResponse | None:
    if not path.exists():
        return None
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("cached translation response must be a JSON object")
    response = TranslationBatchResponse.model_validate(raw)
    if (response.batch_id, response.input_hash, response.prompt_version) != (
        batch.batch_id,
        batch.input_hash,
        batch.prompt_version,
    ):
        raise ValueError("cached translation response does not match batch")
    canonical = response.model_dump(by_alias=True, exclude={"response_hash"})
    expected_hash = hashlib.sha256(rfc8785.dumps(canonical)).hexdigest()
    if response.response_hash != expected_hash:
        raise ValueError("cached translation response hash is invalid")
    return response


def write_translation_response(path: Path, response: TranslationBatchResponse) -> tuple[str, int]:
    return write_json_atomic(path, response.model_dump(by_alias=True))
