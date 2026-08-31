"""The route table: the catch-all is registered last, and nothing it could swallow is swallowed.

This is the suite that guards the load-bearing half of the design. `GET /{code}` matches any
single path segment at the root, so registering it before `/links` or `/health` would make both
of them resolve as a short code -- and each would then answer 404, because neither is seven
characters long. The documentation routes survive any ordering of ours, because `FastAPI.__init__`
registers them before `create_app` includes anything; they are asserted here anyway, since that is
a fact about the framework and not about this code.

The suite also reads the generated document itself. This project calls `/docs` its user interface,
so a document that describes a different API than the one running is a defect in the interface.
"""

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from url_shortener.adapter.web import health_controller, link_controller, redirect_controller
from url_shortener.adapter.web.handler.problem_details import PROBLEM_MEDIA_TYPE
from url_shortener.main import _describe_errors_accurately


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


def test_the_documented_responses_are_the_ones_the_api_can_send(app: FastAPI) -> None:
    """
    Given the generated document,
    when the declared responses of each operation are listed,
    then they are exactly what each route can answer.

    This is what keeps `/docs` from drifting: deleting `status_code=HTTPStatus.FOUND` from the
    redirect decorator makes the document advertise 307 on the one route whose headline decision
    is "302, never 307", and without this assertion nothing notices.
    """
    paths = app.openapi()["paths"]

    assert sorted(paths["/links"]["post"]["responses"]) == ["200", "201", "400", "422"]
    assert sorted(paths["/links/{code}"]["get"]["responses"]) == ["200", "404"]
    assert sorted(paths["/{code}"]["get"]["responses"]) == ["302", "404"]
    assert sorted(paths["/health"]["get"]["responses"]) == ["200", "503"]


def test_every_documented_error_body_is_a_problem_document(app: FastAPI) -> None:
    """
    Given the generated document,
    when the media type of every error response is read,
    then it is application/problem+json -- the one the API actually serves. FastAPI files a
    `responses={"model": ProblemResponse}` entry under the route's own media type, which is
    application/json, so `create_app` corrects the document before caching it.
    """
    for path, operations in app.openapi()["paths"].items():
        for method, operation in operations.items():
            for status, response in operation["responses"].items():
                if int(status) < HTTPStatus.BAD_REQUEST or "content" not in response:
                    continue
                assert list(response["content"]) == [PROBLEM_MEDIA_TYPE], (
                    f"{method} {path} {status}"
                )


def test_the_document_never_mentions_fastapis_own_error_shape(app: FastAPI) -> None:
    """
    Given the generated document,
    when it is searched for FastAPI's default validation envelope,
    then it is absent -- neither advertised on a route nor left orphaned in the components.

    FastAPI injects a 422 pointing at `HTTPValidationError` into every operation that takes a
    parameter. On the two `{code}` routes that response cannot happen, and the shape it promises is
    the `{"detail": [...]}` body this phase replaced, so `/docs` would be contradicting the API it
    documents.
    """
    document = app.openapi()

    assert "HTTPValidationError" not in str(document["paths"])
    assert "HTTPValidationError" not in document["components"]["schemas"]
    assert "ValidationError" not in document["components"]["schemas"]


def test_a_trailing_slash_is_refused_rather_than_redirected(client: TestClient) -> None:
    """
    Given a path that only differs from a route by a trailing slash,
    when it is requested,
    then it is a 404 in this API's own envelope, and not Starlette's convenience 307 -- whose
    Location would be assembled from the caller's own Host header, which is the guess the whole
    BASE_URL setting exists to avoid.
    """
    created = client.post("/links", json={"url": "https://example.com/a"})
    code = created.json()["code"]

    for path in ("/links/", f"/{code}/", f"/links/{code}/"):
        response = client.get(path)
        assert response.status_code == HTTPStatus.NOT_FOUND, path
        assert "location" not in response.headers, path


def test_the_module_level_app_is_the_one_uvicorn_is_told_to_serve() -> None:
    """
    Given the entrypoint documented in the command table, `url_shortener.main:app`,
    when it is imported,
    then it is an application carrying the routes -- the assertion that the name the run command
    depends on cannot be deleted or renamed without something failing.
    """
    from url_shortener.main import app as entrypoint

    assert isinstance(entrypoint, FastAPI)
    assert _paths(entrypoint)[-1] == "/{code}"


def test_a_validation_schema_something_still_points_at_is_not_removed() -> None:
    """
    Given a document whose components carry a validation schema a path still references,
    when the corrections are applied,
    then the schema survives, and the one nothing references is dropped.

    The cleanup exists to remove schemas left dangling once the injected 422s are gone, and the
    condition it must not break is this one: a `$ref` pointing at a schema that is no longer there
    is a broken document, which is worse than an unused definition sitting in it.

    Asserted against the function rather than against the generated document because this
    application's own routes cannot produce the case -- every reference to those two schemas comes
    from a response this pass deletes. A branch that only a hypothetical document reaches is still
    a branch, and leaving it unexercised would mean the `not in still_referenced` half of the guard
    is never once observed refusing a deletion. (The other half, `name in schemas`, stays true on
    every run of the whole suite: FastAPI always generates both schemas.)
    """
    document: dict[str, Any] = {
        "paths": {
            "/somewhere": {
                "post": {
                    "responses": {
                        "422": {
                            "content": {
                                # Not `application/json`, so the first pass leaves it alone and the
                                # reference is still live when the cleanup runs.
                                PROBLEM_MEDIA_TYPE: {
                                    "schema": {"$ref": "#/components/schemas/ValidationError"}
                                }
                            }
                        }
                    }
                }
            }
        },
        "components": {"schemas": {"ValidationError": {}, "HTTPValidationError": {}}},
    }

    corrected = _describe_errors_accurately(document)

    assert set(corrected["components"]["schemas"]) == {"ValidationError"}
