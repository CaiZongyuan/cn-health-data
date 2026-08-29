"""Compatibility exports for the NHSA drug workbook contract."""

from cn_health_compiler.core.workbook import (
    WorkbookConfig,
    WorkbookContainerConfig,
    WorkbookContractError,
    WorkbookInspection,
    WorkbookSheetConfig,
    WorkbookSourceConfig,
    WorkbookStructureConfig,
    inspect_workbook,
)

NhsaDrugWorkbookConfig = WorkbookConfig

__all__ = [
    "NhsaDrugWorkbookConfig",
    "WorkbookContainerConfig",
    "WorkbookContractError",
    "WorkbookInspection",
    "WorkbookSheetConfig",
    "WorkbookSourceConfig",
    "WorkbookStructureConfig",
    "inspect_workbook",
]
