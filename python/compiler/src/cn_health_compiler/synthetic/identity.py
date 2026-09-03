"""Deterministic Chinese synthetic identity generation."""

import hashlib
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cn_health_compiler.core.source import hash_file
from cn_health_compiler.core.sqlite import SQLITE_APPLICATION_ID

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ALGORITHM_VERSION = "synthetic-identity-v1"
_WEIGHT_SCALE = Decimal("1000000")
_NAMESPACE = uuid.UUID("6b168d1a-7338-5ec7-9ac6-e8dbad005a68")
_ID_CARD_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_ID_CARD_CHECKS = ("1", "0", "X", "9", "8", "7", "6", "5", "4", "3", "2")

type Gender = Literal["female", "male", "other", "unknown"]


class CandidateReleaseError(ValueError):
    """Raised when a Candidate Release cannot be trusted by a consumer."""


class _ManifestIdentity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1)


class _ManifestCanonical(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class _ManifestArtifact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    compression: str | None = None
    name: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(alias="sizeBytes", ge=0)
    uncompressed_name: str | None = Field(default=None, alias="uncompressedName")
    uncompressed_sha256: str | None = Field(
        default=None,
        alias="uncompressedSha256",
        pattern=r"^[0-9a-f]{64}$",
    )
    uncompressed_size_bytes: int | None = Field(
        default=None,
        alias="uncompressedSizeBytes",
        ge=0,
    )


class _CandidateManifest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dataset: _ManifestIdentity
    release: _ManifestIdentity
    canonical: _ManifestCanonical
    artifacts: list[_ManifestArtifact]


@dataclass(frozen=True, slots=True)
class DatasetReleaseReference:
    database_path: Path
    release_id: str
    canonical_sha256: str

    def __post_init__(self) -> None:
        if not self.database_path.is_file():
            raise ValueError(f"Dataset database does not exist: {self.database_path}")
        if not self.release_id:
            raise ValueError("Dataset release ID is required")
        if _SHA256.fullmatch(self.canonical_sha256) is None:
            raise ValueError("Dataset canonical SHA256 is invalid")


@dataclass(frozen=True, slots=True)
class SyntheticIdentity:
    algorithm_version: str
    synthetic_person_id: str
    mrn: str
    family_name: str
    given_name: str
    display_name: str
    address: str
    province: str
    city: str
    district: str | None
    postal_code: str
    latitude: float
    longitude: float
    phone: str
    email: str
    simulated_resident_id: str
    names_release_id: str
    names_canonical_sha256: str
    geography_release_id: str
    geography_canonical_sha256: str


@dataclass(frozen=True, slots=True)
class _Location:
    postal_code: str
    province: str
    city: str
    district: str | None
    latitude: float
    longitude: float


def load_dataset_release_reference(
    release_dir: Path,
    *,
    expected_dataset_id: str,
) -> DatasetReleaseReference:
    release_dir = release_dir.resolve(strict=True)
    try:
        manifest = _CandidateManifest.model_validate_json(
            (release_dir / "manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise CandidateReleaseError("Candidate Manifest is unreadable") from error
    if manifest.dataset.id != expected_dataset_id:
        raise CandidateReleaseError("Candidate belongs to a different Dataset")
    sqlite_artifacts = [
        (artifact.sha256, artifact.size_bytes)
        for artifact in manifest.artifacts
        if artifact.name == "data.sqlite"
    ]
    if not sqlite_artifacts:
        sqlite_artifacts = [
            (artifact.uncompressed_sha256, artifact.uncompressed_size_bytes)
            for artifact in manifest.artifacts
            if (
            artifact.name == "data.sqlite.zst"
            and artifact.compression == "zstd"
            and artifact.uncompressed_name == "data.sqlite"
            and artifact.uncompressed_sha256 is not None
            and artifact.uncompressed_size_bytes is not None
            )
        ]
    if len(sqlite_artifacts) != 1:
        raise CandidateReleaseError("Candidate must declare one SQLite artifact")
    expected_sha256, expected_size = sqlite_artifacts[0]
    database_path = release_dir / "data.sqlite"
    try:
        actual_sha256, actual_size = hash_file(database_path)
    except OSError as error:
        raise CandidateReleaseError("Candidate SQLite artifact is unreadable") from error
    if (actual_sha256, actual_size) != (expected_sha256, expected_size):
        raise CandidateReleaseError("Candidate SQLite SHA256 or size does not match Manifest")
    connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    try:
        if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise CandidateReleaseError("Candidate SQLite integrity check failed")
        application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
        if application_id != SQLITE_APPLICATION_ID:
            raise CandidateReleaseError("Candidate SQLite application ID is invalid")
    finally:
        connection.close()
    return DatasetReleaseReference(
        database_path=database_path,
        release_id=manifest.release.id,
        canonical_sha256=manifest.canonical.sha256,
    )


def _digest_number(seed: str, label: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}:{label}".encode()).digest(), "big")


def _weighted_choice(rows: list[tuple[str, float]], seed: str, label: str) -> str:
    weighted = [
        (text, int((Decimal(str(weight)) * _WEIGHT_SCALE).to_integral_value()))
        for text, weight in rows
    ]
    if not weighted or any(weight <= 0 for _, weight in weighted):
        raise ValueError(f"No positive weights are available for {label}")
    target = _digest_number(seed, label) % sum(weight for _, weight in weighted)
    for text, weight in weighted:
        if target < weight:
            return text
        target -= weight
    raise RuntimeError("weighted selection exhausted its range")


def _name_rows(
    reference: DatasetReleaseReference,
    gender: Gender,
    seed: str,
) -> tuple[str, str]:
    selected_gender: Literal["female", "male"] = (
        gender
        if gender in ("female", "male")
        else ("female" if _digest_number(seed, "fallback-gender") % 2 == 0 else "male")
    )
    connection = sqlite3.connect(f"file:{reference.database_path}?mode=ro", uri=True)
    try:
        surnames = [
            (str(row[0]), float(row[1]))
            for row in connection.execute(
                "SELECT text, weight FROM name_component "
                "WHERE kind = 'surname' AND gender = 'any' ORDER BY code"
            )
        ]
        given_names = [
            (str(row[0]), float(row[1]))
            for row in connection.execute(
                "SELECT text, weight FROM name_component "
                "WHERE kind = 'given-name' AND gender = ? ORDER BY code",
                (selected_gender,),
            )
        ]
    finally:
        connection.close()
    return _weighted_choice(surnames, seed, "surname"), _weighted_choice(
        given_names, seed, f"given-name:{selected_gender}"
    )


def _locations(reference: DatasetReleaseReference) -> list[_Location]:
    connection = sqlite3.connect(f"file:{reference.database_path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            """SELECT
                postal.postal_code,
                province.name_zh,
                city.name_zh,
                district.name_zh,
                postal.latitude,
                postal.longitude
            FROM postal_area AS postal
            JOIN administrative_division AS city
              ON city.code = postal.admin2_code AND city.level = 1
            JOIN administrative_division AS province
              ON province.code = city.parent_code AND province.level = 0
            LEFT JOIN administrative_division AS district
              ON district.code = postal.admin3_code AND district.level = 2
            ORDER BY postal.code"""
        ).fetchall()
    finally:
        connection.close()
    return [
        _Location(
            postal_code=str(row[0]),
            province=str(row[1]),
            city=str(row[2]),
            district=None if row[3] is None else str(row[3]),
            latitude=float(row[4]),
            longitude=float(row[5]),
        )
        for row in rows
    ]


def _simulated_resident_id(birth_date: date, gender: Gender, seed: str) -> str:
    sequence = _digest_number(seed, "resident-sequence") % 1000
    if gender == "male" and sequence % 2 == 0:
        sequence = (sequence + 1) % 1000
    elif gender == "female" and sequence % 2 == 1:
        sequence = (sequence + 1) % 1000
    body = f"990000{birth_date:%Y%m%d}{sequence:03d}"
    checksum_index = (
        sum(int(digit) * weight for digit, weight in zip(body, _ID_CARD_WEIGHTS, strict=True)) % 11
    )
    return f"{body}{_ID_CARD_CHECKS[checksum_index]}"


def generate_synthetic_identity(
    *,
    names_release: DatasetReleaseReference,
    geography_release: DatasetReleaseReference,
    seed: str,
    birth_date: str,
    gender: Gender,
) -> SyntheticIdentity:
    if not seed:
        raise ValueError("identity seed is required")
    parsed_birth_date = date.fromisoformat(birth_date)
    effective_seed = "|".join(
        (
            _ALGORITHM_VERSION,
            names_release.release_id,
            names_release.canonical_sha256,
            geography_release.release_id,
            geography_release.canonical_sha256,
            seed,
        )
    )
    family_name, given_name = _name_rows(names_release, gender, effective_seed)
    locations = _locations(geography_release)
    if not locations:
        raise ValueError("Geography release has no usable postal locations")
    location = locations[_digest_number(effective_seed, "location") % len(locations)]
    address_number = _digest_number(effective_seed, "address-number") % 900 + 100
    address = "".join(
        part
        for part in (
            location.province,
            location.city,
            location.district,
            f"合成路{address_number}号",
        )
        if part is not None
    )
    identifier_digest = hashlib.sha256(effective_seed.encode()).hexdigest()
    synthetic_person_id = f"urn:uuid:{uuid.uuid5(_NAMESPACE, effective_seed)}"
    mrn = f"CNH{identifier_digest[:12].upper()}"
    phone = f"100{_digest_number(effective_seed, 'phone') % 100_000_000:08d}"
    return SyntheticIdentity(
        algorithm_version=_ALGORITHM_VERSION,
        synthetic_person_id=synthetic_person_id,
        mrn=mrn,
        family_name=family_name,
        given_name=given_name,
        display_name=f"{family_name}{given_name}",
        address=address,
        province=location.province,
        city=location.city,
        district=location.district,
        postal_code=location.postal_code,
        latitude=location.latitude,
        longitude=location.longitude,
        phone=phone,
        email=f"{mrn.lower()}@example.test",
        simulated_resident_id=_simulated_resident_id(parsed_birth_date, gender, effective_seed),
        names_release_id=names_release.release_id,
        names_canonical_sha256=names_release.canonical_sha256,
        geography_release_id=geography_release.release_id,
        geography_canonical_sha256=geography_release.canonical_sha256,
    )
