"""Every failure of this API, turned into one envelope: RFC 7807 `application/problem+json`.

This module is the only place in the codebase that pairs an error with a status code. The domain
exceptions know nothing about HTTP -- that is what makes them testable with no framework running
-- and the mapping has to live somewhere the outside world can read.

Six handlers. Two of them exist to make "every error of this API looks the same" true rather than
nearly true: without the `HTTPException` handler a `POST /health` answers
`{"detail": "Method Not Allowed"}` in `application/json`, and without the `Exception` handler an
unexpected failure answers Starlette's plain-text `Internal Server Error`. Both are ten-second
curl commands away from contradicting the claim. The sixth, `ServiceUnavailableError`, is the
only one raised about this service rather than about a request. ADR-0008.
"""

import logging
from collections.abc import Mapping
from http import HTTPStatus

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from url_shortener.adapter.web.dto.response.problem_response import FieldError, ProblemResponse
from url_shortener.adapter.web.handler.problem_type import ProblemType
from url_shortener.adapter.web.handler.service_unavailable_error import ServiceUnavailableError
from url_shortener.domain.exception.invalid_target_url_error import InvalidTargetUrlError
from url_shortener.domain.exception.link_not_found_error import LinkNotFoundError

PROBLEM_MEDIA_TYPE = "application/problem+json"

_logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Install every handler on the app, before any router is included.

    Five of the six calls carry a narrow `type: ignore`, and the alternative is worse. Starlette
    types a handler as `Callable[[Request, Exception], Response]`; parameters are contravariant, so
    a handler that precisely declares the exception it handles is not assignable to that. Writing
    `exc: Exception` and casting inside would silence the checker in the one place it is doing
    useful work -- checking each handler's body against the real exception type -- so the
    imprecision is kept at the registration line, where it is visible and explained.

    The sixth needs none: `_handle_unexpected` takes `exc: Exception`, which is exactly the type
    Starlette declares. Removing the five proves they are load-bearing -- `uv run mypy` then
    reports five errors, on those five lines and on no others.

    One registration is written across four lines rather than one, and only because the single
    line would be 101 columns wide. mypy blames the argument, so the suppression sits on the
    argument; it is the same imprecision in the same place, wrapped.
    """
    app.add_exception_handler(InvalidTargetUrlError, _handle_invalid_target_url)  # type: ignore[arg-type]
    app.add_exception_handler(LinkNotFoundError, _handle_link_not_found)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _handle_request_validation)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, _handle_http_exception)  # type: ignore[arg-type]
    app.add_exception_handler(
        ServiceUnavailableError,
        _handle_service_unavailable,  # type: ignore[arg-type]
    )
    app.add_exception_handler(Exception, _handle_unexpected)


def _handle_invalid_target_url(request: Request, exc: InvalidTargetUrlError) -> Response:
    """400: the payload was well formed and the domain policy still refused the target.

    This is the whole 400-versus-422 distinction. The schema was fine; a business rule said no.

    `reason` travels as an extension member, carrying the machine-readable half of the refusal --
    `unsupported-scheme`, `non-public-address` -- so a client can branch on it without matching
    English, while `detail` names the offending scheme or host, which the taxonomy alone cannot.
    All nine reasons map to this one status and this one type: the reason is not a second status
    taxonomy.
    """
    return _problem(
        ProblemResponse(
            type=ProblemType.INVALID_TARGET_URL,
            title="The target URL was refused",
            status=HTTPStatus.BAD_REQUEST,
            detail=exc.message,
            instance=request.url.path,
            reason=exc.reason,
        )
    )


def _handle_link_not_found(request: Request, exc: LinkNotFoundError) -> Response:
    """404: the code names no link -- or is not a code at all, which answers the same.

    Both `GET /{code}` and `GET /links/{code}` arrive here, and the two failures behind them are
    deliberately indistinguishable from outside. Telling them apart would tell somebody
    enumerating codes which of their guesses were at least well formed.

    `detail` repeats the value that was asked for, which looks like the thing the 422 handler
    below refuses to do -- and the difference is worth naming, because the rule is not "never
    reflect input". What that handler drops is `input`: an arbitrary request body, of arbitrary
    size and shape, that the caller chose. What this one reflects is a single path segment the
    router already matched, which `instance` carries anyway, and which is the only thing that makes
    the message useful to whoever mistyped a link.
    """
    return _problem(
        ProblemResponse(
            type=ProblemType.LINK_NOT_FOUND,
            title="No link answers to that code",
            status=HTTPStatus.NOT_FOUND,
            detail=exc.message,
            instance=request.url.path,
        )
    )


def _handle_request_validation(request: Request, exc: RequestValidationError) -> Response:
    """422: the payload is not even the right shape, so no business rule was ever consulted.

    This replaces FastAPI's own handler, whose body is `{"detail": [...]}` in `application/json`.
    Leaving it in place would mean the most common error of the whole API is the one error that
    does not look like the others.

    The field list is rebuilt rather than forwarded: `exc.errors()` carries `input`, which echoes
    the caller's payload back to them, and `ctx`, which holds values that do not always survive
    JSON.
    """
    return _problem(
        ProblemResponse(
            type=ProblemType.VALIDATION_ERROR,
            title="The request body is not valid",
            status=HTTPStatus.UNPROCESSABLE_CONTENT,
            detail="The request does not match the schema this endpoint accepts.",
            instance=request.url.path,
            errors=[
                FieldError(
                    field=".".join(str(part) for part in error["loc"]),
                    message=error["msg"],
                    type=error["type"],
                )
                for error in exc.errors()
            ],
        )
    )


def _handle_http_exception(request: Request, exc: HTTPException) -> Response:
    """Whatever status the framework refused with, in this API's envelope.

    Nothing in this project raises `HTTPException`; the router does, and that is the point. A
    `POST /health` is a 405 and a request the catch-all cannot match is a 404, both produced
    before any controller runs.

    `exc.headers` is passed through because a 405 carries `Allow`, and a 405 without it stops
    being a useful answer. The title is the status phrase, which is what the RFC prescribes when a
    problem has no more specific name than its status.
    """
    return _problem(
        ProblemResponse(
            type=ProblemType.HTTP_ERROR,
            title=HTTPStatus(exc.status_code).phrase,
            status=exc.status_code,
            detail=str(exc.detail),
            instance=request.url.path,
        ),
        headers=exc.headers,
    )


def _handle_service_unavailable(request: Request, exc: ServiceUnavailableError) -> Response:
    """503: this API is up, and something it needs is not.

    The one status in this API that says "come back later" rather than "your request was wrong" or
    "we have a bug". It is answered by `/health` and by nothing else: a caller who hits the database
    being down on `POST /links` gets a 500, because from that route's point of view the request
    failed for a reason nobody can name yet. ADR-0008.

    `detail` names the dependency and stops there. That is more than the 500 says, and deliberately
    so -- the whole job of this endpoint is to report which of its dependencies is out -- but it is
    still a word chosen by this codebase, never a driver message or a connection string.
    """
    return _problem(
        ProblemResponse(
            type=ProblemType.SERVICE_UNAVAILABLE,
            title="The service cannot serve requests right now",
            status=HTTPStatus.SERVICE_UNAVAILABLE,
            detail=f"The {exc.dependency} this service depends on is not answering.",
            instance=request.url.path,
        )
    )


def _handle_unexpected(request: Request, exc: Exception) -> Response:
    """500: something failed that nobody planned for.

    The body says nothing about what: a stack trace, an exception message or a driver error in a
    response is how internal detail leaks to whoever is probing. It goes to the log instead.

    The traceback is attached with `exc_info=exc` rather than by calling `logger.exception`, and
    that is not a style choice. Starlette runs a synchronous exception handler through
    `run_in_threadpool`, so this function executes on a different thread from the `except` block
    that caught the error -- `sys.exc_info()` is empty here, and `logger.exception` writes
    `NoneType: None` where the traceback should be. There is a test asserting the traceback is
    really in the log, because a 500 that records nothing and says nothing is a failure nobody
    ever hears about.
    """
    _logger.error("unhandled error answering %s %s", request.method, request.url.path, exc_info=exc)
    return _problem(
        ProblemResponse(
            type=ProblemType.INTERNAL_ERROR,
            title="The server failed to handle the request",
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="The request could not be handled. The failure was recorded on the server.",
            instance=request.url.path,
        )
    )


def _problem(problem: ProblemResponse, *, headers: Mapping[str, str] | None = None) -> Response:
    """Serialise one problem, with the media type that makes it a Problem Details document.

    `exclude_none=True` is what keeps `reason` and `errors` out of the bodies that have nothing to
    put in them: an extension member is optional by definition, and a null is not the same as an
    absence to a client reading the document.
    """
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(mode="json", exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=dict(headers) if headers else None,
    )
