"""The composition root of the process: builds the app and registers everything on it.

`create_app` exists beside the module-level `app` for two different callers. `uvicorn
url_shortener.main:app` needs an application object at import time; a test needs a fresh one it
can override dependencies on without leaking into the next test. One factory answers both.

This module sits outside the layer contract in `.importlinter`, which names `adapter`,
`application` and `domain` and nothing else. That is deliberate -- a composition root is the one
place allowed to know every layer at once -- and it is a decision rather than an oversight: adding
it as a fourth layer would mean editing `.importlinter`, which this project requires an ADR for,
to constrain twenty lines that exist to import things.
"""

from typing import Any

from fastapi import FastAPI

from url_shortener.adapter.web import health_controller, link_controller, redirect_controller
from url_shortener.adapter.web.handler.problem_details import (
    PROBLEM_MEDIA_TYPE,
    register_exception_handlers,
)

_PROBLEM_SCHEMA_REF = "#/components/schemas/ProblemResponse"
_FASTAPI_VALIDATION_SCHEMA_REFS = frozenset(
    {"#/components/schemas/HTTPValidationError", "#/components/schemas/ValidationError"}
)


def create_app() -> FastAPI:
    """Build the application: exception handlers first, then the routers, in order."""
    app = FastAPI(
        title="url-shortener",
        version="0.1.0",
        summary="Turns a long URL into a seven-character code and redirects it back.",
        description=(
            "Four routes and nothing else: create a link, follow it, read what is known about "
            "it, and report health. Every failure answers with an RFC 7807 problem document."
        ),
        # A trailing slash is a 404 in this API's own envelope, not a redirect. Starlette's
        # convenience 307 builds its `Location` out of the request's own `Host` header and
        # scheme -- exactly the guess `public_url.py` exists to refuse, since behind a proxy that
        # header names something this service was never told it answers on. None of the four
        # routes is defined with a trailing slash, so nothing is given up by saying no.
        redirect_slashes=False,
    )

    # Before the routers, so that a failure raised while answering any of them lands here rather
    # than in Starlette's defaults.
    register_exception_handlers(app)

    # The order below is load-bearing. `GET /{code}` is a catch-all matching any single segment at
    # the root, so it has to be registered *after* `/links` and `/health`. Move it up and both of
    # those paths resolve as a short code instead, then answer 404, because neither is seven
    # characters long. The documentation routes are safe for a different reason, not this one:
    # `FastAPI.__init__` registers them before any of this code runs.
    app.include_router(link_controller.router)
    app.include_router(health_controller.router)
    app.include_router(redirect_controller.router)

    # Generated once here and cached on the app, because `openapi()` hands back `openapi_schema`
    # whenever it is already set.
    app.openapi_schema = _describe_errors_accurately(app.openapi())

    return app


def _describe_errors_accurately(document: dict[str, Any]) -> dict[str, Any]:
    """Make the generated document say what the error path actually does.

    Two corrections, and both exist because this project calls the generated `/docs` its user
    interface. A document that describes a different API than the one running is worse than no
    document, because a reader has no way of telling which half is true.

    **The media type.** FastAPI files every `responses={...: {"model": ProblemResponse}}` entry
    under the route's own media type, which is `application/json`. All of those bodies are served
    as `application/problem+json`. Declaring `content` by hand on each route does not fix it --
    FastAPI merges its own entry alongside, leaving two, one of which is wrong.

    **The phantom 422.** FastAPI injects a `422` pointing at its own `HTTPValidationError` into
    every operation that takes a parameter, unless the route already declares one. On
    `GET /links/{code}` and `GET /{code}` that response can never happen -- `code` is a plain
    `str` and every path segment is one -- and the shape it advertises is the `{"detail": [...]}`
    envelope this phase exists to replace. Declaring a 422 on those routes would silence it by
    documenting a different impossible response, so the injected one is removed instead, together
    with the schemas left with nothing pointing at them.
    """
    for path_item in document["paths"].values():
        for operation in path_item.values():
            responses = operation.get("responses", {})
            for status, response in list(responses.items()):
                content = response.get("content", {})
                reference = content.get("application/json", {}).get("schema", {}).get("$ref")
                if reference in _FASTAPI_VALIDATION_SCHEMA_REFS:
                    del responses[status]
                elif reference == _PROBLEM_SCHEMA_REF:
                    content[PROBLEM_MEDIA_TYPE] = content.pop("application/json")

    schemas = document.get("components", {}).get("schemas", {})
    still_referenced = str(document["paths"])
    for name in ("HTTPValidationError", "ValidationError"):
        if name in schemas and f"#/components/schemas/{name}" not in still_referenced:
            del schemas[name]

    return document


app = create_app()
