"""Build-time orchestration for Synthea translation inventory and drafts."""

import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from tempfile import NamedTemporaryFile

from cn_health_compiler.synthetic.translation.api import validate_translation_response
from cn_health_compiler.synthetic.translation.batches import (
    TranslationBatch,
    TranslationBatchRecord,
    make_translation_batches,
)
from cn_health_compiler.synthetic.translation.catalog import (
    ReviewStatus,
    TranslationCatalog,
    TranslationMethod,
    TranslationRecord,
)
from cn_health_compiler.synthetic.translation.inventory import (
    FieldClassification,
    TranslationInventory,
)


def inventory_batch_records(
    inventory: TranslationInventory,
    *,
    max_contexts: int = 4,
) -> tuple[TranslationBatchRecord, ...]:
    """Project inventory records to bounded, non-patient translation inputs."""
    if max_contexts < 0:
        raise ValueError("max_contexts must be non-negative")
    records: list[TranslationBatchRecord] = []
    for record in inventory.records:
        if record.classification is not FieldClassification.DISPLAY_LOOKUP:
            continue
        domains = tuple(sorted({context.resource_type or "general" for context in record.contexts}))
        contexts = tuple(
            sorted(
                {
                    ":".join(
                        part
                        for part in (context.resource_type, context.module, context.json_path)
                        if part
                    )
                    for context in record.contexts
                }
            )[:max_contexts]
        )
        records.append(
            TranslationBatchRecord(
                translationId=record.translation_id,
                sourceSystem=record.source_system,
                sourceVersion=record.source_version,
                sourceCode=record.source_code,
                sourceDisplay=record.source_display,
                domains=domains or ("general",),
                contexts=contexts,
            )
        )
    return tuple(records)


def batches_from_inventory(
    inventory: TranslationInventory,
    *,
    prompt_version: str,
    glossary: Mapping[str, str] | None = None,
    max_records: int = 40,
    max_source_characters: int = 12_000,
) -> tuple[TranslationBatch, ...]:
    return make_translation_batches(
        inventory_batch_records(inventory),
        inventory_hash=inventory.content_hash,
        prompt_version=prompt_version,
        glossary=glossary,
        max_records=max_records,
        max_source_characters=max_source_characters,
    )


def merge_draft_responses(
    batches: Iterable[TranslationBatch],
    raw_responses: Mapping[str, Mapping[str, object]],
    *,
    model_id: str,
    conflicts: frozenset[tuple[str, str | None, str]] = frozenset(),
) -> TranslationCatalog:
    """Validate exact batch responses and convert them to machine-draft records."""
    return merge_translation_responses(
        batches,
        raw_responses,
        model_id=model_id,
        method="machine",
        review_status="machine-draft",
        conflicts=conflicts,
    )


def merge_translation_responses(
    batches: Iterable[TranslationBatch],
    raw_responses: Mapping[str, Mapping[str, object]],
    *,
    model_id: str,
    method: TranslationMethod,
    review_status: ReviewStatus,
    conflicts: frozenset[tuple[str, str | None, str]] = frozenset(),
    prompt_version: str | None = None,
) -> TranslationCatalog:
    """Validate exact responses and project them to the requested review stage."""
    records: list[TranslationRecord] = []
    seen_batches: set[str] = set()
    for batch in batches:
        if batch.batch_id in seen_batches:
            raise ValueError(f"duplicate batch ID: {batch.batch_id}")
        seen_batches.add(batch.batch_id)
        raw_response = raw_responses.get(batch.batch_id)
        if raw_response is None:
            raise ValueError(f"missing translation response: {batch.batch_id}")
        response = validate_translation_response(batch, raw_response, model_id=model_id)
        translated = {record.translation_id: record for record in response.records}
        for source in batch.records:
            result = translated[source.translation_id]
            key = (source.source_system, source.source_version, source.source_code)
            conflict = key in conflicts
            notes = result.notes
            if conflict:
                notes = (
                    "Source code has conflicting English displays"
                    if notes is None
                    else f"{notes}; source code has conflicting English displays"
                )
            records.append(
                TranslationRecord(
                    translation_id=source.translation_id,
                    source_system=source.source_system,
                    source_version=source.source_version,
                    source_code=source.source_code,
                    source_display=source.source_display,
                    display_zh=result.display_zh,
                    domains=source.domains or ("general",),
                    method=method,
                    review_status=review_status,
                    needs_review=result.needs_review or conflict,
                    provenance_id=batch.batch_id,
                    prompt_version=prompt_version or batch.prompt_version,
                    model=model_id,
                    notes=notes,
                )
            )
    extra_responses = sorted(set(raw_responses) - seen_batches)
    if extra_responses:
        raise ValueError(f"unexpected translation responses: {extra_responses}")
    return TranslationCatalog(records)


def write_catalog_jsonl(path: Path, catalog: TranslationCatalog) -> tuple[str, int]:
    payload = b"".join(
        record.model_dump_json(by_alias=True).encode("utf-8") + b"\n" for record in catalog.records
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}-", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return catalog.sha256, len(payload)
