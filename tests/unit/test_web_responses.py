"""The response models: what they copy from a viewmodel, and what they add or leave out."""

from datetime import UTC, datetime

from url_shortener.adapter.web.dto.response.health_response import HealthResponse
from url_shortener.adapter.web.dto.response.link_details_response import LinkDetailsResponse
from url_shortener.adapter.web.dto.response.link_response import LinkResponse
from url_shortener.adapter.web.dto.response.problem_response import FieldError, ProblemResponse
from url_shortener.application.viewmodel.link_details_result import LinkDetailsResult
from url_shortener.application.viewmodel.link_result import LinkResult

BASE_URL = "https://sho.rt"
CREATED_AT = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
CODE = "000000b"
TARGET = "https://example.com/a"


def _link_result(*, was_created: bool = True) -> LinkResult:
    return LinkResult(code=CODE, url=TARGET, created_at=CREATED_AT, was_created=was_created)


def _details_result(total_clicks: int = 3) -> LinkDetailsResult:
    return LinkDetailsResult(
        code=CODE, url=TARGET, created_at=CREATED_AT, total_clicks=total_clicks
    )


def test_the_link_body_carries_the_four_fields_of_the_contract() -> None:
    """
    Given a use case result,
    when it is rendered for POST /links,
    then the body is exactly code, short_url, url and created_at.
    """
    body = LinkResponse.from_result(_link_result(), base_url=BASE_URL)

    assert body.model_dump() == {
        "code": CODE,
        "short_url": f"{BASE_URL}/{CODE}",
        "url": TARGET,
        "created_at": CREATED_AT,
    }


def test_the_link_body_never_carries_whether_it_was_created() -> None:
    """
    Given two results that differ only in was_created,
    when both are rendered,
    then the bodies are identical, because that fact is carried by the status code alone.
    """
    created = LinkResponse.from_result(_link_result(was_created=True), base_url=BASE_URL)
    existing = LinkResponse.from_result(_link_result(was_created=False), base_url=BASE_URL)

    assert created == existing
    assert "was_created" not in created.model_dump()


def test_the_details_body_adds_the_click_total() -> None:
    """
    Given a details result,
    when it is rendered for GET /links/{code},
    then the body is the link body plus total_clicks.
    """
    body = LinkDetailsResponse.from_result(_details_result(), base_url=BASE_URL)

    assert body.model_dump() == {
        "code": CODE,
        "short_url": f"{BASE_URL}/{CODE}",
        "url": TARGET,
        "created_at": CREATED_AT,
        "total_clicks": 3,
    }


def test_both_bodies_build_the_short_url_from_the_configured_origin() -> None:
    """
    Given a different origin,
    when either body is rendered,
    then the short URL follows the setting, because the API never guesses the host it answers on.
    """
    link = LinkResponse.from_result(_link_result(), base_url="http://localhost:8000")
    details = LinkDetailsResponse.from_result(_details_result(), base_url="http://localhost:8000")

    assert link.short_url == f"http://localhost:8000/{CODE}"
    assert details.short_url == f"http://localhost:8000/{CODE}"


def test_the_health_body_is_one_field() -> None:
    """
    Given the health model,
    when it is rendered,
    then it carries only the status, which is a static ok until Fase 4 checks the database.
    """
    assert HealthResponse(status="ok").model_dump() == {"status": "ok"}


def test_a_problem_body_leaves_out_the_extension_members_it_has_nothing_to_say_in() -> None:
    """
    Given a problem with no reason and no field errors,
    when it is serialised the way the handlers serialise it,
    then the optional members are absent rather than present and null.
    """
    problem = ProblemResponse(
        type="link-not-found",
        title="No link answers to that code",
        status=404,
        detail="no link exists for code 'zzzzzzz'",
        instance="/zzzzzzz",
    )

    assert problem.model_dump(mode="json", exclude_none=True) == {
        "type": "link-not-found",
        "title": "No link answers to that code",
        "status": 404,
        "detail": "no link exists for code 'zzzzzzz'",
        "instance": "/zzzzzzz",
    }


def test_a_problem_body_carries_the_extension_members_that_do_say_something() -> None:
    """
    Given a problem carrying a refusal reason and a field error,
    when it is serialised,
    then both extension members survive, each in the shape a client can branch on.
    """
    problem = ProblemResponse(
        type="validation-error",
        title="The request body is not valid",
        status=422,
        detail="the payload does not match the schema",
        instance="/links",
        reason="non-public-host",
        errors=[FieldError(field="body.url", message="Field required", type="missing")],
    )

    serialised = problem.model_dump(mode="json", exclude_none=True)

    assert serialised["reason"] == "non-public-host"
    assert serialised["errors"] == [
        {"field": "body.url", "message": "Field required", "type": "missing"}
    ]
