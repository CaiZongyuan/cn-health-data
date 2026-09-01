import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest
import yaml
from _loinc import fixture_repository
from cn_health_compiler.cli import app
from cn_health_compiler.core.source import SourceIntegrityError
from cn_health_compiler.core.validation import validate_dataset_contracts
from cn_health_compiler.sources.loinc.build import build_loinc_candidate
from jsonschema import Draft202012Validator, FormatChecker
from typer.testing import CliRunner


def test_complete_loinc_candidate_is_reproducible_and_cli_builds(tmp_path: Path) -> None:
    fixture = fixture_repository(tmp_path)
    assert validate_dataset_contracts(tmp_path) == (tmp_path / "datasets/loinc-zh-cn/dataset.yaml",)
    first = build_loinc_candidate(
        repo_root=tmp_path,
        core_source_path=fixture.core_archive,
        translation_source_path=fixture.translation_archive,
        output_root=tmp_path / ".work/build-one",
        git_commit="d" * 40,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    second = build_loinc_candidate(
        repo_root=tmp_path,
        core_source_path=fixture.core_archive,
        translation_source_path=fixture.translation_archive,
        output_root=tmp_path / ".work/build-two",
        git_commit="d" * 40,
        created_at=datetime(2026, 9, 2, tzinfo=UTC),
    )

    assert (first.release_dir / "data.sqlite").read_bytes() == (
        second.release_dir / "data.sqlite"
    ).read_bytes()
    first_manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    second_manifest = json.loads(second.manifest_path.read_text(encoding="utf-8"))
    assert first_manifest["canonical"] == second_manifest["canonical"]
    assert first_manifest["dataset"] == {
        "id": "loinc-zh-cn",
        "sourceVersion": "fixture-1",
        "datasetSchemaVersion": 2,
        "status": "experimental",
    }
    assert first_manifest["canonical"]["recordCount"] == 9
    assert [table["recordCount"] for table in first_manifest["canonical"]["tables"]] == [
        3,
        4,
        1,
        1,
    ]
    assert [source["roles"] for source in first_manifest["sources"]] == [
        ["core"],
        ["linguistic-variant"],
    ]
    assert first_manifest["rights"]["allowedArtifactTypes"] == [
        "sqlite",
        "sqlite-zstd",
        "parquet",
    ]
    manifest_schema = json.loads(
        (tmp_path / "schemas/manifest.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(manifest_schema, format_checker=FormatChecker()).validate(first_manifest)
    assert sorted(path.name for path in first.release_dir.iterdir()) == [
        "LOINC_short_license.txt",
        "data.sqlite",
        "data.sqlite.zst",
        "diff.json",
        "license.txt",
        "loinc-panel-members.parquet",
        "loinc-specimens.parquet",
        "loinc-units.parquet",
        "loinc.parquet",
        "manifest.json",
        "validation.json",
    ]
    assert pl.read_parquet(first.release_dir / "loinc.parquet").height == 3
    assert pl.read_parquet(first.release_dir / "loinc-units.parquet").height == 4
    validation = json.loads((first.release_dir / "validation.json").read_text(encoding="utf-8"))
    assert validation["translationCoverage"] == {
        "numerator": 1,
        "denominator": 3,
        "ratio": "0.333333",
    }
    assert validation["statusCounts"] == {"ACTIVE": 2, "DEPRECATED": 1}

    revision = build_loinc_candidate(
        repo_root=tmp_path,
        core_source_path=fixture.core_archive,
        translation_source_path=fixture.translation_archive,
        output_root=tmp_path / ".work/build-one",
        build_revision=2,
        sequence=2,
        base_release_dir=first.release_dir,
        git_commit="d" * 40,
        created_at=datetime(2026, 9, 2, tzinfo=UTC),
    )
    diff = json.loads((revision.release_dir / "diff.json").read_text(encoding="utf-8"))
    assert diff["unchanged"] == 9
    assert diff["added"] == diff["removed"] == diff["modified"] == 0

    cli_result = CliRunner().invoke(
        app,
        [
            "build",
            "loinc-zh-cn",
            "--source",
            str(fixture.core_archive),
            "--translation-source",
            str(fixture.translation_archive),
            "--repo-root",
            str(tmp_path),
        ],
    )
    assert cli_result.exit_code == 0, cli_result.output
    assert "loinc-zh-cn/releases/fixture-1.r1/manifest.json" in cli_result.output


def test_candidate_supports_existing_runtime_query_shape(tmp_path: Path) -> None:
    fixture = fixture_repository(tmp_path)
    candidate = build_loinc_candidate(
        repo_root=tmp_path,
        core_source_path=fixture.core_archive,
        translation_source_path=fixture.translation_archive,
        output_root=tmp_path / ".work/dist",
        git_commit="d" * 40,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    connection = sqlite3.connect(f"file:{candidate.release_dir / 'data.sqlite'}?mode=ro", uri=True)
    try:
        assert connection.execute(
            "SELECT code, long_common_name, zh_display FROM loinc ORDER BY code LIMIT 2 OFFSET 1"
        ).fetchall() == [
            (
                "1001-8",
                "Synthetic analyte in Blood",
                "合成分析物:质量浓度:时间点:血液:定量",
            ),
            ("1002-6", "Synthetic cells in Blood by Automated count", None),
        ]
    finally:
        connection.close()


def test_combined_package_records_one_physical_source_with_two_roles(tmp_path: Path) -> None:
    fixture = fixture_repository(tmp_path, package_mode="combined")
    result = CliRunner().invoke(
        app,
        [
            "build",
            "loinc-zh-cn",
            "--source",
            str(fixture.core_archive),
            "--repo-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    manifest = json.loads(
        (tmp_path / "dist/loinc-zh-cn/releases/fixture-1.r1/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(manifest["sources"]) == 1
    assert manifest["sources"][0]["roles"] == ["core", "linguistic-variant"]


def test_combined_package_rejects_conflicting_physical_source_contract(tmp_path: Path) -> None:
    fixture = fixture_repository(tmp_path, package_mode="combined")
    contract_path = tmp_path / "datasets/loinc-zh-cn/dataset.yaml"
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    contract["source"]["linguistic_variant"]["sha256"] = "f" * 64
    contract_path.write_text(
        yaml.safe_dump(contract, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="physical source field sha256"):
        build_loinc_candidate(
            repo_root=tmp_path,
            core_source_path=fixture.core_archive,
            translation_source_path=None,
            output_root=tmp_path / ".work/dist",
            git_commit="d" * 40,
            created_at=datetime(2026, 9, 1, tzinfo=UTC),
        )


def test_source_hash_failure_does_not_publish_partial_candidate(tmp_path: Path) -> None:
    fixture = fixture_repository(tmp_path)
    fixture.core_archive.write_bytes(fixture.core_archive.read_bytes() + b"changed")
    output_root = tmp_path / ".work/failed-dist"

    with pytest.raises(SourceIntegrityError, match="source SHA256 mismatch"):
        build_loinc_candidate(
            repo_root=tmp_path,
            core_source_path=fixture.core_archive,
            translation_source_path=fixture.translation_archive,
            output_root=output_root,
            git_commit="d" * 40,
            created_at=datetime(2026, 9, 1, tzinfo=UTC),
        )

    releases_dir = output_root / "loinc-zh-cn/releases"
    assert not releases_dir.exists() or not any(releases_dir.iterdir())
