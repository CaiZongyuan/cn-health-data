"""End-to-end local Candidate build for Chinese name components."""

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
from cn_health_compiler.sources.names.records import (
    NameComponentRecord,
    parse_faker_name_components,
)
from cn_health_compiler.sources.names.sqlite import build_names_sqlite
from cn_health_compiler.sources.names.validation import (
    NamesValidationReport,
    NamesValidationRules,
)


def _records(snapshot: SourceSnapshot, source_version: str) -> Iterable[NameComponentRecord]:
    return parse_faker_name_components(
        snapshot.path,
        source_version=source_version,
        source_sha256=snapshot.sha256,
    )


def _rules(path: Path) -> NamesValidationRules:
    return NamesValidationRules.model_validate(load_yaml_mapping(path)["validation"])


def _validation_payload(report: NamesValidationReport) -> dict[str, object]:
    return report.model_dump(mode="json")


_ADAPTER = FileCandidateAdapter(
    dataset_id="names-cn",
    source_version_field="declared_version",
    table="name_component",
    iter_records=_records,
    load_rules=_rules,
    build_sqlite=build_names_sqlite,
    validation_payload=_validation_payload,
)


def build_names_candidate(
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
