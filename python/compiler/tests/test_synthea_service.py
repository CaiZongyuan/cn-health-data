import json
import threading
from contextlib import closing
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest
from cn_health_compiler.synthetic.synthea_localizer import (
    LocalizedSyntheaBundle,
    SyntheaLocalizationError,
)
from cn_health_compiler.synthetic.synthea_service import (
    SyntheaClinicalDisplayLocalizer,
    create_synthea_service_server,
)
from cn_health_compiler.synthetic.translation.catalog import (
    TranslationRecord,
    load_catalog,
    translation_id,
)


class _StubLocalizer:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], str]] = []
        self.provenance: dict[str, object] = {
            "dependencies": [
                {
                    "canonicalSha256": "a" * 64,
                    "datasetId": "geography-cn",
                    "releaseId": "geography-cn@test.r1",
                    "sqliteSha256": "b" * 64,
                },
                {
                    "canonicalSha256": "c" * 64,
                    "datasetId": "names-cn",
                    "releaseId": "names-cn@test.r1",
                    "sqliteSha256": "d" * 64,
                },
                {
                    "canonicalSha256": "e" * 64,
                    "datasetId": "population-cn",
                    "releaseId": "population-cn@test.r1",
                    "sqliteSha256": "f" * 64,
                },
            ],
            "identityAlgorithm": "synthetic-identity-v1",
            "profileContentHash": "1" * 64,
            "profileId": "synthea-cn@test.r1",
            "syntheaCommit": "2" * 40,
        }

    def localize(self, raw_bundle: dict[str, Any], *, seed: str) -> LocalizedSyntheaBundle:
        self.calls.append((raw_bundle, seed))
        return LocalizedSyntheaBundle(
            bundle={
                **raw_bundle,
                "meta": {
                    "tag": [{
                        "code": "synthea-cn@test.r1",
                        "display": "1" * 64,
                        "system": "urn:cn-health-data:synthea-profile",
                    }]
                },
            },
            profile_content_hash="1" * 64,
            profile_id="synthea-cn@test.r1",
        )


def _write_catalog(path: Path, *, code: str = "1234-5", display: str = "血压") -> None:
    record = TranslationRecord(
        translation_id=translation_id("LOINC", None, code),
        source_system="LOINC",
        source_version=None,
        source_code=code,
        source_display="Blood pressure",
        display_zh=display,
        domains=("observation",),
        method="machine-checked",
        review_status="machine-checked",
        needs_review=False,
        provenance_id="test",
    )
    path.write_text(record.model_dump_json(by_alias=True) + "\n", encoding="utf-8")


def _request(
    connection: HTTPConnection,
    method: str,
    path: str,
    body: object | None = None,
    *,
    content_type: str = "application/json",
) -> tuple[int, dict[str, Any]]:
    payload = None if body is None else json.dumps(body).encode()
    headers = {} if payload is None else {"content-type": content_type}
    connection.request(method, path, body=payload, headers=headers)
    response = connection.getresponse()
    return response.status, json.loads(response.read())


