"""Deterministic terminology inventory for Synthea modules and FHIR output."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import rfc8785

from cn_health_compiler.synthetic.translation.catalog import translation_id


class FieldClassification(StrEnum):
    """How a discovered field is handled by the localization pipeline."""

    KEEP = "KEEP"
    DISPLAY_LOOKUP = "DISPLAY_LOOKUP"
    UI_LABEL = "UI_LABEL"
    TEMPLATE_LOOKUP = "TEMPLATE_LOOKUP"
    IDENTITY_LOCALIZER = "IDENTITY_LOCALIZER"
    EXCLUDE = "EXCLUDE"
    DEFER = "DEFER"


_EXCLUDED_RESOURCES = frozenset({"Claim", "ExplanationOfBenefit"})
_CHINESE = re.compile(r"[\u3400-\u9fff]")
_KNOWN_SYSTEMS = frozenset(
    {
        "CVX",
        "DICOM-DCM",
        "DICOM-SOP",
        "LOINC",
        "NUBC",
        "NullFlavor",
        "RxNorm",
        "SNOMED-CT",
        "http://dicom.nema.org/resources/ontology/DCM",
        "http://hl7.org/fhir/sid/cvx",
        "http://loinc.org",
        "http://snomed.info/sct",
        "http://www.nlm.nih.gov/research/umls/rxnorm",
    }
)
_SYSTEM_ALIASES = {
    "http://hl7.org/fhir/sid/cvx": "CVX",
    "http://loinc.org": "LOINC",
    "http://snomed.info/sct": "SNOMED-CT",
    "http://www.nlm.nih.gov/research/umls/rxnorm": "RxNorm",
}
_MODULE_RESOURCE_TYPES = {
    "AllergyOnset": "AllergyIntolerance",
    "CarePlanStart": "CarePlan",
    "ConditionOnset": "Condition",
    "Device": "Device",
    "DiagnosticReport": "DiagnosticReport",
    "Encounter": "Encounter",
    "EncounterEnd": "Encounter",
    "EncounterStart": "Encounter",
    "ImagingStudy": "ImagingStudy",
    "Immunization": "Immunization",
    "MedicationOrder": "MedicationRequest",
    "Observation": "Observation",
    "Procedure": "Procedure",
    "SupplyList": "SupplyDelivery",
}


@dataclass(frozen=True, slots=True, order=True)
class SourceContext:
    source_kind: str
    source_name: str
    json_path: str
    module: str | None = None
    resource_type: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "sourceKind": self.source_kind,
            "sourceName": self.source_name,
            "jsonPath": self.json_path,
            "module": self.module,
            "resourceType": self.resource_type,
        }


@dataclass(frozen=True, slots=True)
class InventoryRecord:
    source_system: str
    source_version: str | None
    source_code: str
    source_display: str
    classification: FieldClassification
    occurrence_count: int
    contexts: tuple[SourceContext, ...]

    @property
    def source_key(self) -> tuple[str, str | None, str]:
        return (self.source_system, self.source_version, self.source_code)

    @property
    def translation_id(self) -> str:
        return translation_id(self.source_system, self.source_version, self.source_code)

    def as_dict(self) -> dict[str, object]:
        return {
            "translationId": self.translation_id,
            "sourceSystem": self.source_system,
            "sourceVersion": self.source_version,
            "sourceCode": self.source_code,
            "sourceDisplay": self.source_display,
            "classification": self.classification.value,
            "occurrenceCount": self.occurrence_count,
            "contexts": [context.as_dict() for context in self.contexts],
        }


@dataclass(frozen=True, slots=True)
class InventoryConflict:
    source_system: str
    source_version: str | None
    source_code: str
    source_displays: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "sourceSystem": self.source_system,
            "sourceVersion": self.source_version,
            "sourceCode": self.source_code,
            "sourceDisplays": list(self.source_displays),
        }


@dataclass(frozen=True, slots=True)
class TranslationInventory:
    records: tuple[InventoryRecord, ...]
    conflicts: tuple[InventoryConflict, ...]
    unknown_code_systems: tuple[str, ...]
    module_count: int
    occurrence_count: int

    def content_dict(self) -> dict[str, object]:
        """Return the canonical payload covered by ``content_hash``."""
        return {
            "schemaVersion": 1,
            "moduleCount": self.module_count,
            "occurrenceCount": self.occurrence_count,
            "records": [record.as_dict() for record in self.records],
            "conflicts": [conflict.as_dict() for conflict in self.conflicts],
            "unknownCodeSystems": list(self.unknown_code_systems),
        }

    def content_bytes(self) -> bytes:
        return rfc8785.dumps(cast(Any, self.content_dict()))

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content_bytes()).hexdigest()

    def as_dict(self) -> dict[str, object]:
        return {**self.content_dict(), "contentHash": self.content_hash}

    def to_json_bytes(self) -> bytes:
        """Serialize the complete inventory deterministically."""
        return rfc8785.dumps(cast(Any, self.as_dict())) + b"\n"


@dataclass(frozen=True, slots=True)
class _Occurrence:
    system: str
    version: str | None
    code: str
    display: str
    classification: FieldClassification
    context: SourceContext


def classify_path(
    *, resource_type: str | None, json_path: str, source_kind: str
) -> FieldClassification:
    """Classify a discovered coded display using its explicit source path."""
    del json_path, source_kind
    if resource_type in _EXCLUDED_RESOURCES:
        return FieldClassification.EXCLUDE
    return FieldClassification.DISPLAY_LOOKUP


def _pointer(parts: Sequence[str]) -> str:
    return "/" + "/".join(part.replace("~", "~0").replace("/", "~1") for part in parts)


def _text(value: object) -> str | None:
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        result = str(value).strip()
        return result or None
    return None


def _coding_occurrence(value: Mapping[str, Any], *, context: SourceContext) -> _Occurrence | None:
    system = _text(value.get("system"))
    code = _text(value.get("code"))
    display = _text(value.get("display"))
    if system is None or code is None or display is None:
        return None
    version = _text(value.get("version"))
    classification = classify_path(
        resource_type=context.resource_type,
        json_path=context.json_path,
        source_kind=context.source_kind,
    )
    if _CHINESE.search(display) is not None or (
        context.source_kind == "fhir" and context.resource_type is None
    ):
        classification = FieldClassification.KEEP
    return _Occurrence(
        system=_SYSTEM_ALIASES.get(system, system),
        version=version,
        code=code,
        display=display,
        classification=classification,
        context=context,
    )


def _module_resource_type(ancestors: Sequence[Mapping[str, Any]]) -> str | None:
    for ancestor in reversed(ancestors):
        state_type = _text(ancestor.get("type"))
        if state_type is not None and state_type in _MODULE_RESOURCE_TYPES:
            return _MODULE_RESOURCE_TYPES[state_type]
    return None


def _walk_module(
    value: object,
    *,
    parts: tuple[str, ...],
    ancestors: tuple[Mapping[str, Any], ...],
    module: str,
) -> list[_Occurrence]:
    occurrences: list[_Occurrence] = []
    if isinstance(value, dict):
        context = SourceContext(
            source_kind="module",
            source_name=module,
            json_path=_pointer(parts),
            module=module,
            resource_type=_module_resource_type(ancestors),
        )
        occurrence = _coding_occurrence(value, context=context)
        if occurrence is not None:
            occurrences.append(occurrence)
        next_ancestors = (*ancestors, value)
        for key in sorted(value):
            occurrences.extend(
                _walk_module(
                    value[key], parts=(*parts, key), ancestors=next_ancestors, module=module
                )
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            occurrences.extend(
                _walk_module(
                    child,
                    parts=(*parts, str(index)),
                    ancestors=ancestors,
                    module=module,
                )
            )
    return occurrences


def _walk_fhir(
    value: object,
    *,
    parts: tuple[str, ...],
    source_name: str,
    resource_type: str | None,
) -> list[_Occurrence]:
    occurrences: list[_Occurrence] = []
    if isinstance(value, dict):
        current_type = _text(value.get("resourceType")) or resource_type
        context = SourceContext(
            source_kind="fhir",
            source_name=source_name,
            json_path=_pointer(parts),
            resource_type=current_type if current_type != "Bundle" else None,
        )
        occurrence = _coding_occurrence(value, context=context)
        if occurrence is not None:
            occurrences.append(occurrence)
        for key in sorted(value):
            occurrences.extend(
                _walk_fhir(
                    value[key],
                    parts=(*parts, key),
                    source_name=source_name,
                    resource_type=current_type,
                )
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            occurrences.extend(
                _walk_fhir(
                    child,
                    parts=(*parts, str(index)),
                    source_name=source_name,
                    resource_type=resource_type,
                )
            )
    return occurrences


def _aggregate(occurrences: Iterable[_Occurrence], *, module_count: int) -> TranslationInventory:
    by_key: dict[tuple[str, str | None, str], list[_Occurrence]] = {}
    all_occurrences = list(occurrences)
    for occurrence in all_occurrences:
        by_key.setdefault((occurrence.system, occurrence.version, occurrence.code), []).append(
            occurrence
        )
    records: list[InventoryRecord] = []
    conflicts: list[InventoryConflict] = []
    for key in sorted(by_key, key=lambda item: (item[0], item[1] or "", item[2])):
        grouped = by_key[key]
        displays = tuple(sorted({item.display for item in grouped}))
        classifications = {item.classification for item in grouped}
        if FieldClassification.DISPLAY_LOOKUP in classifications:
            classification = FieldClassification.DISPLAY_LOOKUP
        elif FieldClassification.KEEP in classifications:
            classification = FieldClassification.KEEP
        else:
            classification = sorted(classifications, key=lambda item: item.value)[0]
        records.append(
            InventoryRecord(
                source_system=key[0],
                source_version=key[1],
                source_code=key[2],
                source_display=displays[0],
                classification=classification,
                occurrence_count=len(grouped),
                contexts=tuple(sorted({item.context for item in grouped})),
            )
        )
        if len(displays) > 1:
            conflicts.append(InventoryConflict(key[0], key[1], key[2], displays))
    unknown = tuple(
        sorted({item.system for item in all_occurrences if item.system not in _KNOWN_SYSTEMS})
    )
    return TranslationInventory(
        records=tuple(records),
        conflicts=tuple(conflicts),
        unknown_code_systems=unknown,
        module_count=module_count,
        occurrence_count=len(all_occurrences),
    )


def scan_synthea_modules(module_dir: Path) -> TranslationInventory:
    """Parse every module JSON below ``module_dir`` and build a stable inventory."""
    occurrences, module_count = _scan_module_occurrences(module_dir)
    return _aggregate(occurrences, module_count=module_count)


def _scan_module_occurrences(module_dir: Path) -> tuple[list[_Occurrence], int]:
    paths = sorted(
        module_dir.rglob("*.json"), key=lambda path: path.relative_to(module_dir).as_posix()
    )
    occurrences: list[_Occurrence] = []
    for path in paths:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Synthea module must be a JSON object: {path}")
        module = path.relative_to(module_dir).as_posix()
        occurrences.extend(_walk_module(payload, parts=(), ancestors=(), module=module))
    return occurrences, len(paths)


def scan_fhir_bundle(
    bundle: Mapping[str, Any], *, source_name: str = "bundle"
) -> TranslationInventory:
    """Collect Coding occurrences from one parsed FHIR Bundle."""
    if bundle.get("resourceType") != "Bundle":
        raise ValueError("FHIR inventory input must have resourceType Bundle")
    return _aggregate(
        _walk_fhir(bundle, parts=(), source_name=source_name, resource_type=None), module_count=0
    )


def build_translation_inventory(
    *, module_dir: Path | None = None, fhir_bundle_paths: Iterable[Path] = ()
) -> TranslationInventory:
    """Build one inventory from module files and parsed FHIR Bundle files."""
    occurrences: list[_Occurrence] = []
    module_count = 0
    if module_dir is not None:
        module_occurrences, module_count = _scan_module_occurrences(module_dir)
        occurrences.extend(module_occurrences)
    for path in sorted(fhir_bundle_paths, key=lambda item: item.as_posix()):
        payload: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"FHIR Bundle must be a JSON object: {path}")
        occurrences.extend(
            _walk_fhir(payload, parts=(), source_name=path.as_posix(), resource_type=None)
        )
    return _aggregate(occurrences, module_count=module_count)
