"""End-to-end Candidate build for the project-authored laboratory catalog."""

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
from cn_health_compiler.sources.laboratory.records import (
    LaboratoryConceptRecord,
    iter_laboratory_records,
)
from cn_health_compiler.sources.laboratory.sqlite import build_laboratory_sqlite
from cn_health_compiler.sources.laboratory.validation import (
    LaboratoryValidationReport,
    LaboratoryValidationRules,
)


def _records(snapshot: SourceSnapshot, source_version: str) -> Iterable[LaboratoryConceptRecord]:
    return iter_laboratory_records(
        snapshot.path,
        source_version=source_version,
        source_sha256=snapshot.sha256,
    )


def _rules(path: Path) -> LaboratoryValidationRules:
    return LaboratoryValidationRules.model_validate(load_yaml_mapping(path)["validation"])


def _validation_payload(report: LaboratoryValidationReport) -> dict[str, object]:
    return report.model_dump(mode="json")


_ADAPTER = FileCandidateAdapter(
    dataset_id="laboratory-cn",
    source_version_field="declared_version",
    table="laboratory_concept",
    iter_records=_records,
    load_rules=_rules,
    build_sqlite=build_laboratory_sqlite,
    validation_payload=_validation_payload,
    excluded_diff_fields=("source_row", "source_version", "source_sha256"),
)


def build_laboratory_candidate(
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