def test_synthea_service_exposes_bounded_health_and_localization_contract() -> None:
    localizer = _StubLocalizer()
    server = create_synthea_service_server(localizer, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with closing(HTTPConnection("127.0.0.1", server.server_port, timeout=2)) as connection:
            status, health = _request(connection, "GET", "/health")
            assert status == 200
            assert health == {"status": "ok", "localization": localizer.provenance}

            bundle = {
                "entry": [{
                    "resource": {
                        "birthDate": "1988-03-16",
                        "gender": "female",
                        "id": "patient-1",
                        "resourceType": "Patient",
                    }
                }],
                "resourceType": "Bundle",
                "type": "collection",
            }
            status, localized = _request(
                connection,
                "POST",
                "/v1/localize",
                {"bundle": bundle, "seed": "4242:7331:0"},
            )
            assert status == 200
            assert localized == {
                "bundle": {
                    **bundle,
                    "meta": {
                        "tag": [{
                            "code": "synthea-cn@test.r1",
                            "display": "1" * 64,
                            "system": "urn:cn-health-data:synthea-profile",
                        }]
                    },
                },
                "metadata": localizer.provenance,
                "warnings": [],
            }
            assert localizer.calls == [(bundle, "4242:7331:0")]

            status, error = _request(
                connection,
                "POST",
                "/v1/localize",
                {"bundle": bundle, "extra": True, "seed": "seed"},
            )
            assert status == 400
            assert error == {
                "error": {
                    "code": "REQUEST_INVALID",
                    "message": "The localization request is invalid",
                }
            }

            status, error = _request(
                connection,
                "POST",
                "/v1/localize",
                {"bundle": bundle, "seed": "seed"},
                content_type="text/plain",
            )
            assert status == 415
            assert error["error"]["code"] == "CONTENT_TYPE_INVALID"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_synthea_service_docker_image_is_self_contained() -> None:
    repository = Path(__file__).parents[3]
    dockerfile = (repository / "Dockerfile.synthea-localizer").read_text(encoding="utf-8")
    dockerignore = (repository / ".dockerignore").read_text(encoding="utf-8")

    assert "USER 10001:10001" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "COPY LICENSE /opt/licenses/CN-HEALTH-DATA-LICENSE" in dockerfile
    assert "COPY DATA-NOTICE.md /opt/licenses/CN-HEALTH-DATA-NOTICE" in dockerfile
    assert "pip wheel --no-deps" in dockerfile
    assert '"pydantic>=2.11,<3"' in dockerfile
    assert '"rfc8785>=0.1.4,<1"' in dockerfile
    assert "distribution/profiles/synthea-cn/2026-08-29.r4" in dockerfile
    assert "distribution/releases/geography-cn/2026-08-29.r2" in dockerfile
    assert "distribution/releases/names-cn/40.37.0.r2" in dockerfile
    assert "distribution/releases/population-cn/WPP2024.r2" in dockerfile
    assert "translations/synthea-zh-cn/catalog.jsonl" in dockerfile
    assert "CN_HEALTH_SYNTHEA_PROFILE_PATH=/opt/cn-health/runtime/profile" in dockerfile
    assert "CN_HEALTH_GEOGRAPHY_RELEASE_PATH=/opt/cn-health/runtime/geography" in dockerfile
    assert "CN_HEALTH_NAMES_RELEASE_PATH=/opt/cn-health/runtime/names" in dockerfile
    assert "CN_HEALTH_POPULATION_RELEASE_PATH=/opt/cn-health/runtime/population" in dockerfile
    assert "org.cn-health-data.synthea.review-mode=experimental-preview" in dockerfile
    assert "COPY tmp" not in dockerfile
    assert '"pyyaml>=6.0.2,<7"' in dockerfile
    assert "pydantic pyyaml rfc8785" in dockerfile
    assert "CN_HEALTH_SYNTHEA_EXPECTED_CATALOG_SHA256" in dockerfile
    assert "dist/" in dockerignore
    assert "tmp/" in dockerignore


def test_synthea_runtime_release_builds_and_publishes_verified_image() -> None:
    repository = Path(__file__).parents[3]
    workflow = (repository / ".github/workflows/synthea-runtime.yml").read_text(
        encoding="utf-8"
    )

    assert "ghcr.io/caizongyuan/cn-health-synthea-localizer" in workflow
    assert "linux/amd64,linux/arm64" in workflow
    assert "packages: write" in workflow
    assert "docker build" in workflow
    assert "--read-only" in workflow
    assert "/v1/localize" in workflow
    assert "push: true" in workflow
    assert "sbom: true" in workflow
    assert "attest-build-provenance" in workflow


def test_runtime_projects_reviewed_displays_removes_claims_and_reports_provenance(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog.jsonl"
    _write_catalog(catalog_path)
    expected_catalog_sha256 = load_catalog(catalog_path).sha256
    localizer = SyntheaClinicalDisplayLocalizer(
        _StubLocalizer(),
        catalog_path=catalog_path,
        expected_catalog_sha256=expected_catalog_sha256,
        projection_id="synthea-zh-cn@test.r1",
    )
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "patient-1",
                    "birthDate": "1988-03-16",
                    "gender": "female",
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": "obs-1",
                    "code": {
                        "coding": [{
                            "system": "http://loinc.org",
                            "code": "1234-5",
                            "display": "Blood pressure",
                        }]
                    },
                }
            },
            {"resource": {"resourceType": "Claim", "id": "claim-1"}},
            {"resource": {"resourceType": "ExplanationOfBenefit", "id": "eob-1"}},
        ],
    }
    server = create_synthea_service_server(localizer, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with closing(HTTPConnection("127.0.0.1", server.server_port, timeout=2)) as connection:
            status, health = _request(connection, "GET", "/health")
            assert status == 200
            clinical_display = health["localization"]["clinicalDisplay"]
            assert clinical_display == {
                "projectionId": "synthea-zh-cn@test.r1",
                "catalogSha256": expected_catalog_sha256,
                "language": "zh-CN",
                "recordCount": 1,
                "reviewMode": "experimental-preview",
            }

            status, response = _request(
                connection, "POST", "/v1/localize", {"bundle": bundle, "seed": "seed"}
            )
            assert status == 200
            assert response["metadata"] == localizer.provenance
            assert response["warnings"] == []
            resources = [entry["resource"] for entry in response["bundle"]["entry"]]
            assert [resource["resourceType"] for resource in resources] == [
                "Patient",
                "Observation",
            ]
            assert resources[1]["code"]["coding"][0]["display"] == "血压"
            assert resources[1]["code"]["text"] == "血压"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_runtime_preserves_source_display_and_warns_when_translation_is_missing(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog.jsonl"
    _write_catalog(catalog_path, code="other")
    localizer = SyntheaClinicalDisplayLocalizer(
        _StubLocalizer(),
        catalog_path=catalog_path,
        expected_catalog_sha256=load_catalog(catalog_path).sha256,
        projection_id="synthea-zh-cn@test.r1",
    )
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{
            "resource": {
                "resourceType": "Observation",
                "id": "obs-1",
                "code": {"coding": [{
                    "system": "http://loinc.org",
                    "code": "missing",
                    "display": "Untranslated",
                }]},
            }
        }],
    }
    server = create_synthea_service_server(localizer, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with closing(HTTPConnection("127.0.0.1", server.server_port, timeout=2)) as connection:
            status, response = _request(
                connection, "POST", "/v1/localize", {"bundle": bundle, "seed": "seed"}
            )
            assert status == 200
            assert response["bundle"]["entry"][0]["resource"]["code"]["coding"][0][
                "display"
            ] == "Untranslated"
            assert response["warnings"] == [{
                "code": "TRANSLATION_GAP",
                "message": "The Synthea Bundle contains untranslated clinical displays",
                "gapCount": 1,
                "gaps": [{
                    "resourceType": "Observation",
                    "resourceId": "obs-1",
                    "path": "code.coding[0]",
                    "system": "http://loinc.org",
                    "version": None,
                    "code": "missing",
                    "sourceDisplay": "Untranslated",
                }],
                "truncated": False,
            }]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_runtime_rejects_catalog_that_does_not_match_expected_sha256(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.jsonl"
    _write_catalog(catalog_path)
    expected_catalog_sha256 = load_catalog(catalog_path).sha256
    _write_catalog(catalog_path, display="高血压")

    with pytest.raises(SyntheaLocalizationError, match="catalog SHA-256 mismatch"):
        SyntheaClinicalDisplayLocalizer(
            _StubLocalizer(),
            catalog_path=catalog_path,
            expected_catalog_sha256=expected_catalog_sha256,
            projection_id="synthea-zh-cn@test.r1",
        )
