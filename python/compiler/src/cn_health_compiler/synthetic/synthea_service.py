"""Bounded internal HTTP service for the cn-health Synthea Bundle localizer."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cn_health_compiler.synthetic.synthea_localizer import (
    LocalizedSyntheaBundle,
    SyntheaBundleLocalizer,
    SyntheaLocalizationError,
)
from cn_health_compiler.synthetic.translation.catalog import (
    CatalogDisplayLookup,
    ReviewStatus,
    load_catalog,
)
from cn_health_compiler.synthetic.translation.projector import TranslationGap, project_bundle

_MAX_BODY_BYTES = 64 * 1024 * 1024
_MAX_TRANSLATION_GAPS = 100
_RUNTIME_REVIEW_STATUSES: frozenset[ReviewStatus] = frozenset(
    {"approved", "human-reviewed", "machine-checked"}
)


@dataclass(frozen=True, slots=True)
class LocalizedSyntheaProjection:
    bundle: dict[str, Any]
    gaps: tuple[TranslationGap, ...]
    profile_content_hash: str
    profile_id: str


class SyntheaClinicalDisplayLocalizer:
    """Compose identity localization with fail-closed Chinese display projection."""

    def __init__(
        self,
        identity_localizer: _IdentityLocalizer,
        *,
        catalog_path: Path,
        expected_catalog_sha256: str,
        projection_id: str,
    ) -> None:
        if not projection_id:
            raise ValueError("clinical display projection ID must not be empty")
        if re.fullmatch(r"[0-9a-f]{64}", expected_catalog_sha256) is None:
            raise ValueError("expected catalog SHA-256 must be 64 lowercase hexadecimal digits")
        catalog = load_catalog(catalog_path)
        if catalog.sha256 != expected_catalog_sha256:
            raise SyntheaLocalizationError("Synthea translation catalog SHA-256 mismatch")
        self._identity_localizer = identity_localizer
        self._lookup = CatalogDisplayLookup(
            catalog, accepted_review_statuses=_RUNTIME_REVIEW_STATUSES
        )
        self._projection_id = projection_id
        self._catalog_sha256 = expected_catalog_sha256
        self._provenance = identity_localizer.provenance
        self._provenance["clinicalDisplay"] = {
            "projectionId": projection_id,
            "catalogSha256": expected_catalog_sha256,
            "language": "zh-CN",
            "recordCount": len(catalog.records),
            "reviewMode": "experimental-preview",
        }

    @property
    def provenance(self) -> dict[str, object]:
        return copy.deepcopy(self._provenance)

    def localize(
        self, raw_bundle: dict[str, Any], *, seed: str
    ) -> LocalizedSyntheaProjection:
        localized = self._identity_localizer.localize(raw_bundle, seed=seed)
        projected = project_bundle(
            localized.bundle,
            self._lookup,
            release_id=self._projection_id,
            content_hash=self._catalog_sha256,
        )
        return LocalizedSyntheaProjection(
            bundle=projected.bundle,
            gaps=projected.gaps,
            profile_content_hash=localized.profile_content_hash,
            profile_id=localized.profile_id,
        )


class _LocalizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundle: dict[str, Any]
    seed: str = Field(min_length=1, max_length=256)


class _IdentityLocalizer(Protocol):
    @property
    def provenance(self) -> dict[str, object]: ...

    def localize(
        self, raw_bundle: dict[str, Any], *, seed: str
    ) -> LocalizedSyntheaBundle: ...


class _ServiceLocalizer(Protocol):
    @property
    def provenance(self) -> dict[str, object]: ...

    def localize(
        self, raw_bundle: dict[str, Any], *, seed: str
    ) -> LocalizedSyntheaBundle | LocalizedSyntheaProjection: ...


def _translation_warnings(gaps: tuple[TranslationGap, ...]) -> list[dict[str, object]]:
    if not gaps:
        return []
    return [{
        "code": "TRANSLATION_GAP",
        "message": "The Synthea Bundle contains untranslated clinical displays",
        "gapCount": len(gaps),
        "gaps": [
            {
                "resourceType": gap.resource_type,
                "resourceId": gap.resource_id,
                "path": gap.path,
                "system": gap.system,
                "version": gap.version,
                "code": gap.code,
                "sourceDisplay": gap.source_display,
            }
            for gap in gaps[:_MAX_TRANSLATION_GAPS]
        ],
        "truncated": len(gaps) > _MAX_TRANSLATION_GAPS,
    }]


class _SyntheaServiceHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    _localizer: _ServiceLocalizer

    def do_GET(self) -> None:
        if self.path != "/health":
            self._error(HTTPStatus.NOT_FOUND, "NOT_FOUND", "The endpoint was not found")
            return
        self._json(
            HTTPStatus.OK,
            {"status": "ok", "localization": self._localizer.provenance},
        )

    def do_POST(self) -> None:
        if self.path != "/v1/localize":
            self._error(HTTPStatus.NOT_FOUND, "NOT_FOUND", "The endpoint was not found")
            return
        content_type = self.headers.get("content-type", "").lower()
        if not content_type.startswith("application/json"):
            self._error(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                "CONTENT_TYPE_INVALID",
                "application/json is required",
            )
            return
        try:
            content_length = int(self.headers.get("content-length", ""))
        except ValueError:
            self._error(
                HTTPStatus.LENGTH_REQUIRED,
                "CONTENT_LENGTH_REQUIRED",
                "Content-Length is required",
            )
            return
        if content_length < 0 or content_length > _MAX_BODY_BYTES:
            self._error(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "REQUEST_TOO_LARGE",
                "The request is too large",
            )
            return
        try:
            request = _LocalizationRequest.model_validate_json(self.rfile.read(content_length))
            localized = self._localizer.localize(request.bundle, seed=request.seed)
        except (ValidationError, json.JSONDecodeError):
            self._error(
                HTTPStatus.BAD_REQUEST,
                "REQUEST_INVALID",
                "The localization request is invalid",
            )
            return
        except SyntheaLocalizationError:
            self._error(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "BUNDLE_INVALID",
                "The Synthea Bundle cannot be localized",
            )
            return
        gaps = localized.gaps if isinstance(localized, LocalizedSyntheaProjection) else ()
        self._json(HTTPStatus.OK, {
            "bundle": localized.bundle,
            "metadata": self._localizer.provenance,
            "warnings": _translation_warnings(gaps),
        })

    def do_PUT(self) -> None:
        self._method_not_allowed()

    def do_DELETE(self) -> None:
        self._method_not_allowed()

    def do_PATCH(self) -> None:
        self._method_not_allowed()

    def log_message(self, format: str, *args: object) -> None:
        return

    def _method_not_allowed(self) -> None:
        self._error(
            HTTPStatus.METHOD_NOT_ALLOWED,
            "METHOD_NOT_ALLOWED",
            "The HTTP method is not allowed",
        )

    def _error(self, status: HTTPStatus, code: str, message: str) -> None:
        self._json(status, {"error": {"code": code, "message": message}})

    def _json(self, status: HTTPStatus, value: object) -> None:
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
        if len(body) > _MAX_BODY_BYTES:
            self._error(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "RESPONSE_TOO_LARGE",
                "The localized Bundle is too large",
            )
            return
        self.send_response(status.value)
        self.send_header("content-length", str(len(body)))
        self.send_header("content-type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)


def create_synthea_service_server(
    localizer: _ServiceLocalizer,
    *,
    host: str,
    port: int,
) -> ThreadingHTTPServer:
    class BoundSyntheaServiceHandler(_SyntheaServiceHandler):
        _localizer = localizer

    return ThreadingHTTPServer((host, port), BoundSyntheaServiceHandler)


def _path_argument(parser: argparse.ArgumentParser, name: str, environment: str) -> None:
    default = os.environ.get(environment)
    parser.add_argument(name, default=default, required=default is None, type=Path)


def _sha256_argument(value: str) -> str:
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise argparse.ArgumentTypeError("must be 64 lowercase hexadecimal digits")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Serve deterministic cn-health Synthea localization"
    )
    _path_argument(parser, "--profile", "CN_HEALTH_SYNTHEA_PROFILE_PATH")
    _path_argument(parser, "--names-release", "CN_HEALTH_NAMES_RELEASE_PATH")
    _path_argument(parser, "--geography-release", "CN_HEALTH_GEOGRAPHY_RELEASE_PATH")
    _path_argument(parser, "--population-release", "CN_HEALTH_POPULATION_RELEASE_PATH")
    _path_argument(
        parser,
        "--translation-catalog",
        "CN_HEALTH_SYNTHEA_TRANSLATION_CATALOG_PATH",
    )
    parser.add_argument(
        "--clinical-display-projection-id",
        default=os.environ.get("CN_HEALTH_SYNTHEA_CLINICAL_DISPLAY_PROJECTION_ID"),
        required=os.environ.get("CN_HEALTH_SYNTHEA_CLINICAL_DISPLAY_PROJECTION_ID") is None,
    )
    expected_catalog_sha256 = os.environ.get(
        "CN_HEALTH_SYNTHEA_EXPECTED_CATALOG_SHA256"
    )
    parser.add_argument(
        "--expected-catalog-sha256",
        default=expected_catalog_sha256,
        required=expected_catalog_sha256 is None,
        type=_sha256_argument,
    )
    parser.add_argument("--host", default=os.environ.get("CN_HEALTH_LOCALIZER_HOST", "0.0.0.0"))
    parser.add_argument(
        "--port",
        default=int(os.environ.get("CN_HEALTH_LOCALIZER_PORT", "51879")),
        type=int,
    )
    arguments = parser.parse_args()
    identity_localizer = SyntheaBundleLocalizer(
        profile_dir=arguments.profile,
        names_release_dir=arguments.names_release,
        geography_release_dir=arguments.geography_release,
        population_release_dir=arguments.population_release,
    )
    localizer = SyntheaClinicalDisplayLocalizer(
        identity_localizer,
        catalog_path=arguments.translation_catalog,
        expected_catalog_sha256=arguments.expected_catalog_sha256,
        projection_id=arguments.clinical_display_projection_id,
    )
    server = create_synthea_service_server(localizer, host=arguments.host, port=arguments.port)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
