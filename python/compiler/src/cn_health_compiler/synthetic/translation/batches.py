"""Deterministic bounded batches for Synthea display translation."""

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any, Self

import rfc8785
from pydantic import BaseModel, ConfigDict, Field, model_validator


class TranslationBatchRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    translation_id: str = Field(alias="translationId", min_length=1)
    source_system: str = Field(alias="sourceSystem", min_length=1)
    source_version: str | None = Field(alias="sourceVersion", default=None)
    source_code: str = Field(alias="sourceCode", min_length=1)
    source_display: str = Field(alias="sourceDisplay", min_length=1)
    domains: tuple[str, ...] = ()
    contexts: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_collections(self) -> Self:
        if len(set(self.domains)) != len(self.domains):
            raise ValueError("translation domains must be unique")
        if len(set(self.contexts)) != len(self.contexts):
            raise ValueError("translation contexts must be unique")
        return self


class TranslationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    schema_version: int = Field(alias="schemaVersion", default=1)
    batch_id: str = Field(alias="batchId", min_length=1)
    inventory_hash: str = Field(alias="inventoryHash", pattern=r"^[0-9a-f]{64}$")
    prompt_version: str = Field(alias="promptVersion", min_length=1)
    glossary_hash: str = Field(alias="glossaryHash", pattern=r"^[0-9a-f]{64}$")
    glossary: dict[str, str]
    records: tuple[TranslationBatchRecord, ...] = Field(min_length=1)
    input_hash: str = Field(alias="inputHash", pattern=r"^[0-9a-f]{64}$")


def translation_batch_record_sort_key(
    record: TranslationBatchRecord,
) -> tuple[str, str, str, str, str]:
    return (
        record.source_system,
        record.domains[0] if record.domains else "",
        record.source_version or "",
        record.source_code,
        record.source_display,
    )


def make_translation_batches(
    records: Iterable[TranslationBatchRecord],
    *,
    inventory_hash: str,
    prompt_version: str,
    glossary: Mapping[str, str] | None = None,
    max_records: int = 40,
    max_source_characters: int = 12_000,
) -> tuple[TranslationBatch, ...]:
    """Group records by terminology/domain without exceeding either batch bound."""
    if max_records < 1 or max_source_characters < 1:
        raise ValueError("translation batch limits must be positive")
    if len(inventory_hash) != 64:
        raise ValueError("inventory hash must be SHA256")

    ordered = sorted(records, key=translation_batch_record_sort_key)
    identifiers = [record.translation_id for record in ordered]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("translation IDs must be unique before batching")

    normalized_glossary = dict(sorted((glossary or {}).items()))
    glossary_hash = hashlib.sha256(rfc8785.dumps(normalized_glossary)).hexdigest()
    chunks: list[list[TranslationBatchRecord]] = []
    current: list[TranslationBatchRecord] = []
    current_characters = 0
    current_group: tuple[str, str] | None = None
    for record in ordered:
        record_group = (record.source_system, record.domains[0] if record.domains else "")
        record_characters = len(record.source_display)
        exceeds_limit = current and (
            len(current) >= max_records
            or current_characters + record_characters > max_source_characters
            or record_group != current_group
        )
        if exceeds_limit:
            chunks.append(current)
            current = []
            current_characters = 0
        current.append(record)
        current_characters += record_characters
        current_group = record_group
    if current:
        chunks.append(current)

    batches: list[TranslationBatch] = []
    for index, chunk in enumerate(chunks, start=1):
        content: dict[str, Any] = {
            "schemaVersion": 1,
            "inventoryHash": inventory_hash,
            "promptVersion": prompt_version,
            "glossaryHash": glossary_hash,
            "glossary": normalized_glossary,
            "records": [record.model_dump(by_alias=True) for record in chunk],
        }
        input_hash = hashlib.sha256(rfc8785.dumps(content)).hexdigest()
        batches.append(
            TranslationBatch(
                batchId=f"batch-{index:04d}-{input_hash[:12]}",
                inventoryHash=inventory_hash,
                promptVersion=prompt_version,
                glossaryHash=glossary_hash,
                glossary=normalized_glossary,
                records=tuple(chunk),
                inputHash=input_hash,
            )
        )
    return tuple(batches)
