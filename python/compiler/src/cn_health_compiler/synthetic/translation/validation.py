"""Invariant and coverage validation for projected Synthea FHIR Bundles."""

from __future__ import annotations

import copy
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Protocol

from cn_health_compiler.synthetic.translation.catalog import (
    ReviewStatus,
    TranslationCatalog,
)
from cn_health_compiler.synthetic.translation.inventory import (
    FieldClassification,
    TranslationInventory,
)
from cn_health_compiler.synthetic.translation.projector import (
    _PATHS,
    _TRANSLATION_TAG_SYSTEM,
    _exclude_with_reference_closure,
    _nodes_at_path,
)

_CHINESE = re.compile(r"[\u3400-\u9fff]")


class TranslationReviewLookup(Protocol):
    """Optional review metadata lookup used only to classify coverage."""

    def review_status(
        self,
        system: str,
        version: str | None,
        code: str,
        source_display: str,
    ) -> str | None: ...


class ProjectionValidationError(ValueError):
    """Raised when a projection changes anything outside its contract."""


@dataclass(frozen=True, order=True)
class CoverageRow:
    dimension: str
    key: str
    translated: int
    gap: int


@dataclass(frozen=True, order=True)
class ReviewStatusCount:
    review_status: str
    count: int


@dataclass(frozen=True)
class ValidationReport:
    total: int
    translated: int
    gap: int
    coverage: tuple[CoverageRow, ...]
    review_statuses: tuple[ReviewStatusCount, ...]
    removed_resources: tuple[str, ...]


@dataclass(frozen=True)
class InventoryCoverageReport:
    total: int
    covered: int
    gap: int
    needs_review: int
    coverage: tuple[CoverageRow, ...]
    review_statuses: tuple[ReviewStatusCount, ...]
    missing_translation_ids: tuple[str, ...]


@dataclass(frozen=True)
class _ConceptResult:
    resource_type: str
    system: str
    translated: bool
    review_status: str | None


def validate_projection(
    source_bundle: dict[str, Any],
    projected_bundle: dict[str, Any],
    *,
    review_lookup: TranslationReviewLookup | None = None,
) -> ValidationReport:
    """Validate projection invariants and return deterministic concept coverage."""
    source = copy.deepcopy(source_bundle)
    projected = copy.deepcopy(projected_bundle)
    source_entries = source.get("entry")
    projected_entries = projected.get("entry")
    if not isinstance(source_entries, list) or not isinstance(projected_entries, list):
        raise ProjectionValidationError("source and projected Bundles must contain entry arrays")

    expected_entries, removed = _exclude_with_reference_closure(source_entries)
    if len(expected_entries) != len(projected_entries):
        raise ProjectionValidationError("projected Bundle does not contain the expected resources")

    concepts: list[_ConceptResult] = []
    for index, (source_entry, projected_entry) in enumerate(
        zip(expected_entries, projected_entries, strict=True)
    ):
        if not isinstance(source_entry, dict) or not isinstance(projected_entry, dict):
            if source_entry != projected_entry:
                raise ProjectionValidationError(f"entry[{index}] changed")
            continue
        if source_entry.get("fullUrl") != projected_entry.get("fullUrl"):
            raise ProjectionValidationError(f"entry[{index}].fullUrl changed")
        source_resource = source_entry.get("resource")
        projected_resource = projected_entry.get("resource")
        if not isinstance(source_resource, dict) or not isinstance(projected_resource, dict):
            if source_resource != projected_resource:
                raise ProjectionValidationError(f"entry[{index}].resource changed")
            continue
        resource_type = source_resource.get("resourceType")
        if (
            not isinstance(resource_type, str)
            or projected_resource.get("resourceType") != resource_type
        ):
            raise ProjectionValidationError(f"entry[{index}].resourceType changed")
        concepts.extend(
            _normalize_allowed_displays(
                source_resource, projected_resource, resource_type, review_lookup
            )
        )

    _remove_translation_tag(source)
    _remove_translation_tag(projected)
    source["entry"] = expected_entries
    projected["entry"] = projected_entries
    if source != projected:
        raise ProjectionValidationError(
            "projected Bundle changed a field outside the display allowlist"
        )
    return _coverage_report(concepts, removed)


def validate_inventory_coverage(
    inventory: TranslationInventory,
    catalog: TranslationCatalog,
    *,
    accepted_review_statuses: frozenset[ReviewStatus],
) -> InventoryCoverageReport:
    """Prove static translation coverage independently of generated patient paths."""
    if not accepted_review_statuses:
        raise ValueError("at least one accepted review status is required")
    relevant = tuple(
        record
        for record in inventory.records
        if record.classification is FieldClassification.DISPLAY_LOOKUP
    )
    missing: list[str] = []
    status_counts: Counter[str] = Counter()
    system_counts: dict[str, list[int]] = {}
    needs_review = 0
    for source in relevant:
        translated = catalog.lookup(*source.source_key)
        if translated is not None and translated.source_display != source.source_display:
            raise ProjectionValidationError(
                f"catalog source display differs from inventory: {source.translation_id}"
            )
        covered = translated is not None and translated.review_status in accepted_review_statuses
        counts = system_counts.setdefault(source.source_system, [0, 0])
        counts[0 if covered else 1] += 1
        if not covered:
            missing.append(source.translation_id)
            continue
        assert translated is not None
        status_counts[translated.review_status] += 1
        needs_review += translated.needs_review
    covered_count = len(relevant) - len(missing)
    return InventoryCoverageReport(
        total=len(relevant),
        covered=covered_count,
        gap=len(missing),
        needs_review=needs_review,
        coverage=tuple(
            CoverageRow("code-system", system, counts[0], counts[1])
            for system, counts in sorted(system_counts.items())
        ),
        review_statuses=tuple(
            ReviewStatusCount(status, count) for status, count in sorted(status_counts.items())
        ),
        missing_translation_ids=tuple(sorted(missing)),
    )


