"""Project reviewed Chinese displays onto an immutable FHIR R4 Bundle copy."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any, Protocol


class TranslationLookup(Protocol):
    """Read-only lookup implemented by a translation catalog or a test fixture."""

    def lookup(
        self,
        system: str,
        version: str | None,
        code: str,
        source_display: str,
    ) -> str | None: ...


@dataclass(frozen=True, order=True)
class TranslationGap:
    resource_type: str
    resource_id: str
    path: str
    system: str
    version: str | None
    code: str
    source_display: str


@dataclass(frozen=True)
class ProjectionResult:
    bundle: dict[str, Any]
    gaps: tuple[TranslationGap, ...]
    removed_resources: tuple[str, ...]


_TRANSLATION_TAG_SYSTEM = "urn:cn-health-data:synthea-translation"
_EXCLUDED_RESOURCE_TYPES = frozenset({"Claim", "ExplanationOfBenefit"})
_CHINESE = re.compile(r"[\u3400-\u9fff]")

# Paths are relative to a resource. ``*`` consumes one list element. A node may
# be either a CodeableConcept or a Coding; no other strings are traversed.
_PATHS: dict[str, tuple[tuple[str, ...], ...]] = {
    "AllergyIntolerance": (
        ("clinicalStatus",),
        ("verificationStatus",),
        ("code",),
        ("reaction", "*", "substance"),
        ("reaction", "*", "manifestation", "*"),
    ),
    "CarePlan": (
        ("category", "*"),
        ("activity", "*", "detail", "code"),
        ("activity", "*", "detail", "reasonCode", "*"),
    ),
    "CareTeam": (
        ("category", "*"),
        ("participant", "*", "role", "*"),
        ("reasonCode", "*"),
    ),
    "Condition": (
        ("clinicalStatus",),
        ("verificationStatus",),
        ("category", "*"),
        ("code",),
        ("bodySite", "*"),
    ),
    "DetectedIssue": (("code",), ("mitigation", "*", "action")),
    "Device": (("type",),),
    "DiagnosticReport": (("category", "*"), ("code",)),
    "DocumentReference": (
        ("type",),
        ("category", "*"),
        ("context", "event", "*"),
        ("context", "facilityType"),
        ("context", "practiceSetting"),
    ),
    "Encounter": (
        ("class",),
        ("type", "*"),
        ("reasonCode", "*"),
        ("diagnosis", "*", "use"),
        ("participant", "*", "type", "*"),
        ("hospitalization", "admitSource"),
        ("hospitalization", "dischargeDisposition"),
        ("hospitalization", "dietPreference", "*"),
        ("hospitalization", "specialArrangement", "*"),
        ("hospitalization", "specialCourtesy", "*"),
    ),
    "Goal": (
        ("category", "*"),
        ("description",),
        ("target", "*", "measure"),
    ),
    "ImagingStudy": (
        ("modality", "*"),
        ("series", "*", "modality"),
        ("series", "*", "bodySite"),
    ),
    "Immunization": (
        ("vaccineCode",),
        ("site",),
        ("route",),
        ("reasonCode", "*"),
        ("programEligibility", "*"),
        ("fundingSource",),
    ),
    "Media": (
        ("type",),
        ("modality",),
        ("view",),
        ("bodySite",),
        ("reasonCode", "*"),
    ),
    "Medication": (
        ("code",),
        ("form",),
        ("ingredient", "*", "itemCodeableConcept"),
    ),
    "MedicationAdministration": (
        ("category",),
        ("medicationCodeableConcept",),
        ("reasonCode", "*"),
        ("dosage", "site"),
        ("dosage", "route"),
        ("dosage", "method"),
    ),
    "MedicationRequest": (
        ("category", "*"),
        ("medicationCodeableConcept",),
        ("reasonCode", "*"),
        ("dosageInstruction", "*", "additionalInstruction", "*"),
        ("dosageInstruction", "*", "site"),
        ("dosageInstruction", "*", "route"),
        ("dosageInstruction", "*", "method"),
        ("dosageInstruction", "*", "doseAndRate", "*", "type"),
    ),
    "MedicationStatement": (
        ("category",),
        ("medicationCodeableConcept",),
        ("reasonCode", "*"),
        ("dosage", "*", "additionalInstruction", "*"),
        ("dosage", "*", "site"),
        ("dosage", "*", "route"),
        ("dosage", "*", "method"),
    ),
    "Observation": (
        ("category", "*"),
        ("code",),
        ("interpretation", "*"),
        ("bodySite",),
        ("method",),
        ("dataAbsentReason",),
        ("valueCodeableConcept",),
        ("component", "*", "code"),
        ("component", "*", "interpretation", "*"),
        ("component", "*", "valueCodeableConcept"),
    ),
    "Organization": (("identifier", "*", "type"), ("type", "*")),
    "Patient": (
        ("identifier", "*", "type"),
        ("maritalStatus",),
        ("communication", "*", "language"),
    ),
    "Practitioner": (
        ("identifier", "*", "type"),
        ("qualification", "*", "code"),
        ("communication", "*"),
    ),
    "PractitionerRole": (("code", "*"), ("specialty", "*")),
    "Procedure": (
        ("category",),
        ("code",),
        ("reasonCode", "*"),
        ("bodySite", "*"),
        ("outcome",),
        ("complication", "*"),
        ("followUp", "*"),
        ("focalDevice", "*", "action"),
    ),
    "RiskAssessment": (("method",), ("prediction", "*", "qualitativeRisk")),
    "ServiceRequest": (
        ("category", "*"),
        ("code",),
        ("orderDetail", "*"),
        ("reasonCode", "*"),
        ("bodySite", "*"),
    ),
    "Location": (("type", "*"), ("physicalType",)),
    "RelatedPerson": (("relationship", "*"), ("communication", "*", "language")),
    "Specimen": (
        ("type",),
        ("collection", "method"),
        ("collection", "bodySite"),
        ("processing", "*", "procedure"),
        ("container", "*", "type"),
    ),
    "SupplyDelivery": (("type",), ("suppliedItem", "itemCodeableConcept")),
}


def project_bundle(
    source_bundle: dict[str, Any],
    lookup: TranslationLookup,
    *,
    release_id: str,
    content_hash: str,
) -> ProjectionResult:
    """Return a localized deep copy without changing clinical machine values."""
    bundle = copy.deepcopy(source_bundle)
    entries = bundle.get("entry")
    if not isinstance(entries, list):
        entries = []

    kept, removed = _exclude_with_reference_closure(entries)
    bundle["entry"] = kept
    gaps: list[TranslationGap] = []
    for entry in kept:
        resource = entry.get("resource")
        if not isinstance(resource, dict):
            continue
        resource_type = resource.get("resourceType")
        if not isinstance(resource_type, str):
            continue
        raw_resource_id = resource.get("id")
        resource_id = raw_resource_id if isinstance(raw_resource_id, str) else ""
        for path in _PATHS.get(resource_type, ()):
            for node, concrete_path in _nodes_at_path(resource, path):
                _translate_node(node, lookup, gaps, resource_type, resource_id, concrete_path)

    meta = bundle.setdefault("meta", {})
    if not isinstance(meta, dict):
        meta = {}
        bundle["meta"] = meta
    existing_tags = meta.get("tag")
    tags = (
        [
            tag
            for tag in existing_tags
            if isinstance(tag, dict) and tag.get("system") != _TRANSLATION_TAG_SYSTEM
        ]
        if isinstance(existing_tags, list)
        else []
    )
    tags.append({"system": _TRANSLATION_TAG_SYSTEM, "code": release_id, "display": content_hash})
    meta["tag"] = tags
    return ProjectionResult(
        bundle=bundle,
        gaps=tuple(sorted(set(gaps))),
        removed_resources=tuple(sorted(removed)),
    )


def _nodes_at_path(
    value: Any, path: tuple[str, ...], prefix: str = ""
) -> list[tuple[dict[str, Any], str]]:
    if not path:
        return [(value, prefix)] if isinstance(value, dict) else []
    part, remaining = path[0], path[1:]
    if part == "*":
        if not isinstance(value, list):
            return []
        result: list[tuple[dict[str, Any], str]] = []
        for index, item in enumerate(value):
            result.extend(_nodes_at_path(item, remaining, f"{prefix}[{index}]"))
        return result
    if not isinstance(value, dict) or part not in value:
        return []
    separator = "." if prefix else ""
    return _nodes_at_path(value[part], remaining, f"{prefix}{separator}{part}")


def _translate_node(
    node: dict[str, Any],
    lookup: TranslationLookup,
    gaps: list[TranslationGap],
    resource_type: str,
    resource_id: str,
    path: str,
) -> None:
    codings = node.get("coding")
    if isinstance(codings, list):
        translated: list[str] = []
        for index, coding in enumerate(codings):
            if isinstance(coding, dict):
                display = _translate_coding(
                    coding,
                    lookup,
                    gaps,
                    resource_type,
                    resource_id,
                    f"{path}.coding[{index}]",
                )
                if display is not None:
                    translated.append(display)
        if translated:
            node["text"] = translated[0]
        return
    _translate_coding(node, lookup, gaps, resource_type, resource_id, path)


def _translate_coding(
    coding: dict[str, Any],
    lookup: TranslationLookup,
    gaps: list[TranslationGap],
    resource_type: str,
    resource_id: str,
    path: str,
) -> str | None:
    system, code, source_display = (coding.get("system"), coding.get("code"), coding.get("display"))
    version = coding.get("version")
    if (
        not isinstance(system, str)
        or not system
        or not isinstance(code, str)
        or not code
        or not isinstance(source_display, str)
        or not source_display
    ):
        return None
    if not isinstance(version, str):
        version = None
    if _CHINESE.search(source_display) is not None:
        return source_display
    display_zh = lookup.lookup(system, version, code, source_display)
    if display_zh is None:
        gaps.append(
            TranslationGap(resource_type, resource_id, path, system, version, code, source_display)
        )
        return None
    coding["display"] = display_zh
    return display_zh


def _exclude_with_reference_closure(
    entries: list[Any],
) -> tuple[list[Any], set[str]]:
    removed_indexes = {
        index
        for index, entry in enumerate(entries)
        if _resource_type(entry) in _EXCLUDED_RESOURCE_TYPES
    }
    while True:
        removed_aliases = (
            set().union(*(_entry_aliases(entries[index]) for index in removed_indexes))
            if removed_indexes
            else set()
        )
        newly_removed = {
            index
            for index, entry in enumerate(entries)
            if index not in removed_indexes and _references(entry, removed_aliases)
        }
        if not newly_removed:
            break
        removed_indexes.update(newly_removed)
    removed = {_entry_label(entries[index], index) for index in removed_indexes}
    return (
        [entry for index, entry in enumerate(entries) if index not in removed_indexes],
        removed,
    )


def _resource_type(entry: Any) -> str | None:
    if not isinstance(entry, dict) or not isinstance(entry.get("resource"), dict):
        return None
    value = entry["resource"].get("resourceType")
    return value if isinstance(value, str) else None


def _entry_aliases(entry: Any) -> set[str]:
    if not isinstance(entry, dict):
        return set()
    aliases = {entry["fullUrl"]} if isinstance(entry.get("fullUrl"), str) else set()
    resource = entry.get("resource")
    if isinstance(resource, dict):
        resource_type, resource_id = resource.get("resourceType"), resource.get("id")
        if isinstance(resource_type, str) and isinstance(resource_id, str):
            aliases.add(f"{resource_type}/{resource_id}")
    return aliases


def _references(value: Any, removed_aliases: set[str]) -> bool:
    if isinstance(value, dict):
        reference = value.get("reference")
        if isinstance(reference, str) and reference in removed_aliases:
            return True
        return any(_references(child, removed_aliases) for child in value.values())
    if isinstance(value, list):
        return any(_references(child, removed_aliases) for child in value)
    return False


def _entry_label(entry: Any, index: int) -> str:
    aliases = sorted(_entry_aliases(entry))
    return aliases[0] if aliases else f"entry[{index}]"
