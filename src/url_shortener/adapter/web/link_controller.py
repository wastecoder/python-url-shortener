"""The `/links` collection: creating a link, and reading what is known about one."""

from http import HTTPStatus

from fastapi import APIRouter, Response

from url_shortener.adapter.config.dependencies import (
    CreateLinkUseCaseDep,
    GetLinkDetailsUseCaseDep,
    SettingsDep,
)
from url_shortener.adapter.web.dto.request.create_link_request import CreateLinkRequest
from url_shortener.adapter.web.dto.response.link_details_response import LinkDetailsResponse
from url_shortener.adapter.web.dto.response.link_response import LinkResponse
from url_shortener.adapter.web.dto.response.problem_response import ProblemResponse
from url_shortener.adapter.web.public_url import link_details_url
from url_shortener.application.viewmodel.create_link_command import CreateLinkCommand

router = APIRouter(tags=["links"])


@router.post(
    "/links",
    status_code=HTTPStatus.CREATED,
    response_model=LinkResponse,
    summary="Shorten a URL",
    responses={
        HTTPStatus.OK: {
            "model": LinkResponse,
            "description": "This URL already had a link, and that link came back unchanged.",
        },
        HTTPStatus.BAD_REQUEST: {
            "model": ProblemResponse,
            "description": "The target URL is well formed and the domain policy refuses it.",
        },
        HTTPStatus.UNPROCESSABLE_CONTENT: {
            "model": ProblemResponse,
            "description": "The body is not the shape this endpoint accepts.",
        },
    },
)
def create_link(
    payload: CreateLinkRequest,
    response: Response,
    use_case: CreateLinkUseCaseDep,
    settings: SettingsDep,
) -> LinkResponse:
    """Shorten a URL, or hand back the link it already has.

    Answers **201** when a link was created and **200** when an existing one came back, so the
    caller can tell the two apart. Asking twice for the same URL is not an error and is not a
    second link: the same code comes back.

    The endpoint is `def` and not `async def`, like every endpoint in this project. FastAPI runs it
    in a threadpool, which is the right shape when the bottleneck is a database round trip -- and
    it is what keeps a synchronous driver from blocking the event loop later.
    """
    result = use_case.create(CreateLinkCommand(url=payload.url))
    body = LinkResponse.from_result(result, base_url=settings.base_url)

    if result.was_created:
        # `Location` names the resource that was created, which in this API is the link's own
        # member of the /links collection -- not the short URL. `GET /{code}` is not a
        # representation of the link, it is an action on it, and the short URL is already in the
        # body, so pointing the header there would repeat a fact instead of adding one.
        response.headers["Location"] = link_details_url(body.code, base_url=settings.base_url)
    else:
        # The status declared on the decorator is 201; the injected response is how the other
        # outcome is expressed without giving up the response model or the generated schema. No
        # `Location` here: nothing was created, so there is nothing for it to point at.
        response.status_code = HTTPStatus.OK

    return body


@router.get(
    "/links/{code}",
    response_model=LinkDetailsResponse,
    summary="Read a link and its click total",
    responses={
        HTTPStatus.NOT_FOUND: {
            "model": ProblemResponse,
            "description": "No link answers to that code, or it is not a code at all.",
        },
    },
)
def get_link_details(
    code: str,
    use_case: GetLinkDetailsUseCaseDep,
    settings: SettingsDep,
) -> LinkDetailsResponse:
    """Report a link's destination, when it was created, and how often it has been followed.

    Reading this records nothing. Asking how many times a link was followed is not following it,
    and a read that counted would change the number by being asked for it.

    The route is registered before the catch-all `GET /{code}`, which is what keeps `/links/abc`
    from being read as a seven-character code. `code` is a plain `str` here for the same reason
    the redirect takes one: the value frequently is not a code, and answering that case is the
    whole job.
    """
    return LinkDetailsResponse.from_result(use_case.get_details(code), base_url=settings.base_url)
