"""End-to-end local Candidate build for the NHSA drug dataset."""

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from cn_health_compiler.core.candidate import (
    CandidateBuild,
    XlsxCandidateAdapter,
    build_xlsx_candidate,
)
from cn_health_compiler.core.workbook import WorkbookConfig, WorkbookInspection
from cn_health_compiler.sources.nhsa_drugs.records import (
    DrugRecord,
    iter_raw_drug_rows,
    normalize_raw_drug_row,
)
from cn_health_compiler.sources.nhsa_drugs.sqlite import build_drug_sqlite
from cn_health_compiler.sources.nhsa_drugs.validation import (
    DrugValidationRules,
    ValidationReport,
)


def _records(
    inspection: WorkbookInspection,
    config: WorkbookConfig,
    source_version: str,
    source_sha256: str,
) -> Iterable[DrugRecord]:
    return (
        normalize_raw_drug_row(raw, source_version, source_sha256)
        for raw in iter_raw_drug_rows(inspection, config)
    )


def _validation_payload(report: ValidationReport) -> dict[str, object]:
    return {
        "recordCount": report.record_count,
        "uniqueCodes": report.unique_codes,
        "nullCounts": dict(report.null_counts),
        "marketStatusCounts": dict(report.market_status_counts),
    }


_ADAPTER = XlsxCandidateAdapter(
    dataset_id="nhsa-drugs",
    source_version_field="declared_data_as_of",
    table="drug",
    iter_records=_records,
    load_rules=DrugValidationRules.load_dataset,
    build_sqlite=build_drug_sqlite,
    validation_payload=_validation_payload,
)


def build_nhsa_drug_candidate(
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
    return build_xlsx_candidate(
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
