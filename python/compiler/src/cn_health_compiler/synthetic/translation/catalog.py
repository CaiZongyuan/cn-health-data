"""Strict, deterministic translation catalog contracts and merging."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import rfc8785
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

ReviewStatus = Literal[
    "pending", "machine-draft", "machine-checked", "human-reviewed", "approved", "rejected"
]
TranslationMethod = Literal[
    "machine", "machine-checked", "human-reviewed", "project-curated", "manual-override"
]
CatalogKey = tuple[str, str | None, str]
_SYSTEM_ALIASES = {
    "http://dicom.nema.org/medical/dicom/current/output/chtml/part16/sect_CID_29.html": "DICOM-DCM",
    "http://hl7.org/fhir/sid/cvx": "CVX",
    "http://loinc.org": "LOINC",
    "http://snomed.info/sct": "SNOMED-CT",
    "http://www.nlm.nih.gov/research/umls/rxnorm": "RxNorm",
}


def _camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part.capitalize() for part in tail)


class TranslationCatalogError(ValueError):
    """Raised when translation inputs cannot form an unambiguous catalog."""


def translation_id(system: str, version: str | None, code: str) -> str:
    """Return the stable identifier for a terminology key."""
    return hashlib.sha256(rfc8785.dumps([system, version, code])).hexdigest()


class TranslationRecord(BaseModel):
    """One Chinese display associated with an exact terminology key."""

    model_config = ConfigDict(
        alias_generator=_camel, populate_by_name=True, extra="forbid", frozen=True
    )

    schema_version: Literal[1] = 1
    translation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_system: str = Field(min_length=1)
    source_version: str | None
    source_code: str = Field(min_length=1)
    source_display: str = Field(min_length=1)
    language: Literal["zh-CN"] = "zh-CN"
    display_zh: str = Field(min_length=1, pattern=r"[\u3400-\u9fff]")
    domains: tuple[str, ...] = Field(min_length=1)
    method: TranslationMethod
    review_status: ReviewStatus
    needs_review: bool
    provenance_id: str = Field(min_length=1)
    prompt_version: str | None = None
    model: str | None = None
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_review_claims(self) -> TranslationRecord:
        if self.translation_id != translation_id(*self.key):
            raise ValueError("translationId does not match source key")
        if len(set(self.domains)) != len(self.domains) or any(not item for item in self.domains):
            raise ValueError("domains must contain unique non-empty values")
        if self.method == "machine" and self.review_status != "machine-draft":
            raise ValueError("machine output must have machine-draft review status")
        if self.review_status == "approved":
            if self.method not in ("manual-override", "project-curated"):
                raise ValueError("approved records require an approved source")
            if self.needs_review:
                raise ValueError("approved records cannot need review")
        return self

    @property
    def key(self) -> CatalogKey:
        return (self.source_system, self.source_version, self.source_code)


class TranslationRelease(BaseModel):
    """Immutable release provenance for a serialized catalog."""

    model_config = ConfigDict(
        alias_generator=_camel, populate_by_name=True, extra="forbid", frozen=True
    )

    schema_version: Literal[1] = 1
    release_id: str = Field(pattern=r"^[a-z0-9-]+@\d{4}-\d{2}-\d{2}\.r[1-9]\d*$")
    language: Literal["zh-CN"] = "zh-CN"
    synthea_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    profile_id: str = Field(min_length=1)
    profile_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    inventory_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    glossary_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_version: str | None = None
    builder_version: str = Field(min_length=1)
    record_count: int = Field(ge=0)
    experimental: bool = False


class GlossaryEntry(BaseModel):
    """A source phrase constraint shared across translation batches."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    domains: tuple[str, ...] = ()
    do_not_translate: bool = False


class TranslationCatalog:
    """Read-only exact-key index produced from validated records."""

    def __init__(self, records: Iterable[TranslationRecord]) -> None:
        index: dict[CatalogKey, TranslationRecord] = {}
        identifiers: set[str] = set()
        for record in records:
            if record.translation_id in identifiers:
                raise TranslationCatalogError(f"duplicate translationId {record.translation_id}")
            identifiers.add(record.translation_id)
            previous = index.get(record.key)
            if previous is not None:
                raise TranslationCatalogError(f"duplicate translation key {record.key!r}")
            index[record.key] = record
        self._index = index

    @property
    def records(self) -> tuple[TranslationRecord, ...]:
        return tuple(self._index[key] for key in sorted(self._index, key=_sortable_key))

    def lookup(self, system: str, version: str | None, code: str) -> TranslationRecord | None:
        return self._index.get((system, version, code))

    @property
    def sha256(self) -> str:
        return catalog_sha256(self.records)


