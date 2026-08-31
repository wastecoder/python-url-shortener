"""`GET /health`: it asks the database, and it answers 503 when the database does not.

Every assertion in this file was rewritten in Fase 4, deliberately. Until then the endpoint was
static and this suite pinned that it declared *no* dependency at all -- the honest shape while
there was nothing to check, and a marker that it was unfinished. What replaces that assertion is
not weaker but narrower: the route declares exactly one dependency, and it is the probe.
"""

from http import HTTPStatus

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from tests.fakes import StubHealthProbe
from url_shortener.adapter.config.dependencies import get_health_probe, get_session
from url_shortener.adapter.web import health_controller
from url_shortener.adapter.web.handler.problem_details import PROBLEM_MEDIA_TYPE


def _health_route() -> APIRoute:
    """The health route, read off its own router.

    Read directly rather than through `app.routes`, and that is not incidental: Starlette 1.6 wraps
    an included router in an opaque object instead of flattening its routes into the application,
    so `app.routes` no longer contains this route at all.
    """
    return next(
        candidate
        for candidate in health_controller.router.routes
        if isinstance(candidate, APIRoute) and candidate.path == "/health"
    )


def test_health_answers_ok_when_the_database_answers(client: TestClient) -> None:
    """
    Given a database that responds,
    when the health of the service is asked for,
    then it answers 200 with a status of ok, in plain application/json.
    """
    response = client.get("/health")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"].startswith("application/json")


def test_health_answers_503_when_the_database_does_not(
    client: TestClient, probe: StubHealthProbe
) -> None:
    """
    Given a database that is not answering,
    when the health of the service is asked for,
    then it answers 503 in this API's own error envelope, naming the dependency that is out.

    503 and not 500: the service is up and something it needs is not, which is a different fact and
    a differently actionable one. ADR-0008.
    """
    probe.reachable = False

    response = client.get("/health")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json() == {
        "type": "service-unavailable",
        "title": "The service cannot serve requests right now",
        "status": 503,
        "detail": "The database this service depends on is not answering.",
        "instance": "/health",
    }


def test_health_tracks_the_database_rather_than_deciding_once(
    client: TestClient, probe: StubHealthProbe
) -> None:
    """
    Given a service whose database goes away and comes back,
    when health is asked for at each point,
    then the answer follows it.

    This is the assertion that the check is really being run per request. An endpoint that resolved
    its answer at startup -- or that cached a healthy result -- would pass both tests above and
    still be a lie, because a health check is only worth anything at the moment things break.
    """
    assert client.get("/health").status_code == HTTPStatus.OK

    probe.reachable = False
    assert client.get("/health").status_code == HTTPStatus.SERVICE_UNAVAILABLE

    probe.reachable = True
    assert client.get("/health").status_code == HTTPStatus.OK


def test_health_depends_on_exactly_one_thing_and_it_is_the_probe() -> None:
    """
    Given the health route,
    when its dependencies are inspected,
    then there is exactly one and it is the probe.

    The old form of this test asserted the list was empty, on the principle that an endpoint needing
    a session, a setting or a use case to report health could fail for reasons unrelated to the
    health it reports. The principle is intact and this is the stricter statement of it: not "few
    dependencies" but *this* dependency -- the one thing the endpoint exists to report on.
    """
    dependencies = _health_route().dependant.dependencies

    assert [dependency.call for dependency in dependencies] == [get_health_probe]


def test_health_is_not_enlisted_in_the_request_transaction() -> None:
    """
    Given the health route,
    when its whole dependency tree is walked,
    then the request session is nowhere in it.

    Two failures are avoided by this and they are different. A `/health` holding a session would
    report unhealthy whenever the pool was busy, which is a fact about load. Worse, a session that
    cannot connect raises while the dependency is being *acquired* -- before this controller runs --
    so the answer would be a 500 from the generic handler, in the exact situation the endpoint
    exists to report as 503.
    """
    route = _health_route()
    reached = {dependency.call for dependency in route.dependant.dependencies}
    for dependency in route.dependant.dependencies:
        reached.update(nested.call for nested in dependency.dependencies)

    assert get_session not in reached


def test_the_health_document_advertises_both_answers(client: TestClient) -> None:
    """
    Given the generated OpenAPI document,
    when the health operation is read,
    then it declares 200 and 503 -- a documented endpoint that hides its failure mode is a
    documented endpoint nobody can write a client against.
    """
    responses = client.get("/openapi.json").json()["paths"]["/health"]["get"]["responses"]

    assert sorted(responses) == ["200", "503"]
    assert list(responses["503"]["content"]) == [PROBLEM_MEDIA_TYPE]
