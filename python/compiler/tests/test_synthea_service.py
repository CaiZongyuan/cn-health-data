import json
import threading
from contextlib import closing
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

from cn_health_compiler.synthetic.synthea_localizer import LocalizedSyntheaBundle
from cn_health_compiler.synthetic.synthea_service import create_synthea_service_server


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


def test_synthea_service_docker_image_keeps_candidate_data_external() -> None:
    repository = Path(__file__).parents[3]
    dockerfile = (repository / "Dockerfile.synthea-localizer").read_text(encoding="utf-8")
    dockerignore = (repository / ".dockerignore").read_text(encoding="utf-8")

    assert "USER 10001:10001" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "COPY LICENSE /opt/licenses/CN-HEALTH-DATA-LICENSE" in dockerfile
    assert "COPY DATA-NOTICE.md /opt/licenses/CN-HEALTH-DATA-NOTICE" in dockerfile
    assert "COPY dist" not in dockerfile
    assert "COPY tmp" not in dockerfile
    assert "dist/" in dockerignore
    assert "tmp/" in dockerignore
