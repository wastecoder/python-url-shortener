"""`GET /health`: static while there is nothing to check, and dependent on nothing."""

from http import HTTPStatus

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from url_shortener.adapter.web import health_controller


def test_health_answers_ok(client: TestClient) -> None:
    """
    Given the running service,
    when its health is asked for,
    then it answers 200 with a status of ok.
    """
    response = client.get("/health")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ok"}


def test_health_needs_no_dependency_to_answer() -> None:
    """
    Given the health route,
    when its dependencies are inspected,
    then it declares none -- an endpoint that needed a session, a setting or a use case to report
    health could fail for reasons that have nothing to do with the health it reports.

    This is the assertion that has to change in Fase 4, deliberately: the endpoint gains a
    database dependency there, because from then on it has something real to check.

    The router is read directly rather than through `app.routes`, and that is not incidental:
    Starlette 1.6 wraps an included router in an opaque object instead of flattening its routes
    into the application, so `app.routes` no longer contains this route at all.
    """
    route = next(
        candidate
        for candidate in health_controller.router.routes
        if isinstance(candidate, APIRoute) and candidate.path == "/health"
    )

    assert route.dependant.dependencies == []


def test_health_says_nothing_about_the_store_yet(client: TestClient) -> None:
    """
    Given a request that fills the store and one that does not,
    when health is asked for after each,
    then the answer is the same -- which is the honest reading of a static check, and the reason
    Fase 4 has to replace it with one that runs SELECT 1.
    """
    before = client.get("/health").json()
    client.post("/links", json={"url": "https://example.com/a"})

    assert client.get("/health").json() == before
