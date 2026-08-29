"""Project canonical Chinese datasets into a versioned Synthea profile."""

import csv
import hashlib
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from io import StringIO
from pathlib import Path
from typing import Any

import rfc8785
import yaml

from cn_health_compiler import __version__
from cn_health_compiler.core.candidate import candidate_staging_directory, resolve_git_commit
from cn_health_compiler.core.manifest import write_json_atomic
from cn_health_compiler.core.source import hash_file
from cn_health_compiler.synthetic.identity import (
    DatasetReleaseReference,
    load_dataset_release_reference,
)

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_AGE_STARTS = tuple(range(0, 85, 5))
_INCOME_FIELDS = (
    "00..10",
    "10..15",
    "15..25",
    "25..35",
    "35..50",
    "50..75",
    "75..100",
    "100..150",
    "150..200",
    "200..999",
)
_EDUCATION_FIELDS = ("LESS_THAN_HS", "HS_DEGREE", "SOME_COLLEGE", "BS_DEGREE")
_INCOME = (0.02, 0.03, 0.08, 0.15, 0.22, 0.24, 0.15, 0.08, 0.02, 0.01)
_EDUCATION = (0.20, 0.30, 0.30, 0.20)
_DEMOGRAPHICS_FIELDS = (
    "ID",
    "COUNTY",
    "NAME",
    "STNAME",
    "POPESTIMATE2015",
    "CTYNAME",
    "TOT_POP",
    "TOT_MALE",
    "TOT_FEMALE",
    "WHITE",
    "HISPANIC",
    "BLACK",
    "ASIAN",
    "NATIVE",
    "OTHER",
    *(str(index) for index in range(1, 19)),
    *_INCOME_FIELDS,
    *_EDUCATION_FIELDS,
)
_PROVIDER_FIELDS = (
    "",
    "id",
    "name",
    "address",
    "city",
    "state",
    "zip",
    "county",
    "phone",
    "type",
    "ownership",
    "emergency",
    "quality",
    "LAT",
    "LON",
)


@dataclass(frozen=True, slots=True)
class SyntheaProfileBuild:
    profile_dir: Path
    manifest_path: Path


@dataclass(frozen=True, slots=True)
class _City:
    code: str
    name: str
    province: str
    population: int
    postal_code: str
    latitude: float
    longitude: float

    @property
    def synthea_name(self) -> str:
        return f"{self.name}-{self.code}"


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def _csv_text(fieldnames: tuple[str, ...], rows: list[dict[str, object]]) -> str:
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _name_profile(reference: DatasetReleaseReference) -> dict[str, object]:
    connection = sqlite3.connect(f"file:{reference.database_path}?mode=ro", uri=True)
    try:
        surnames = [
            (str(row[0]), Decimal(str(row[1])))
            for row in connection.execute(
                "SELECT text, weight FROM name_component "
                "WHERE kind = 'surname' AND gender = 'any' ORDER BY code"
            )
        ]
        male = [
            str(row[0])
            for row in connection.execute(
                "SELECT text FROM name_component "
                "WHERE kind = 'given-name' AND gender = 'male' ORDER BY code"
            )
        ]
        female = [
            str(row[0])
            for row in connection.execute(
                "SELECT text FROM name_component "
                "WHERE kind = 'given-name' AND gender = 'female' ORDER BY code"
            )
        ]
    finally:
        connection.close()
    if not surnames or not male or not female:
        raise ValueError("Names release has no usable components")
    family = [
        name
        for name, weight in surnames
        for _ in range(max(1, int((weight * Decimal(100)).quantize(1, rounding=ROUND_HALF_UP))))
    ]
    return {
        "english": {"M": male, "F": female, "family": family},
        "street": {"type": ["路", "街", "巷"], "secondary": ["单元", "室"]},
    }


