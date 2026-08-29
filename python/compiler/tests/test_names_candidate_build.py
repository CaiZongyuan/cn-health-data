import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import yaml
import zstandard
from cn_health_compiler.cli import app
from cn_health_compiler.sources.names.build import build_names_candidate
from jsonschema import Draft202012Validator, FormatChecker
from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[3]


def _fixture_repository(root: Path) -> Path:
    dataset_dir = root / "datasets/names-cn"
    schema_dir = root / "schemas"
    source_dir = root / "tmp"
    dataset_dir.mkdir(parents=True)
    schema_dir.mkdir()
    source_dir.mkdir()
    shutil.copyfile(REPO_ROOT / "datasets/names-cn/schema.sql", dataset_dir / "schema.sql")
    shutil.copyfile(REPO_ROOT / "schemas/manifest.schema.json", schema_dir / "manifest.schema.json")
    (root / "uv.lock").write_text("fixture lock\n", encoding="utf-8")
    (dataset_dir / "layout.yaml").write_text("version: 1\n", encoding="utf-8")
    source = source_dir / "faker-person.py"
    source.write_text(
        "from collections import OrderedDict\n\n"
        "class Provider:\n"
        '    first_names_male = ["伟"]\n'
        '    first_names_female = ["芳"]\n'
        '    last_names = OrderedDict((("王", 7.17), ("欧阳", 0.068)))\n',
        encoding="utf-8",
    )
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    contract = {
        "id": "names-cn",
        "title": "测试中文姓名组件",
        "description": "Synthetic Faker provider fixture.",
        "status": "experimental",
        "authority": {
            "name": "Faker",
            "role": "software-data-source",
            "verification": "fixture",
        },
        "source": {
            "type": "python-source",
            "acquisition": "manual-local",
            "path_hint": "tmp/faker-person.py",
            "source_url": "https://example.test/faker-person.py",
            "declared_version": "40.37.0",
            "upstream_commit": "e" * 40,
            "sha256": source_sha256,
            "size_bytes": source.stat().st_size,
            "upstream_sync": False,
        },
        "versioning": {"strategy": "upstream-package-version"},
        "output": {"primary": "sqlite", "optional": ["parquet"]},
        "runtime": {"searchable": False, "minimum_sqlite_version": "3.34.0"},
        "rights": {"redistribution": "normalized-only", "release_eligible": False},
        "validation": {
            "min_surname_count": 2,
            "min_male_given_count": 1,
            "min_female_given_count": 1,
        },
    }
    (dataset_dir / "dataset.yaml").write_text(
        yaml.safe_dump(contract, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (root / ".gitignore").write_text("tmp/\n.work/\ndist/\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main", root], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", root, "config", "user.email", "fixture@example.invalid"], check=True
    )
    subprocess.run(["git", "-C", root, "config", "user.name", "Fixture"], check=True)
    subprocess.run(["git", "-C", root, "add", "."], check=True)
    subprocess.run(["git", "-C", root, "commit", "-m", "fixture"], check=True, capture_output=True)
    return source


def test_build_names_candidate_packages_and_diffs_components(tmp_path: Path) -> None:
    source = _fixture_repository(tmp_path)

    result = build_names_candidate(
        repo_root=tmp_path,
        source_path=source,
        output_root=tmp_path / "dist",
        git_commit="d" * 40,
        created_at=datetime(2026, 8, 29, tzinfo=UTC),
    )

    release = result.release_dir
    assert sorted(path.name for path in release.iterdir()) == [
        "data.parquet",
        "data.sqlite",
        "data.sqlite.zst",
        "diff.json",
        "manifest.json",
        "validation.json",
    ]
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    schema = json.loads((tmp_path / "schemas/manifest.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(manifest)
    assert manifest["release"]["id"] == "names-cn@40.37.0.r1"
    assert manifest["canonical"]["recordCount"] == 4
    assert manifest["sources"][0]["recordCount"] == 4
    assert pl.read_parquet(release / "data.parquet").height == 4
    sqlite_bytes = (release / "data.sqlite").read_bytes()
    assert (
        zstandard.ZstdDecompressor().decompress((release / "data.sqlite.zst").read_bytes())
        == sqlite_bytes
    )

    revision = build_names_candidate(
        repo_root=tmp_path,
        source_path=source,
        output_root=tmp_path / "dist",
        build_revision=2,
        sequence=2,
        base_release_dir=release,
        git_commit="d" * 40,
        created_at=datetime(2026, 8, 30, tzinfo=UTC),
    )
    revision_manifest = json.loads(revision.manifest_path.read_text(encoding="utf-8"))
    revision_diff = json.loads((revision.release_dir / "diff.json").read_text(encoding="utf-8"))
    assert revision_manifest["release"]["supersedes"] == "names-cn@40.37.0.r1"
    assert revision_diff["unchanged"] == 4


def test_build_command_accepts_names_source(tmp_path: Path) -> None:
    source = _fixture_repository(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "build",
            "names-cn",
            "--source",
            str(source),
            "--repo-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "names-cn/releases/40.37.0.r1/manifest.json" in result.output
