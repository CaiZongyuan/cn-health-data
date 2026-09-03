"""Stage and start the self-contained Synthea localization runtime."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from cn_health_compiler.core.source import hash_file
from cn_health_compiler.synthetic.translation.catalog import load_catalog

_DATASET_DIRECTORIES = {
    "geography-cn": "geography",
    "names-cn": "names",
    "population-cn": "population",
}


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(item.capitalize() for item in tail)


class SyntheaRuntimeError(ValueError):
    """Raised when runtime assets do not match their release manifest."""


class _Profile(BaseModel):
    model_config = ConfigDict(alias_generator=lambda value: _camel(value), extra="forbid")

    profile_id: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_path: str = Field(min_length=1)


class _Dataset(BaseModel):
    model_config = ConfigDict(alias_generator=lambda value: _camel(value), extra="forbid")

    dataset_id: Literal["geography-cn", "names-cn", "population-cn"]
    release_id: str = Field(min_length=1)
    canonical_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sqlite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_path: str = Field(min_length=1)


class _ClinicalDisplay(BaseModel):
    model_config = ConfigDict(alias_generator=lambda value: _camel(value), extra="forbid")

    projection_id: str = Field(min_length=1)
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_source_path: str = Field(min_length=1)
    policy_source_path: str = Field(min_length=1)
    record_count: int = Field(ge=1)
    review_mode: Literal["experimental-preview"]


class _Image(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository: str = Field(pattern=r"^ghcr\.io/[a-z0-9._/-]+$")
    tag: str = Field(pattern=r"^[A-Za-z0-9._-]+$")
    platforms: tuple[Literal["linux/amd64", "linux/arm64"], ...] = Field(min_length=1)


class SyntheaRuntimeManifest(BaseModel):
    model_config = ConfigDict(alias_generator=lambda value: _camel(value), extra="forbid")

    schema_version: Literal[1]
    runtime_id: str = Field(min_length=1)
    release_tag: str = Field(pattern=r"^synthea-cn-[A-Za-z0-9._-]+$")
    synthea_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    profile: _Profile
    datasets: tuple[_Dataset, ...] = Field(min_length=3, max_length=3)
    clinical_display: _ClinicalDisplay
    image: _Image

    @model_validator(mode="after")
    def validate_runtime_identity(self) -> SyntheaRuntimeManifest:
        dataset_ids = [item.dataset_id for item in self.datasets]
        if set(dataset_ids) != set(_DATASET_DIRECTORIES) or len(dataset_ids) != len(
            set(dataset_ids)
        ):
            raise ValueError("runtime must contain each identity Dataset exactly once")
        if self.release_tag.removeprefix("synthea-cn-") != self.image.tag:
            raise ValueError("release tag and image tag do not agree")
        return self
def load_synthea_runtime_manifest(path: Path) -> SyntheaRuntimeManifest:
    try:
        return SyntheaRuntimeManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as error:
        raise SyntheaRuntimeError("Synthea runtime Manifest is invalid") from error


def _source_path(repository_root: Path, value: str) -> Path:
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != value:
        raise SyntheaRuntimeError(f"Synthea runtime contains unsafe source path: {value}")
    path = repository_root.joinpath(*relative.parts).resolve(strict=True)
    if repository_root.resolve() not in path.parents:
        raise SyntheaRuntimeError(f"Synthea runtime source escapes repository: {value}")
    return path


def _stage_dataset(dataset: _Dataset, repository_root: Path, output_root: Path) -> None:
    import zstandard

    source = _source_path(repository_root, dataset.source_path)
    try:
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        compressed = next(
            artifact
            for artifact in manifest["artifacts"]
            if artifact["name"] == "data.sqlite.zst"
        )
    except (KeyError, OSError, StopIteration, TypeError, ValueError) as error:
        raise SyntheaRuntimeError(f"{dataset.dataset_id} distribution is invalid") from error
    if (
        manifest["dataset"]["id"] != dataset.dataset_id
        or manifest["release"]["id"] != dataset.release_id
        or manifest["canonical"]["sha256"] != dataset.canonical_sha256
        or compressed.get("compression") != "zstd"
        or compressed.get("uncompressedName") != "data.sqlite"
        or compressed.get("uncompressedSha256") != dataset.sqlite_sha256
    ):
        raise SyntheaRuntimeError(f"{dataset.dataset_id} distribution identity mismatch")
    compressed_path = source / compressed["url"]
    if hash_file(compressed_path) != (compressed["sha256"], compressed["sizeBytes"]):
        raise SyntheaRuntimeError(f"{dataset.dataset_id} compressed artifact mismatch")

    destination = output_root / _DATASET_DIRECTORIES[dataset.dataset_id]
    destination.mkdir(parents=True)
    shutil.copy2(source / "manifest.json", destination / "manifest.json")
    database_path = destination / "data.sqlite"
    with compressed_path.open("rb") as compressed_stream, database_path.open("wb") as database:
        zstandard.ZstdDecompressor().copy_stream(compressed_stream, database)
    if hash_file(database_path) != (
        compressed["uncompressedSha256"],
        compressed["uncompressedSizeBytes"],
    ):
        raise SyntheaRuntimeError(f"{dataset.dataset_id} SQLite artifact mismatch")


def stage_synthea_runtime(manifest_path: Path, repository_root: Path, output_root: Path) -> None:
    manifest = load_synthea_runtime_manifest(manifest_path)
    if output_root.exists() and any(output_root.iterdir()):
        raise SyntheaRuntimeError("Synthea runtime output must be empty")
    output_root.mkdir(parents=True, exist_ok=True)

    profile_source = _source_path(repository_root, manifest.profile.source_path)
    try:
        profile_manifest = json.loads(
            (profile_source / "manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, TypeError, ValueError) as error:
        raise SyntheaRuntimeError("Synthea profile Manifest is invalid") from error
    if (
        profile_manifest.get("profileId") != manifest.profile.profile_id
        or profile_manifest.get("contentHash") != manifest.profile.content_hash
        or profile_manifest.get("supportedSyntheaCommit") != manifest.synthea_commit
    ):
        raise SyntheaRuntimeError("Synthea profile identity mismatch")
    shutil.copytree(profile_source, output_root / "profile")

    for dataset in manifest.datasets:
        _stage_dataset(dataset, repository_root, output_root)

    catalog_source = _source_path(
        repository_root, manifest.clinical_display.catalog_source_path
    )
    catalog = load_catalog(catalog_source)
    if (
        catalog.sha256 != manifest.clinical_display.catalog_sha256
        or len(catalog.records) != manifest.clinical_display.record_count
    ):
        raise SyntheaRuntimeError("Synthea translation catalog mismatch")
    translation_root = output_root / "translation"
    translation_root.mkdir()
    shutil.copy2(catalog_source, translation_root / "catalog.jsonl")
    shutil.copy2(
        _source_path(repository_root, manifest.clinical_display.policy_source_path),
        translation_root / "translation.yaml",
    )
    shutil.copy2(manifest_path, output_root / "runtime-manifest.json")


def synthea_service_arguments(runtime_root: Path) -> list[str]:
    manifest = load_synthea_runtime_manifest(runtime_root / "runtime-manifest.json")
    return [
        "--profile",
        str(runtime_root / "profile"),
        "--geography-release",
        str(runtime_root / _DATASET_DIRECTORIES["geography-cn"]),
        "--names-release",
        str(runtime_root / _DATASET_DIRECTORIES["names-cn"]),
        "--population-release",
        str(runtime_root / _DATASET_DIRECTORIES["population-cn"]),
        "--translation-catalog",
        str(runtime_root / "translation/catalog.jsonl"),
        "--clinical-display-projection-id",
        manifest.clinical_display.projection_id,
        "--expected-catalog-sha256",
        manifest.clinical_display.catalog_sha256,
    ]


def main() -> None:
    if len(sys.argv) != 1:
        raise SystemExit("cn-health-synthea-runtime does not accept arguments")
    from cn_health_compiler.synthetic.synthea_service import main as service_main

    sys.argv = [
        "cn-health-synthea-service",
        *synthea_service_arguments(Path("/opt/cn-health/runtime")),
    ]
    service_main()