def _population_profile(
    reference: DatasetReleaseReference,
    year: int,
) -> tuple[list[float], float, float, int]:
    connection = sqlite3.connect(f"file:{reference.database_path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            """SELECT age_start, male_population, female_population, total_population
            FROM population_age_sex
            WHERE country_code = 'CHN' AND variant = 'Medium' AND year = ?
            ORDER BY age_start""",
            (year,),
        ).fetchall()
    finally:
        connection.close()
    if len(rows) != 21:
        raise ValueError(f"Population release has no complete {year} age distribution")
    by_start = {int(row[0]): int(row[3]) for row in rows}
    if set(by_start) != {*range(0, 100, 5), 100}:
        raise ValueError("Population release has unexpected age groups")
    total = sum(by_start.values())
    male = sum(int(row[1]) for row in rows)
    female = sum(int(row[2]) for row in rows)
    age_counts = [by_start[start] for start in _AGE_STARTS]
    age_counts.append(sum(value for start, value in by_start.items() if start >= 85))
    return (
        [value / total for value in age_counts],
        male / (male + female),
        female / (male + female),
        total,
    )


def _cities(reference: DatasetReleaseReference) -> list[_City]:
    connection = sqlite3.connect(f"file:{reference.database_path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            """SELECT
                city.code,
                city.name_zh,
                province.name_zh,
                max(COALESCE(place.population, 1)),
                min(postal.postal_code),
                avg(postal.latitude),
                avg(postal.longitude)
            FROM administrative_division AS city
            JOIN administrative_division AS province
              ON province.code = city.parent_code AND province.level = 0
            JOIN postal_area AS postal ON postal.admin2_code = city.code
            LEFT JOIN place
              ON place.admin2_code = city.code AND place.kind = 'populated-place'
            WHERE city.level = 1
            GROUP BY city.code, city.name_zh, province.name_zh
            ORDER BY city.code"""
        ).fetchall()
    finally:
        connection.close()
    cities = [
        _City(
            code=str(row[0]),
            name=str(row[1]),
            province=str(row[2]),
            population=max(1, int(row[3])),
            postal_code=str(row[4]),
            latitude=float(row[5]),
            longitude=float(row[6]),
        )
        for row in rows
    ]
    if not cities:
        raise ValueError("Geography release has no Synthea-compatible cities")
    return cities


def _demographics(
    cities: list[_City], ages: list[float], male: float, female: float, total: int
) -> str:
    rows: list[dict[str, object]] = []
    for city in cities:
        row: dict[str, object] = {
            "ID": city.code,
            "COUNTY": city.province,
            "NAME": city.synthea_name,
            "STNAME": "中国",
            "POPESTIMATE2015": city.population,
            "CTYNAME": city.province,
            "TOT_POP": total,
            "TOT_MALE": male,
            "TOT_FEMALE": female,
            "WHITE": 0,
            "HISPANIC": 0,
            "BLACK": 0,
            "ASIAN": 1,
            "NATIVE": 0,
            "OTHER": 0,
        }
        row.update({str(index): value for index, value in enumerate(ages, start=1)})
        row.update(dict(zip(_INCOME_FIELDS, _INCOME, strict=True)))
        row.update(dict(zip(_EDUCATION_FIELDS, _EDUCATION, strict=True)))
        rows.append(row)
    return _csv_text(_DEMOGRAPHICS_FIELDS, rows)


def _zipcodes(cities: list[_City]) -> str:
    return _csv_text(
        ("", "USPS", "ST", "NAME", "ZCTA5", "LAT", "LON"),
        [
            {
                "": index,
                "USPS": "中国",
                "ST": "CN",
                "NAME": city.synthea_name,
                "ZCTA5": city.postal_code,
                "LAT": city.latitude,
                "LON": city.longitude,
            }
            for index, city in enumerate(cities)
        ],
    )


def _providers(cities: list[_City], provider_type: str) -> str:
    names = {
        "hospital": "合成人民医院",
        "primary": "合成基层医疗中心",
        "urgent": "合成急诊中心",
    }
    return _csv_text(
        _PROVIDER_FIELDS,
        [
            {
                "": index,
                "id": f"CNH-{provider_type.upper()}-{city.code}",
                "name": f"{city.name}{names[provider_type]}",
                "address": "合成路1号",
                "city": city.synthea_name,
                "state": "中国",
                "zip": city.postal_code,
                "county": city.province,
                "phone": "10000000000",
                "type": names[provider_type],
                "ownership": "Synthetic",
                "emergency": "Yes" if provider_type in ("hospital", "urgent") else "No",
                "quality": 3,
                "LAT": city.latitude,
                "LON": city.longitude,
            }
            for index, city in enumerate(cities)
        ],
    )


def _properties() -> str:
    values = {
        "exporter.baseDirectory": "./output/",
        "exporter.pretty_print": "false",
        "exporter.years_of_history": "10",
        "exporter.fhir.export": "true",
        "exporter.fhir_stu3.export": "false",
        "exporter.fhir_dstu2.export": "false",
        "exporter.fhir.use_us_core_ig": "false",
        "exporter.fhir.transaction_bundle": "false",
        "exporter.hospital.fhir.export": "false",
        "exporter.practitioner.fhir.export": "false",
        "exporter.csv.export": "false",
        "generate.thread_pool_size": "1",
        "generate.demographics.default_file": "geography/demographics.csv",
        "generate.geography.zipcodes.default_file": "geography/zipcodes.csv",
        "generate.geography.country_code": "CN",
        "generate.geography.timezones.default_file": "geography/timezones.csv",
        "generate.geography.foreign.birthplace.default_file": "geography/foreign_birthplace.json",
        "generate.geography.sdoh.default_file": "",
        "generate.geography.passport_uri": "urn:cn-health-data:synthetic-passport",
        "generate.append_numbers_to_person_names": "false",
        "generate.providers.hospitals.default_file": "providers/hospitals.csv",
        "generate.providers.primarycare.default_file": "providers/primary_care_facilities.csv",
        "generate.providers.urgentcare.default_file": "providers/urgent_care_facilities.csv",
        "generate.providers.ihs.hospitals.default_file": "",
        "generate.providers.ihs.primarycare.default_file": "",
        "generate.providers.veterans.default_file": "",
        "generate.providers.homehealth.default_file": "",
        "generate.providers.hospice.default_file": "",
        "generate.providers.nursing.default_file": "",
        "generate.payers.insurance_companies.default_file": "payers/insurance_companies.csv",
        "generate.payers.insurance_plans.default_file": "payers/insurance_plans.csv",
        "generate.payers.insurance_plans.eligibilities_file": "payers/insurance_eligibilities.csv",
        "generate.payers.insurance_companies.medicare": "模拟基本医疗保险",
        "generate.payers.insurance_companies.medicaid": "模拟基本医疗保险",
        "generate.payers.insurance_companies.dual_eligible": "模拟基本医疗保险",
        "generate.payers.selection_behavior": "priority",
        "generate.payers.loss_of_care": "false",
    }
    return "".join(f"{key} = {value}\n" for key, value in values.items())


def _payer_files() -> dict[str, str]:
    return {
        "payers/insurance_companies.csv": _csv_text(
            (
                "Id",
                "Name",
                "Address",
                "City",
                "State Headquarterd",
                "Zip",
                "Phone",
                "States Covered",
                "Ownership",
                "Priority Level",
            ),
            [
                {
                    "Id": "10001",
                    "Name": "模拟基本医疗保险",
                    "Address": "合成路1号",
                    "City": "北京市",
                    "State Headquarterd": "中国",
                    "Zip": "100000",
                    "Phone": "10000000000",
                    "States Covered": "*",
                    "Ownership": "Synthetic",
                    "Priority Level": 1,
                }
            ],
        ),
        "payers/insurance_plans.csv": _csv_text(
            (
                "Payer Id",
                "Plan Id",
                "Name",
                "Services Covered",
                "Deductible",
                "Default Coinsurance",
                "Default Copay",
                "Monthly Premium",
                "Medicare Supplement",
                "Eligibility Policy",
                "Start Year",
                "End Year",
                "Notes",
            ),
            [
                {
                    "Payer Id": "10001",
                    "Plan Id": "10010",
                    "Name": "模拟基本医疗保险计划",
                    "Services Covered": "*",
                    "Deductible": 0,
                    "Default Coinsurance": 0,
                    "Default Copay": 0,
                    "Monthly Premium": 0,
                    "Medicare Supplement": "false",
                    "Eligibility Policy": "EveryoneEligible",
                    "Start Year": 0,
                    "End Year": "",
                    "Notes": "",
                }
            ],
        ),
        "payers/insurance_eligibilities.csv": _csv_text(
            (
                "Name",
                "Poverty Multiplier",
                "Income Threshold",
                "Age Threshold",
                "Qualifying Codes",
                "Qualifying Attributes",
                "Poverty Multiplier File",
                "Spenddown File",
                "Acceptance Likelihood",
                "Sub-Eligibilities",
                "Logical Operator",
            ),
            [
                {
                    "Name": "EveryoneEligible",
                    "Poverty Multiplier": "",
                    "Income Threshold": "",
                    "Age Threshold": 0,
                    "Qualifying Codes": "",
                    "Qualifying Attributes": "",
                    "Poverty Multiplier File": "",
                    "Spenddown File": "",
                    "Acceptance Likelihood": "",
                    "Sub-Eligibilities": "",
                    "Logical Operator": "",
                }
            ],
        ),
    }


def _dependency(dataset_id: str, reference: DatasetReleaseReference) -> dict[str, str]:
    artifact_sha256, _ = hash_file(reference.database_path)
    return {
        "datasetId": dataset_id,
        "releaseId": reference.release_id,
        "canonicalSha256": reference.canonical_sha256,
        "sqliteSha256": artifact_sha256,
    }


def build_synthea_profile(
    *,
    repo_root: Path,
    names_release_dir: Path,
    geography_release_dir: Path,
    population_release_dir: Path,
    output_root: Path,
    profile_version: str,
    reference_year: int,
    synthea_commit: str,
    build_revision: int = 1,
    created_at: datetime | None = None,
    git_commit: str | None = None,
) -> SyntheaProfileBuild:
    repo_root = repo_root.resolve(strict=True)
    if not profile_version or "/" in profile_version or ".." in profile_version:
        raise ValueError("profile version is invalid")
    if _COMMIT.fullmatch(synthea_commit) is None:
        raise ValueError("Synthea commit must be a full lowercase SHA")
    resolved_commit = resolve_git_commit(repo_root, git_commit)
    names = load_dataset_release_reference(names_release_dir, expected_dataset_id="names-cn")
    geography = load_dataset_release_reference(
        geography_release_dir, expected_dataset_id="geography-cn"
    )
    population = load_dataset_release_reference(
        population_release_dir, expected_dataset_id="population-cn"
    )
    cities = _cities(geography)
    ages, male, female, total = _population_profile(population, reference_year)
    storage_key = f"{profile_version}.r{build_revision}"
    releases_dir = output_root / "synthea-cn-profile/releases"
    with candidate_staging_directory(releases_dir, storage_key) as (profile_dir, release_dir):
        resources = {
            "names.yml": yaml.safe_dump(
                _name_profile(names), allow_unicode=True, sort_keys=False, width=120
            ),
            "geography/demographics.csv": _demographics(cities, ages, male, female, total),
            "geography/zipcodes.csv": _zipcodes(cities),
            "geography/timezones.csv": (
                "STATE,ST,TIMEZONE,TZ\n中国,CN,China Standard Time,Asia/Shanghai\n"
            ),
            "geography/foreign_birthplace.json": json.dumps(
                {"english": ["北京市,中国,CN"], "chinese": ["北京市,中国,CN"]},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            "providers/hospitals.csv": _providers(cities, "hospital"),
            "providers/primary_care_facilities.csv": _providers(cities, "primary"),
            "providers/urgent_care_facilities.csv": _providers(cities, "urgent"),
            **_payer_files(),
        }
        files = {
            "synthea.properties": _properties(),
            **{f"classpath/{path}": content for path, content in resources.items()},
        }
        for relative_path, content in files.items():
            _write_text(profile_dir / relative_path, content)
        file_entries: list[dict[str, str | int]] = []
        for relative_path in sorted(files):
            sha256, size_bytes = hash_file(profile_dir / relative_path)
            file_entries.append({"path": relative_path, "sha256": sha256, "sizeBytes": size_bytes})
        dependencies = [
            _dependency("geography-cn", geography),
            _dependency("names-cn", names),
            _dependency("population-cn", population),
        ]
        policy: dict[str, Any] = {
            "demographicsCompatibility": "synthetic",
            "incomeDistribution": list(_INCOME),
            "educationDistribution": list(_EDUCATION),
            "raceProjection": {"ASIAN": 1},
            "identityAlgorithm": "synthetic-identity-v1",
            "referenceYear": reference_year,
        }
        compiler: dict[str, str | int] = {
            "name": "cn-health-compiler",
            "version": __version__,
            "adapter": "synthea-cn-profile",
            "adapterVersion": 1,
            "gitCommit": resolved_commit,
        }
        content_hash = hashlib.sha256(
            rfc8785.dumps(
                {
                    "supportedSyntheaCommit": synthea_commit,
                    "dependencies": dependencies,
                    "projectionPolicy": policy,
                    "compiler": compiler,
                    "files": file_entries,
                }
            )
        ).hexdigest()
        timestamp = created_at or datetime.now(UTC)
        if timestamp.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        manifest = {
            "schemaVersion": 1,
            "profileId": f"synthea-cn@{storage_key}",
            "storageKey": storage_key,
            "createdAt": timestamp.astimezone(UTC)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "supportedSyntheaCommit": synthea_commit,
            "dependencies": dependencies,
            "projectionPolicy": policy,
            "compiler": compiler,
            "files": file_entries,
            "contentHash": content_hash,
        }
        write_json_atomic(profile_dir / "manifest.json", manifest)
        return SyntheaProfileBuild(release_dir, release_dir / "manifest.json")