def _normalize_allowed_displays(
    source: dict[str, Any],
    projected: dict[str, Any],
    resource_type: str,
    review_lookup: TranslationReviewLookup | None,
) -> list[_ConceptResult]:
    results: list[_ConceptResult] = []
    for path in _PATHS.get(resource_type, ()):
        source_nodes = _nodes_at_path(source, path)
        projected_nodes = _nodes_at_path(projected, path)
        if [item[1] for item in source_nodes] != [item[1] for item in projected_nodes]:
            raise ProjectionValidationError(f"{resource_type}.{'.'.join(path)} structure changed")
        for (source_node, concrete_path), (projected_node, _) in zip(
            source_nodes, projected_nodes, strict=True
        ):
            results.extend(
                _normalize_node(
                    source_node,
                    projected_node,
                    resource_type,
                    concrete_path,
                    review_lookup,
                )
            )
    return results


def _normalize_node(
    source: dict[str, Any],
    projected: dict[str, Any],
    resource_type: str,
    path: str,
    review_lookup: TranslationReviewLookup | None,
) -> list[_ConceptResult]:
    source_codings = source.get("coding")
    projected_codings = projected.get("coding")
    if isinstance(source_codings, list):
        if not isinstance(projected_codings, list) or len(source_codings) != len(projected_codings):
            raise ProjectionValidationError(f"{resource_type}.{path}.coding changed")
        results: list[_ConceptResult] = []
        for index, (source_coding, projected_coding) in enumerate(
            zip(source_codings, projected_codings, strict=True)
        ):
            if not isinstance(source_coding, dict) or not isinstance(projected_coding, dict):
                if source_coding != projected_coding:
                    raise ProjectionValidationError(
                        f"{resource_type}.{path}.coding[{index}] changed"
                    )
                continue
            result = _normalize_coding(
                source_coding, projected_coding, resource_type, review_lookup
            )
            if result is not None:
                results.append(result)
        source.pop("text", None)
        projected.pop("text", None)
        return results
    result = _normalize_coding(source, projected, resource_type, review_lookup)
    return [result] if result is not None else []


def _normalize_coding(
    source: dict[str, Any],
    projected: dict[str, Any],
    resource_type: str,
    review_lookup: TranslationReviewLookup | None,
) -> _ConceptResult | None:
    system = source.get("system")
    version = source.get("version")
    code = source.get("code")
    source_display = source.get("display")
    projected_display = projected.get("display")
    if (
        not isinstance(system, str)
        or not isinstance(code, str)
        or not isinstance(source_display, str)
    ):
        return None
    if not isinstance(projected_display, str) or not projected_display:
        raise ProjectionValidationError(
            f"{resource_type} translation removed a required Coding.display"
        )
    normalized_version = version if isinstance(version, str) else None
    source_localized = _CHINESE.search(source_display) is not None
    translated = source_localized or (
        isinstance(projected_display, str) and projected_display != source_display
    )
    status: str | None
    if source_localized:
        status = "source-localized"
    elif translated and review_lookup is not None:
        status = review_lookup.review_status(system, normalized_version, code, source_display)
    else:
        status = None
    source.pop("display", None)
    projected.pop("display", None)
    return _ConceptResult(resource_type, system, translated, status)


def _remove_translation_tag(bundle: dict[str, Any]) -> None:
    meta = bundle.get("meta")
    if not isinstance(meta, dict):
        return
    tags = meta.get("tag")
    if not isinstance(tags, list):
        return
    filtered = [
        tag
        for tag in tags
        if not (isinstance(tag, dict) and tag.get("system") == _TRANSLATION_TAG_SYSTEM)
    ]
    if filtered:
        meta["tag"] = filtered
    else:
        meta.pop("tag", None)
    if not meta:
        bundle.pop("meta", None)


def _coverage_report(concepts: list[_ConceptResult], removed: set[str]) -> ValidationReport:
    counters: dict[tuple[str, str], list[int]] = {}
    for concept in concepts:
        for dimension, key in (
            ("code-system", concept.system),
            ("resource-type", concept.resource_type),
        ):
            counts = counters.setdefault((dimension, key), [0, 0])
            counts[0 if concept.translated else 1] += 1
    coverage = tuple(
        CoverageRow(dimension, key, counts[0], counts[1])
        for (dimension, key), counts in sorted(counters.items())
    )
    statuses = Counter(
        concept.review_status or "unknown" for concept in concepts if concept.translated
    )
    translated = sum(concept.translated for concept in concepts)
    return ValidationReport(
        total=len(concepts),
        translated=translated,
        gap=len(concepts) - translated,
        coverage=coverage,
        review_statuses=tuple(
            ReviewStatusCount(status, count) for status, count in sorted(statuses.items())
        ),
        removed_resources=tuple(sorted(removed)),
    )
