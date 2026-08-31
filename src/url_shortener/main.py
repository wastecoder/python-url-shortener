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

from url_shortener.adapter.web import health_controller, link_controller
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
    )

    # Before the routers, so that a failure raised while answering any of them lands here rather
    # than in Starlette's defaults.
    register_exception_handlers(app)

    app.include_router(link_controller.router)
    app.include_router(health_controller.router)

    return app


app = create_app()
