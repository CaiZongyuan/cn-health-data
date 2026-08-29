"""Deterministically localize Synthea FHIR R4 identity resources for China."""

import copy
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import rfc8785
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cn_health_compiler.core.source import hash_file
from cn_health_compiler.synthetic.identity import (
    DatasetReleaseReference,
    SyntheticIdentity,
    generate_synthetic_identity,
    load_dataset_release_reference,
)

_CHINESE = re.compile(r"[\u3400-\u9fff]")


class SyntheaLocalizationError(ValueError):
    """Raised when a profile or source Bundle violates the localization contract."""


class _ProfileFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(alias="sizeBytes", ge=0)


class _ProfileDependency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(alias="datasetId")
    release_id: str = Field(alias="releaseId")
    canonical_sha256: str = Field(alias="canonicalSha256", pattern=r"^[0-9a-f]{64}$")
    sqlite_sha256: str = Field(alias="sqliteSha256", pattern=r"^[0-9a-f]{64}$")


class _ProfileCompiler(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    adapter: str
    adapter_version: int = Field(alias="adapterVersion", ge=1)
    git_commit: str = Field(alias="gitCommit", pattern=r"^[0-9a-f]{40}$")


class _ProfileManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(alias="schemaVersion")
    profile_id: str = Field(alias="profileId")
    storage_key: str = Field(alias="storageKey")
    created_at: str = Field(alias="createdAt")
    supported_synthea_commit: str = Field(alias="supportedSyntheaCommit", pattern=r"^[0-9a-f]{40}$")
    dependencies: list[_ProfileDependency]
    projection_policy: dict[str, Any] = Field(alias="projectionPolicy")
    compiler: _ProfileCompiler
    files: list[_ProfileFile]
    content_hash: str = Field(alias="contentHash", pattern=r"^[0-9a-f]{64}$")


class _ResourceIdentity(BaseModel):
    model_config = ConfigDict(extra="allow")

    resource_type: str = Field(alias="resourceType")
    id: str = Field(min_length=1)


class _BundleEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    resource: _ResourceIdentity


class _BundleShape(BaseModel):
    model_config = ConfigDict(extra="allow")

    resource_type: str = Field(alias="resourceType", pattern="^Bundle$")
    type: str = Field(pattern="^collection$")
    entry: list[_BundleEntry] = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class LocalizedSyntheaBundle:
    bundle: dict[str, Any]
    profile_id: str
    profile_content_hash: str


def _safe_profile_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise SyntheaLocalizationError(f"Profile contains unsafe file path: {value}")
    return path


def _load_profile(profile_dir: Path) -> _ProfileManifest:
    profile_dir = profile_dir.resolve(strict=True)
    try:
        manifest = _ProfileManifest.model_validate_json(
            (profile_dir / "manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise SyntheaLocalizationError("Synthea profile Manifest is invalid") from error
    if manifest.schema_version != 1:
        raise SyntheaLocalizationError("Synthea profile schema is unsupported")
    for entry in manifest.files:
        relative_path = _safe_profile_path(entry.path)
        try:
            sha256, size_bytes = hash_file(profile_dir / relative_path)
        except OSError as error:
            raise SyntheaLocalizationError(f"Profile file is unreadable: {entry.path}") from error
        if (sha256, size_bytes) != (entry.sha256, entry.size_bytes):
            raise SyntheaLocalizationError(f"Profile file hash or size mismatch: {entry.path}")
    content_payload: dict[str, Any] = {
        "supportedSyntheaCommit": manifest.supported_synthea_commit,
        "dependencies": [
            dependency.model_dump(by_alias=True) for dependency in manifest.dependencies
        ],
        "projectionPolicy": manifest.projection_policy,
        "compiler": manifest.compiler.model_dump(by_alias=True),
        "files": [entry.model_dump(by_alias=True) for entry in manifest.files],
    }
    if hashlib.sha256(rfc8785.dumps(content_payload)).hexdigest() != manifest.content_hash:
        raise SyntheaLocalizationError("Synthea profile content hash does not match Manifest")
    return manifest


def _release_dependencies(
    manifest: _ProfileManifest,
    references: dict[str, DatasetReleaseReference],
) -> None:
    dependencies = {dependency.dataset_id: dependency for dependency in manifest.dependencies}
    if set(dependencies) != set(references) or len(dependencies) != len(manifest.dependencies):
        raise SyntheaLocalizationError("Synthea profile dependency set is invalid")
    for dataset_id, reference in references.items():
        dependency = dependencies[dataset_id]
        sqlite_sha256, _ = hash_file(reference.database_path)
        if (
            dependency.release_id != reference.release_id
            or dependency.canonical_sha256 != reference.canonical_sha256
            or dependency.sqlite_sha256 != sqlite_sha256
        ):
            raise SyntheaLocalizationError(f"Synthea profile dependency mismatch: {dataset_id}")


def _patient_identity(resource: dict[str, Any], identity: SyntheticIdentity) -> None:
    resource["name"] = [
        {
            "use": "official",
            "text": identity.display_name,
            "family": identity.family_name,
            "given": [identity.given_name],
        }
    ]
    resource["address"] = [
        {
            "use": "home",
            "line": [identity.address],
            "city": identity.city,
            "district": identity.district,
            "state": identity.province,
            "postalCode": identity.postal_code,
            "country": "CN",
            "extension": [
                {
                    "url": "http://hl7.org/fhir/StructureDefinition/geolocation",
                    "extension": [
                        {"url": "latitude", "valueDecimal": identity.latitude},
                        {"url": "longitude", "valueDecimal": identity.longitude},
                    ],
                }
            ],
        }
    ]
    if identity.district is None:
        resource["address"][0].pop("district")
    resource["telecom"] = [
        {"system": "phone", "value": identity.phone, "use": "home"},
        {"system": "email", "value": identity.email, "use": "home"},
    ]
    identifiers = [
        value
        for value in resource.get("identifier", [])
        if value.get("system") == "https://github.com/synthetichealth/synthea"
    ]
    identifiers.extend(
        [
            {
                "system": "urn:cn-health-data:synthetic-person",
                "value": identity.synthetic_person_id,
            },
            {
                "type": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/v2-0203",
                            "code": "MR",
                            "display": "Medical record number",
                        }
                    ]
                },
                "system": "urn:cn-health-data:synthetic-mrn",
                "value": identity.mrn,
            },
            {
                "type": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/v2-0203",
                            "code": "NI",
                            "display": "模拟居民身份号码",
                        }
                    ]
                },
                "system": "urn:cn-health-data:simulated-resident-id",
                "value": identity.simulated_resident_id,
                "extension": [{"url": "urn:cn-health-data:synthetic", "valueBoolean": True}],
            },
        ]
    )
    resource["identifier"] = identifiers
    resource["communication"] = [
        {
            "language": {
                "coding": [{"system": "urn:ietf:bcp:47", "code": "zh-CN", "display": "简体中文"}]
            },
            "preferred": True,
        }
    ]


