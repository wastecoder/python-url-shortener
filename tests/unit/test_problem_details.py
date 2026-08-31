"""Every failure of this API in one envelope, checked against a bare app that only raises.

The app built here carries the handlers and four routes that exist to trip them, and no controller
at all. That is on purpose: what is under test is the mapping from error to response, and
exercising it through the real endpoints would make these assertions depend on route order, on
wiring and on the use cases.
"""

import logging
from http import HTTPStatus
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from url_shortener.adapter.web.handler.problem_details import (
    PROBLEM_MEDIA_TYPE,
    register_exception_handlers,
)
from url_shortener.adapter.web.handler.service_unavailable_error import ServiceUnavailableError
from url_shortener.domain.exception.invalid_target_url_error import InvalidTargetUrlError
from url_shortener.domain.exception.link_not_found_error import LinkNotFoundError
from url_shortener.domain.exception.rejection_reason import RejectionReason

REFUSAL_DETAIL = "the host 'localhost' can only name something on the caller's own network"
UNEXPECTED_DETAIL = "the database connection went away"
DEPENDENCY = "database"


class _Payload(BaseModel):
    url: str


def _app() -> FastAPI:
    """A bare app: the handlers, plus one route per failure they answer."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/refused")
    def _refused() -> None:
        raise InvalidTargetUrlError(RejectionReason.NON_PUBLIC_HOST, REFUSAL_DETAIL)

    @app.get("/missing")
    def _missing() -> None:
        raise LinkNotFoundError("zzzzzzz")

    @app.post("/validated")
    def _validated(payload: _Payload) -> str:
        return payload.url

    @app.get("/boom")
    def _boom() -> None:
        raise RuntimeError(UNEXPECTED_DETAIL)

    @app.get("/down")
    def _down() -> None:
        raise ServiceUnavailableError(DEPENDENCY)

    return app


@pytest.fixture
def bare_client() -> TestClient:
    """A client that lets a 500 come back as a response instead of re-raising in the test.

    Without `raise_server_exceptions=False` the test client re-raises whatever the app failed
    with, which is convenient everywhere except here -- the body of the 500 is precisely what has
    to be inspected.
    """
    return TestClient(_app(), raise_server_exceptions=False)


def test_a_refused_target_url_answers_400_carrying_its_reason(bare_client: TestClient) -> None:
    """
    Given a request the domain policy refuses,
    when the endpoint answers,
    then it is a 400 problem document naming the type, the offending host and the machine-readable
    reason -- because the payload was well formed and only a business rule said no.
    """
    response = bare_client.get("/refused")

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json() == {
        "type": "invalid-target-url",
        "title": "The target URL was refused",
        "status": 400,
        "detail": REFUSAL_DETAIL,
        "instance": "/refused",
        "reason": "non-public-host",
    }


def test_an_unknown_code_answers_404_without_the_extension_members(bare_client: TestClient) -> None:
    """
    Given a code that names no link,
    when the endpoint answers,
    then it is a 404 problem document, and the optional members are absent rather than null.
    """
    response = bare_client.get("/missing")

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json() == {
        "type": "link-not-found",
        "title": "No link answers to that code",
        "status": 404,
        "detail": "no link exists for code 'zzzzzzz'",
        "instance": "/missing",
    }


def test_a_malformed_body_answers_422_naming_the_field_it_refused(bare_client: TestClient) -> None:
    """
    Given a body missing a required field,
    when the endpoint answers,
    then it is a 422 problem document in the same envelope as every other error, listing the
    field -- and not FastAPI's own `{"detail": [...]}` shape.
    """
    response = bare_client.post("/validated", json={})

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json() == {
        "type": "validation-error",
        "title": "The request body is not valid",
        "status": 422,
        "detail": "The request does not match the schema this endpoint accepts.",
        "instance": "/validated",
        "errors": [{"field": "body.url", "message": "Field required", "type": "missing"}],
    }


def test_the_validation_body_never_echoes_the_payload_back(bare_client: TestClient) -> None:
    """
    Given a body whose value is wrong rather than missing,
    when the endpoint answers,
    then the offending value is not repeated in the response, because Pydantic's `input` and `ctx`
    are rebuilt away rather than forwarded.
    """
    response = bare_client.post("/validated", json={"url": {"secret": "do-not-echo-me"}})

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert "do-not-echo-me" not in response.text
    assert "input" not in response.json()["errors"][0]


def test_a_wrong_method_answers_in_the_same_envelope_and_keeps_allow(
    bare_client: TestClient,
) -> None:
    """
    Given a request using a method the route does not serve,
    when the router refuses it,
    then the 405 arrives as a problem document too -- which is what makes "every error looks the
    same" true -- and it still carries the Allow header a 405 is useless without.
    """
    response = bare_client.put("/refused")

    assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.headers["allow"] == "GET"
    assert response.json() == {
        "type": "http-error",
        "title": "Method Not Allowed",
        "status": 405,
        "detail": "Method Not Allowed",
        "instance": "/refused",
    }


def test_a_path_no_route_matches_answers_in_the_same_envelope(bare_client: TestClient) -> None:
    """
    Given a path no route matches,
    when the router refuses it,
    then the 404 is a problem document as well, and it is typed `http-error` rather than
    `link-not-found`: nothing looked for a link, so claiming one is missing would be a guess.
    """
    response = bare_client.get("/nothing/here")
    body: dict[str, Any] = response.json()

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert body["type"] == "http-error"
    assert body["title"] == "Not Found"


def test_an_unexpected_failure_answers_500_without_leaking_the_cause(
    bare_client: TestClient,
) -> None:
    """
    Given an endpoint that fails in a way nobody planned for,
    when it answers,
    then it is a 500 problem document, and the exception message is nowhere in the body -- an
    internal message in a response is how detail leaks to whoever is probing.
    """
    response = bare_client.get("/boom")

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json() == {
        "type": "internal-error",
        "title": "The server failed to handle the request",
        "status": 500,
        "detail": "The request could not be handled. The failure was recorded on the server.",
        "instance": "/boom",
    }
    assert UNEXPECTED_DETAIL not in response.text


def test_an_unexpected_failure_is_recorded_on_the_server(
    bare_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """
    Given an endpoint that fails unexpectedly,
    when it answers,
    then the traceback is in the log, which is the other half of not putting it in the body.
    """
    with caplog.at_level(logging.ERROR):
        bare_client.get("/boom")

    assert UNEXPECTED_DETAIL in caplog.text
    assert "Traceback" in caplog.text


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/refused"),
        ("GET", "/missing"),
        ("POST", "/validated"),
        ("GET", "/boom"),
        ("GET", "/down"),
    ],
)
def test_every_failure_is_served_as_a_problem_document(
    bare_client: TestClient, method: str, path: str
) -> None:
    """
    Given each kind of failure this API can produce,
    when it answers,
    then the media type is the RFC 7807 one and never plain application/json.
    """
    response = bare_client.request(method, path, json={})

    assert response.status_code >= HTTPStatus.BAD_REQUEST
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


def test_a_dependency_that_is_down_answers_503_naming_it(bare_client: TestClient) -> None:
    """
    Given a service whose database is not answering,
    when the endpoint that reports on it is asked,
    then the answer is 503 in the same envelope, saying which dependency is out.

    503 rather than 500, and the split is the point: 500 means this API has a bug, 503 means it is
    working and something it needs is not. A load balancer can act on the second one, and only the
    first is worth waking somebody for.
    """
    response = bare_client.get("/down")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json() == {
        "type": "service-unavailable",
        "title": "The service cannot serve requests right now",
        "status": 503,
        "detail": "The database this service depends on is not answering.",
        "instance": "/down",
    }


def test_the_unavailable_body_carries_no_configuration(bare_client: TestClient) -> None:
    """
    Given the 503 body,
    when it is read,
    then it names the dependency and nothing about how that dependency is reached -- no DSN, no
    host, no driver message. What is down is worth telling; where it lives is not.
    """
    body = bare_client.get("/down").text

    assert DEPENDENCY in body
    for secret in ("postgresql", "psycopg", "localhost", "5432", "password"):
        assert secret not in body, secret
