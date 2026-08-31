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

from fastapi import FastAPI

from url_shortener.adapter.web import health_controller, link_controller, redirect_controller
from url_shortener.adapter.web.handler.problem_details import register_exception_handlers


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

    return app


app = create_app()
