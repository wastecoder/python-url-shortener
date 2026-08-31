"""The route table: the catch-all is registered last, and nothing it could swallow is swallowed.

This is the suite that guards the load-bearing half of the design. `GET /{code}` matches any
single path segment at the root, so registering it before `/links`, `/health` or the generated
documentation would make every one of them resolve as a short code -- and each of those would then
answer 404, because none of them is seven characters long. The failure is silent: every test that
posts to `/links` would still fail, but a reviewer opening `/docs` is the one who finds out.
"""

from http import HTTPStatus

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from url_shortener.adapter.web import health_controller, link_controller, redirect_controller


def _included_routers(app: FastAPI) -> list[object]:
    """The routers of the app, in the order they were included.

    Starlette 1.6 keeps an included router as one opaque entry in `app.routes` instead of
    flattening its routes into the application, so the order of registration is read here rather
    than by looking for paths.
    """
    return [route.original_router for route in app.routes if hasattr(route, "original_router")]


def _paths(app: FastAPI) -> list[str]:
    """Every path the app answers, in registration order, flattened across the routers."""
    paths: list[str] = []
    for route in app.routes:
        original = getattr(route, "original_router", None)
        candidates = original.routes if original is not None else [route]
        paths.extend(candidate.path for candidate in candidates if isinstance(candidate, APIRoute))
    return paths


def test_the_catch_all_router_is_registered_last(app: FastAPI) -> None:
    """
    Given the application,
    when its routers are read in order,
    then the redirect router is the last one -- registered after /links and /health, because a
    catch-all at the root matches them too and the first match wins.
    """
    assert _included_routers(app) == [
        link_controller.router,
        health_controller.router,
        redirect_controller.router,
    ]


def test_the_catch_all_path_comes_after_every_other(app: FastAPI) -> None:
    """
    Given every path the application serves,
    when they are listed in registration order,
    then `/{code}` is last, which is the same fact stated about paths rather than routers.
    """
    paths = _paths(app)

    assert paths[-1] == "/{code}"
    assert set(paths) == {"/links", "/links/{code}", "/health", "/{code}"}


def test_the_api_serves_exactly_four_operations(app: FastAPI) -> None:
    """
    Given the generated OpenAPI document,
    when its operations are counted,
    then there are four and they are the four of the contract -- the scope guard, asserted.
    """
    document = app.openapi()
    operations = {
        (method.upper(), path) for path, methods in document["paths"].items() for method in methods
    }

    assert operations == {
        ("POST", "/links"),
        ("GET", "/links/{code}"),
        ("GET", "/health"),
        ("GET", "/{code}"),
    }


def test_the_documentation_is_still_reachable(client: TestClient) -> None:
    """
    Given the catch-all registered at the root,
    when the generated documentation is requested,
    then it answers -- and this is the cheapest proof that the catch-all swallowed nothing, since
    the docs are registered by FastAPI itself before any router of ours.
    """
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == HTTPStatus.OK, path


def test_the_named_routes_answer_their_own_endpoints(client: TestClient) -> None:
    """
    Given the catch-all registered at the root,
    when /health and /links/{code} are requested,
    then each is answered by its own endpoint rather than read as a short code -- which would be a
    404, since neither `health` nor `links` is seven characters long.
    """
    created = client.post("/links", json={"url": "https://example.com/a"})

    assert client.get("/health").json() == {"status": "ok"}
    assert client.get(f"/links/{created.json()['code']}").status_code == HTTPStatus.OK


def test_the_root_itself_is_not_a_code(client: TestClient) -> None:
    """
    Given the catch-all,
    when the root is requested,
    then it is a 404 from the router and not from a lookup: `/{code}` needs a segment, and an
    empty one does not match.
    """
    response = client.get("/")

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()["type"] == "http-error"
