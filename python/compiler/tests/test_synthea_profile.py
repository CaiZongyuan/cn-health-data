import csv
import hashlib
import json
import sqlite3
import subprocess
from io import StringIO
from pathlib import Path

import yaml
from cn_health_compiler.cli import app
from cn_health_compiler.synthetic.synthea_profile import build_synthea_profile
from typer.testing import CliRunner

APPLICATION_ID = 1129203780
SYNTHEA_COMMIT = "d9d07a6eef91ee5144293b42ab64224d84d124f8"


def _release(root: Path, dataset_id: str, release_id: str, sql: str) -> Path:
    root.mkdir()
    database = root / "data.sqlite"
    connection = sqlite3.connect(database)
    try:
        connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        connection.executescript(sql)
    finally:
        connection.close()
    database_bytes = database.read_bytes()
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "release": {"id": release_id},
                "dataset": {"id": dataset_id},
                "canonical": {"sha256": hashlib.sha256(dataset_id.encode()).hexdigest()},
                "artifacts": [
                    {
                        "name": "data.sqlite",
                        "sha256": hashlib.sha256(database_bytes).hexdigest(),
                        "sizeBytes": len(database_bytes),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return root


def _names_release(root: Path) -> Path:
    return _release(
        root,
        "names-cn",
        "names-cn@fixture.r1",
        """
        CREATE TABLE name_component (
            code TEXT PRIMARY KEY, kind TEXT, gender TEXT, text TEXT, weight REAL
        );
        INSERT INTO name_component VALUES
            ('surname:王', 'surname', 'any', '王', 7),
            ('surname:欧阳', 'surname', 'any', '欧阳', 1),
            ('given-name:male:安宁', 'given-name', 'male', '安宁', 1),
            ('given-name:female:知夏', 'given-name', 'female', '知夏', 1);
        """,
    )


def _geography_release(root: Path) -> Path:
    return _release(
        root,
        "geography-cn",
        "geography-cn@fixture.r1",
        """
        CREATE TABLE administrative_division (
            code TEXT PRIMARY KEY, parent_code TEXT, level INTEGER, name_zh TEXT
        );
        CREATE TABLE postal_area (
            code TEXT PRIMARY KEY, postal_code TEXT, admin1_code TEXT,
            admin2_code TEXT, admin3_code TEXT, latitude REAL, longitude REAL
        );
        CREATE TABLE place (
            code TEXT PRIMARY KEY, kind TEXT, admin2_code TEXT, population INTEGER
        );
        INSERT INTO administrative_division VALUES
            ('32', NULL, 0, '江苏省'),
            ('3205', '32', 1, '苏州市'),
            ('320582', '3205', 2, '张家港市');
        INSERT INTO postal_area VALUES
            ('postal:215600', '215600', '04', '3205', '320582', 31.865, 120.5389);
        INSERT INTO place VALUES
            ('geonames:1', 'populated-place', '3205', 1432044);
        """,
    )


def _population_release(root: Path) -> Path:
    rows = []
    for start in range(0, 100, 5):
        end = start + 4
        rows.append(
            f"('CHN:Medium:2026:{start:03d}', 'CHN', 'Medium', 2026, {start}, {end}, "
            "1000, 1000, 2000)"
        )
    rows.append("('CHN:Medium:2026:100', 'CHN', 'Medium', 2026, 100, NULL, 100, 300, 400)")
    return _release(
        root,
        "population-cn",
        "population-cn@fixture.r1",
        """
        CREATE TABLE population_age_sex (
            code TEXT PRIMARY KEY, country_code TEXT, variant TEXT, year INTEGER,
            age_start INTEGER, age_end INTEGER, male_population INTEGER,
            female_population INTEGER, total_population INTEGER
        );
        INSERT INTO population_age_sex VALUES
        """
        + ",\n".join(rows)
        + ";",
    )


def test_profile_projects_versioned_datasets_to_synthea_resources(tmp_path: Path) -> None:
    names = _names_release(tmp_path / "names")
    geography = _geography_release(tmp_path / "geography")
    population = _population_release(tmp_path / "population")
    (tmp_path / ".gitignore").write_text("profiles/\ncli-profiles/\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main", tmp_path], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", tmp_path, "config", "user.email", "fixture@example.invalid"], check=True
    )
    subprocess.run(["git", "-C", tmp_path, "config", "user.name", "Fixture"], check=True)
    subprocess.run(["git", "-C", tmp_path, "add", "."], check=True)
    subprocess.run(
        ["git", "-C", tmp_path, "commit", "-m", "fixture"], check=True, capture_output=True
    )

    result = build_synthea_profile(
        repo_root=tmp_path,
        names_release_dir=names,
        geography_release_dir=geography,
        population_release_dir=population,
        output_root=tmp_path / "profiles",
        profile_version="2026-08-29",
        reference_year=2026,
        synthea_commit=SYNTHEA_COMMIT,
        git_commit="f" * 40,
    )

    expected_files = {
        "geography/demographics.csv",
        "geography/foreign_birthplace.json",
        "geography/timezones.csv",
        "geography/zipcodes.csv",
        "manifest.json",
        "names.yml",
        "payers/insurance_companies.csv",
        "payers/insurance_eligibilities.csv",
        "payers/insurance_plans.csv",
        "providers/hospitals.csv",
        "providers/primary_care_facilities.csv",
        "providers/urgent_care_facilities.csv",
        "synthea.properties",
    }
    assert {
        path.relative_to(result.profile_dir).as_posix()
        for path in result.profile_dir.rglob("*")
        if path.is_file()
    } == expected_files

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["supportedSyntheaCommit"] == SYNTHEA_COMMIT
    assert manifest["compiler"]["gitCommit"] == "f" * 40
    assert [dependency["datasetId"] for dependency in manifest["dependencies"]] == [
        "geography-cn",
        "names-cn",
        "population-cn",
    ]
    assert manifest["projectionPolicy"]["demographicsCompatibility"] == "synthetic"

    demographic_rows = list(
        csv.DictReader(StringIO((result.profile_dir / "geography/demographics.csv").read_text()))
    )
    assert len(demographic_rows) == 1
    row = demographic_rows[0]
    assert row["NAME"] == "苏州市-3205"
    assert row["STNAME"] == "中国"
    assert abs(sum(float(row[str(index)]) for index in range(1, 19)) - 1) < 1e-9
    assert abs(float(row["TOT_MALE"]) + float(row["TOT_FEMALE"]) - 1) < 1e-9

    names_yml = yaml.safe_load((result.profile_dir / "names.yml").read_text(encoding="utf-8"))
    assert set(names_yml["english"]["family"]) == {"王", "欧阳"}
    assert names_yml["english"]["M"] == ["安宁"]
    assert "中国" in (result.profile_dir / "providers/hospitals.csv").read_text(encoding="utf-8")
    properties = (result.profile_dir / "synthea.properties").read_text(encoding="utf-8")
    assert "generate.geography.country_code = CN" in properties
    assert "generate.demographics.default_file = geography/demographics.csv" in properties

    cli_result = CliRunner().invoke(
        app,
        [
            "synthea",
            "profile",
            "--names-release",
            str(names),
            "--geography-release",
            str(geography),
            "--population-release",
            str(population),
            "--output-root",
            str(tmp_path / "cli-profiles"),
            "--profile-version",
            "2026-08-29",
            "--reference-year",
            "2026",
            "--synthea-commit",
            SYNTHEA_COMMIT,
            "--repo-root",
            str(tmp_path),
        ],
    )
    assert cli_result.exit_code == 0, cli_result.output
    assert "synthea-cn-profile/releases/2026-08-29.r1/manifest.json" in cli_result.output