def _related_identity(
    resource: dict[str, Any],
    identity: SyntheticIdentity,
    resource_type: str,
) -> None:
    if resource_type == "Practitioner":
        resource["name"] = [
            {
                "use": "official",
                "text": identity.display_name,
                "family": identity.family_name,
                "given": [identity.given_name],
            }
        ]
    elif not isinstance(resource.get("name"), str) or _CHINESE.search(resource["name"]) is None:
        resource["name"] = f"合成医疗机构-{resource['id']}"
    resource["address"] = [
        {
            "line": [identity.address],
            "city": identity.city,
            "state": identity.province,
            "postalCode": identity.postal_code,
            "country": "CN",
        }
    ]
    resource["telecom"] = [{"system": "phone", "value": identity.phone, "use": "work"}]
    resource["identifier"] = [
        {
            "system": f"urn:cn-health-data:synthetic-{resource_type.lower()}",
            "value": identity.synthetic_person_id,
        }
    ]


def localize_synthea_bundle(
    raw_bundle: dict[str, Any],
    *,
    profile_dir: Path,
    names_release_dir: Path,
    geography_release_dir: Path,
    population_release_dir: Path,
    seed: str,
) -> LocalizedSyntheaBundle:
    try:
        _BundleShape.model_validate(raw_bundle)
    except ValidationError as error:
        raise SyntheaLocalizationError("Synthea source Bundle is invalid") from error
    manifest = _load_profile(profile_dir)
    names = load_dataset_release_reference(names_release_dir, expected_dataset_id="names-cn")
    geography = load_dataset_release_reference(
        geography_release_dir, expected_dataset_id="geography-cn"
    )
    population = load_dataset_release_reference(
        population_release_dir, expected_dataset_id="population-cn"
    )
    references = {"geography-cn": geography, "names-cn": names, "population-cn": population}
    _release_dependencies(manifest, references)

    bundle = copy.deepcopy(raw_bundle)
    resources = [entry["resource"] for entry in bundle["entry"]]
    patients = [resource for resource in resources if resource.get("resourceType") == "Patient"]
    if len(patients) != 1:
        raise SyntheaLocalizationError("Synthea Bundle must contain exactly one Patient")
    patient = patients[0]
    patient_id = patient.get("id")
    birth_date = patient.get("birthDate")
    gender = patient.get("gender")
    if (
        not isinstance(patient_id, str)
        or not isinstance(birth_date, str)
        or gender
        not in {
            "female",
            "male",
            "other",
            "unknown",
        }
    ):
        raise SyntheaLocalizationError("Synthea Patient identity fields are invalid")
    identity_seed = f"{manifest.content_hash}:{patient_id}:{seed}"
    patient_identity = generate_synthetic_identity(
        names_release=names,
        geography_release=geography,
        seed=identity_seed,
        birth_date=birth_date,
        gender=gender,
    )
    _patient_identity(patient, patient_identity)
    for resource in resources:
        resource_type = resource.get("resourceType")
        if resource_type not in {"Practitioner", "Organization"}:
            continue
        related_identity = generate_synthetic_identity(
            names_release=names,
            geography_release=geography,
            seed=f"{identity_seed}:{resource_type}:{resource['id']}",
            birth_date="1980-01-01",
            gender="unknown",
        )
        _related_identity(resource, related_identity, resource_type)
    meta = bundle.setdefault("meta", {})
    tags = [
        tag
        for tag in meta.get("tag", [])
        if tag.get("system") != "urn:cn-health-data:synthea-profile"
    ]
    tags.append(
        {
            "system": "urn:cn-health-data:synthea-profile",
            "code": manifest.profile_id,
            "display": manifest.content_hash,
        }
    )
    meta["tag"] = tags
    return LocalizedSyntheaBundle(
        bundle=bundle,
        profile_id=manifest.profile_id,
        profile_content_hash=manifest.content_hash,
    )
