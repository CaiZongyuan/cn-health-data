"""End-to-end local Candidate build for Chinese aggregate population data."""

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from cn_health_compiler.core.candidate import (
    CandidateBuild,
    FileCandidateAdapter,
    build_file_candidate,
)
from cn_health_compiler.core.dataset import load_yaml_mapping
from cn_health_compiler.core.source import SourceSnapshot
from cn_health_compiler.sources.population.records import (
    PopulationAgeSexRecord,
    iter_wpp_age_sex_records,
)
from cn_health_compiler.sources.population.sqlite import build_population_sqlite
from cn_health_compiler.sources.population.validation import (
    PopulationValidationReport,
    PopulationValidationRules,
)


def _records(snapshot: SourceSnapshot, source_version: str) -> Iterable[PopulationAgeSexRecord]:
    return iter_wpp_age_sex_records(
        snapshot.path,
        source_version=source_version,
        source_sha256=snapshot.sha256,
    )


def _rules(path: Path) -> PopulationValidationRules:
    return PopulationValidationRules.model_validate(load_yaml_mapping(path)["validation"])


def _validation_payload(report: PopulationValidationReport) -> dict[str, object]:
    return report.model_dump(mode="json")


_ADAPTER = FileCandidateAdapter(
    dataset_id="population-cn",
    source_version_field="declared_version",
    table="population_age_sex",
    iter_records=_records,
    load_rules=_rules,
    build_sqlite=build_population_sqlite,
    validation_payload=_validation_payload,
    excluded_diff_fields=("source_row", "source_version", "source_sha256"),
)


def build_population_candidate(
    repo_root: Path,
    source_path: Path,
    output_root: Path,
    *,
    build_revision: int = 1,
    sequence: int = 1,
    git_commit: str | None = None,
    created_at: datetime | None = None,
    base_release_dir: Path | None = None,
) -> CandidateBuild:
    return build_file_candidate(
        _ADAPTER,
        repo_root,
        source_path,
        output_root,
        build_revision=build_revision,
        sequence=sequence,
        git_commit=git_commit,
        created_at=created_at,
        base_release_dir=base_release_dir,
    )
