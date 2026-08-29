import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from cn_health_compiler.synthetic.identity import (
    CandidateReleaseError,
    DatasetReleaseReference,
    generate_synthetic_identity,
    load_dataset_release_reference,
)


def _names_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA application_id = 1129203780")
        connection.executescript(
            """
            CREATE TABLE name_component (
                code TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                gender TEXT NOT NULL,
                text TEXT NOT NULL,
                weight REAL NOT NULL
            );
            INSERT INTO name_component VALUES
                ('surname:王', 'surname', 'any', '王', 7.17),
                ('surname:欧阳', 'surname', 'any', '欧阳', 0.068),
                ('given-name:male:安宁', 'given-name', 'male', '安宁', 1),
                ('given-name:male:思远', 'given-name', 'male', '思远', 1),
                ('given-name:female:知夏', 'given-name', 'female', '知夏', 1);
            """
        )
    finally:
        connection.close()


def _geography_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA application_id = 1129203780")
        connection.executescript(
            """
            CREATE TABLE administrative_division (
                code TEXT PRIMARY KEY,
                parent_code TEXT,
                level INTEGER NOT NULL,
                name_zh TEXT NOT NULL
            );
            CREATE TABLE postal_area (
                code TEXT PRIMARY KEY,
                postal_code TEXT NOT NULL,
                admin1_code TEXT NOT NULL,
                admin2_code TEXT NOT NULL,
                admin3_code TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL
            );
            INSERT INTO administrative_division VALUES
                ('32', NULL, 0, '江苏省'),
                ('3205', '32', 1, '苏州市'),
                ('320582', '3205', 2, '张家港市');
            INSERT INTO postal_area VALUES
                ('postal:215600', '215600', '04', '3205', '320582', 31.865, 120.5389);
            """
        )
    finally:
        connection.close()


def _resident_checksum(value: str) -> str:
    weights = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
    checks = ("1", "0", "X", "9", "8", "7", "6", "5", "4", "3", "2")
    return checks[
        sum(int(digit) * weight for digit, weight in zip(value, weights, strict=True)) % 11
    ]


def test_synthetic_identity_is_deterministic_and_non_routable(tmp_path: Path) -> None:
    names = tmp_path / "names.sqlite"
    geography = tmp_path / "geography.sqlite"
    _names_database(names)
    _geography_database(geography)
    names_release = DatasetReleaseReference(
        database_path=names,
        release_id="names-cn@40.37.0.r1",
        canonical_sha256="a" * 64,
    )
    geography_release = DatasetReleaseReference(
        database_path=geography,
        release_id="geography-cn@2026-08-29.r1",
        canonical_sha256="b" * 64,
    )

    first = generate_synthetic_identity(
        names_release=names_release,
        geography_release=geography_release,
        seed="patient-42",
        birth_date="1988-06-18",
        gender="male",
    )
    repeated = generate_synthetic_identity(
        names_release=names_release,
        geography_release=geography_release,
        seed="patient-42",
        birth_date="1988-06-18",
        gender="male",
    )
    different = generate_synthetic_identity(
        names_release=names_release,
        geography_release=geography_release,
        seed="patient-43",
        birth_date="1988-06-18",
        gender="male",
    )

    assert first == repeated
    assert first != different
    assert first.display_name == f"{first.family_name}{first.given_name}"
    assert first.address.startswith("江苏省苏州市张家港市合成路")
    assert first.postal_code == "215600"
    assert first.phone.startswith("100") and len(first.phone) == 11
    assert first.email.endswith("@example.test")
    assert first.simulated_resident_id.startswith("99000019880618")
    assert first.simulated_resident_id[-1] == _resident_checksum(first.simulated_resident_id[:-1])
    assert int(first.simulated_resident_id[-2]) % 2 == 1
    assert first.algorithm_version == "synthetic-identity-v1"
    assert first.names_release_id == names_release.release_id
    assert first.geography_release_id == geography_release.release_id

    generated_names = {
        generate_synthetic_identity(
            names_release=names_release,
            geography_release=geography_release,
            seed=f"patient-{index}",
            birth_date="1988-06-18",
            gender="male",
        ).display_name
        for index in range(16)
    }
    assert len(generated_names) > 1


def test_candidate_release_loader_verifies_manifest_and_sqlite(tmp_path: Path) -> None:
    release = tmp_path / "names-release"
    release.mkdir()
    database = release / "data.sqlite"
    _names_database(database)
    database_bytes = database.read_bytes()
    database_sha256 = hashlib.sha256(database_bytes).hexdigest()
    (release / "manifest.json").write_text(
        json.dumps(
            {
                "release": {"id": "names-cn@40.37.0.r1"},
                "dataset": {"id": "names-cn"},
                "canonical": {"sha256": "a" * 64},
                "artifacts": [
                    {
                        "name": "data.sqlite",
                        "sha256": database_sha256,
                        "sizeBytes": len(database_bytes),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    reference = load_dataset_release_reference(release, expected_dataset_id="names-cn")

    assert reference.release_id == "names-cn@40.37.0.r1"
    assert reference.database_path == database

    with database.open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(CandidateReleaseError, match="SHA256 or size"):
        load_dataset_release_reference(release, expected_dataset_id="names-cn")
