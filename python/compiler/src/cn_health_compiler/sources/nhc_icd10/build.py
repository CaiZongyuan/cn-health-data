"""End-to-end local Candidate build for NHC clinical diagnosis data."""

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from cn_health_compiler.core.candidate import (
    CandidateBuild,
    XlsxCandidateAdapter,
    build_xlsx_candidate,
)
from cn_health_compiler.core.workbook import WorkbookConfig, WorkbookInspection
from cn_health_compiler.sources.nhc_icd10.records import (
    DiagnosisRecord,
    iter_raw_diagnosis_rows,
    normalize_raw_diagnosis_row,
)
from cn_health_compiler.sources.nhc_icd10.sqlite import build_diagnosis_sqlite
from cn_health_compiler.sources.nhc_icd10.validation import (
    DiagnosisValidationReport,
    DiagnosisValidationRules,
)


def _records(
    inspection: WorkbookInspection,
    config: WorkbookConfig,
    source_version: str,
    source_sha256: str,
) -> Iterable[DiagnosisRecord]:
    return (
        normalize_raw_diagnosis_row(raw, source_version, source_sha256)
        for raw in iter_raw_diagnosis_rows(inspection, config)
    )


def _validation_payload(report: DiagnosisValidationReport) -> dict[str, object]:
    return {
        "recordCount": report.record_count,
        "uniqueCodes": report.unique_codes,
        "mainCodeCount": report.main_code_count,
        "additionalOnlyCount": report.additional_only_count,
        "pairedCodeCount": report.paired_code_count,
    }


_ADAPTER = XlsxCandidateAdapter(
    dataset_id="nhc-icd10-clinical",
    source_version_field="declared_version",
    table="diagnosis",
    iter_records=_records,
    load_rules=DiagnosisValidationRules.load_dataset,
    build_sqlite=build_diagnosis_sqlite,
    validation_payload=_validation_payload,
)


def build_diagnosis_candidate(
    repo_root: Path,
    source_path: Path,
    output_root: Path,
    *,
    build_revision: int = 1,
    sequence: int = 1,
    git_commit: str | None = None,
    created_at: datetime | None = None,
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
    )
