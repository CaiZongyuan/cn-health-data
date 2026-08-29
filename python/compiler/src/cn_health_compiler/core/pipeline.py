"""Compiler pipeline stage definitions."""

from enum import StrEnum


class PipelineStage(StrEnum):
    """Stable names for build pipeline stages."""

    RESOLVE_SOURCE = "resolve-source"
    SNAPSHOT = "snapshot"
    INSPECT = "inspect"
    EXTRACT = "extract"
    NORMALIZE = "normalize"
    VALIDATE = "validate"
    DIFF = "diff"
    BUILD_SQLITE = "build-sqlite"
    PACKAGE = "package"