class CatalogDisplayLookup:
    """Expose one catalog through the projector and coverage lookup protocols."""

    def __init__(
        self,
        catalog: TranslationCatalog,
        *,
        accepted_review_statuses: frozenset[ReviewStatus] = frozenset({"approved"}),
    ) -> None:
        if not accepted_review_statuses:
            raise ValueError("at least one accepted review status is required")
        self._catalog = catalog
        self._accepted = accepted_review_statuses

    def _record(self, system: str, version: str | None, code: str) -> TranslationRecord | None:
        exact = self._catalog.lookup(system, version, code)
        if exact is not None:
            return exact
        alias = _SYSTEM_ALIASES.get(system)
        return self._catalog.lookup(alias, version, code) if alias is not None else None

    def _accepted_record(
        self, system: str, version: str | None, code: str
    ) -> TranslationRecord | None:
        record = self._record(system, version, code)
        return record if record is not None and record.review_status in self._accepted else None

    def lookup(
        self,
        system: str,
        version: str | None,
        code: str,
        source_display: str,
    ) -> str | None:
        del source_display
        record = self._accepted_record(system, version, code)
        return record.display_zh if record is not None else None

    def review_status(
        self,
        system: str,
        version: str | None,
        code: str,
        source_display: str,
    ) -> str | None:
        del source_display
        record = self._accepted_record(system, version, code)
        return record.review_status if record is not None else None


def load_catalog(path: Path) -> TranslationCatalog:
    """Load a UTF-8 JSONL catalog, rejecting blank and malformed records."""
    records: list[TranslationRecord] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise TranslationCatalogError(f"cannot read catalog {path}") from error
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise TranslationCatalogError(f"catalog line {line_number} is blank")
        try:
            records.append(TranslationRecord.model_validate_json(line))
        except (ValueError, json.JSONDecodeError) as error:
            raise TranslationCatalogError(f"invalid catalog line {line_number}") from error
    return TranslationCatalog(records)


def load_glossary(path: Path) -> tuple[GlossaryEntry, ...]:
    """Load a strict YAML glossary and reject contradictory source phrases."""
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise TranslationCatalogError(f"cannot read glossary {path}") from error
    if not isinstance(payload, Mapping) or set(payload) != {"schemaVersion", "entries"}:
        raise TranslationCatalogError("glossary must contain only schemaVersion and entries")
    if payload["schemaVersion"] != 1 or not isinstance(payload["entries"], list):
        raise TranslationCatalogError("invalid glossary contract")
    entries = tuple(GlossaryEntry.model_validate(item) for item in payload["entries"])
    seen: dict[str, GlossaryEntry] = {}
    for entry in entries:
        if entry.source in seen:
            raise TranslationCatalogError(f"duplicate glossary source {entry.source!r}")
        seen[entry.source] = entry
    return entries


def merge_catalogs(*record_groups: Iterable[TranslationRecord]) -> TranslationCatalog:
    """Merge sources by explicit precedence and fail on equal-rank conflicts."""
    chosen: dict[CatalogKey, TranslationRecord] = {}
    for record in (item for group in record_groups for item in group):
        previous = chosen.get(record.key)
        if previous is None:
            chosen[record.key] = record
            continue
        if previous.source_display != record.source_display:
            raise TranslationCatalogError(f"conflicting source display for key {record.key!r}")
        old_rank, new_rank = _precedence(previous), _precedence(record)
        if old_rank == new_rank:
            if previous != record:
                raise TranslationCatalogError(f"conflicting translation key {record.key!r}")
        elif new_rank > old_rank:
            chosen[record.key] = record
    return TranslationCatalog(chosen.values())


def catalog_sha256(records: Iterable[TranslationRecord]) -> str:
    payload = [
        record.model_dump(mode="json", by_alias=True)
        for record in sorted(records, key=lambda item: _sortable_key(item.key))
    ]
    return hashlib.sha256(rfc8785.dumps(payload)).hexdigest()


def glossary_sha256(entries: Iterable[GlossaryEntry]) -> str:
    payload = [
        entry.model_dump(mode="json") for entry in sorted(entries, key=lambda item: item.source)
    ]
    return hashlib.sha256(rfc8785.dumps(payload)).hexdigest()


def project_laboratory_record(
    record: Any,
    *,
    provenance_id: str,
    source_display: str,
    synthea_source_system: str = "LOINC",
    synthea_source_version: str | None = None,
) -> TranslationRecord:
    """Project a laboratory-cn concept without importing its storage adapter."""
    key = (synthea_source_system, synthea_source_version, str(record.code))
    return TranslationRecord(
        translation_id=translation_id(*key),
        source_system=key[0],
        source_version=key[1],
        source_code=key[2],
        source_display=source_display,
        display_zh=str(record.display_zh),
        domains=("laboratory",),
        method="project-curated",
        review_status="approved",
        needs_review=False,
        provenance_id=provenance_id,
        notes=f"Chinese display curated against LOINC {record.terminology_version}",
    )


def _precedence(record: TranslationRecord) -> int:
    if record.method == "manual-override" and record.review_status == "approved":
        return 60
    if record.method == "project-curated" and record.review_status == "approved":
        return 50
    return {
        "human-reviewed": 40,
        "machine-checked": 30,
        "machine-draft": 20,
        "pending": 10,
        "rejected": 0,
    }[record.review_status]


def _sortable_key(key: CatalogKey) -> tuple[str, str, str]:
    return (key[0], key[1] or "", key[2])
