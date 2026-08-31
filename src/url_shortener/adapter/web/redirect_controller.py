"""`GET /{code}`: the catch-all at the root that follows a short link."""

from http import HTTPStatus
from ipaddress import IPv4Address, IPv6Address, ip_address

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import RedirectResponse

from url_shortener.adapter.config.dependencies import ResolveLinkUseCaseDep
from url_shortener.adapter.web.dto.response.problem_response import ProblemResponse

router = APIRouter(tags=["redirect"])


@router.get(
    "/{code}",
    status_code=HTTPStatus.FOUND,
    response_class=RedirectResponse,
    summary="Follow a short code to its destination",
    responses={
        HTTPStatus.FOUND: {
            "description": "The destination, in the Location header. The access was recorded.",
        },
        HTTPStatus.NOT_FOUND: {
            "model": ProblemResponse,
            "description": "No link answers to that code, or it is not a code at all.",
        },
    },
)
def follow_short_code(
    code: str, request: Request, use_case: ResolveLinkUseCaseDep
) -> RedirectResponse:
    """Send the caller to where the code points, and record that somebody went there.

    **302, explicitly.** Starlette's `RedirectResponse` defaults to `307`, which preserves the
    request method -- not what a short link means. `301` would be worse: a browser caches it, so
    the second visit never reaches this API at all, which kills the measurement and makes the
    destination impossible to change or switch off afterwards. See ADR-0001.

    `Cache-Control: no-store` says the same thing to anything between the caller and here. A `302`
    is already not cacheable without explicit freshness information, so the header adds no rule --
    it makes the rule checkable with one `curl -i` instead of with a reading of RFC 9111.

    A failure to record the click fails the redirect. Nothing here catches it, and that is the
    decision rather than an oversight: there is no queue and no outbox, so swallowing it would
    turn a database failure on the only write path of this route into a log line with no second
    alarm behind it.
    """
    result = use_case.resolve(
        code,
        user_agent=request.headers.get("user-agent"),
        referer=request.headers.get("referer"),
        ip=_client_address(request),
    )
    return RedirectResponse(
        result.target_url,
        status_code=HTTPStatus.FOUND,
        headers={"Cache-Control": "no-store"},
    )


def _client_address(request: Request) -> IPv4Address | IPv6Address | None:
    """The address the request came from, or `None` when there is not one to be had.

    Parsed here rather than in the application, so a value that layer accepted cannot fail later
    against a column that stores addresses. Three things can happen and all three are ordinary: an
    ASGI server may report no client at all, the value may not parse as an address, and it may
    parse fine -- a click with no address is a click, not an error.

    `X-Forwarded-For` is deliberately not read. Nothing terminates in front of this application, so
    the header is not evidence of anything: any caller can set it, and trusting it would let every
    click record whatever address its sender preferred. The day a proxy exists, the fix is to
    configure the ASGI server's trusted-hosts middleware -- which parses the header once, against a
    list of proxies it is told about -- and not to read it here.
    """
    client = request.client
    if client is None:
        return None
    try:
        return ip_address(client.host)
    except ValueError:
        return None
