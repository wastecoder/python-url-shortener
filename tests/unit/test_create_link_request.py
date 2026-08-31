"""The request body: what it refuses, and everything it deliberately does not judge."""

import pytest
from pydantic import ValidationError

from url_shortener.adapter.web.dto.request.create_link_request import CreateLinkRequest
from url_shortener.domain.service.url_policy import MAX_TARGET_URL_LENGTH


def test_the_url_arrives_as_the_string_that_was_sent() -> None:
    """
    Given a body carrying a URL,
    when it is parsed,
    then the value is the string itself and not a parsed URL object.
    """
    request = CreateLinkRequest.model_validate({"url": "https://example.com/a"})

    assert request.url == "https://example.com/a"
    assert type(request.url) is str


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "https://Example.com/A",
        "https://example.com/a?b=1&a=2",
        "https://example.com/a#fragment",
    ],
)
def test_nothing_is_normalised(url: str) -> None:
    """
    Given URLs that a URL type would rewrite -- no trailing slash, mixed case, query order,
    fragment,
    when they are parsed,
    then each one comes back byte for byte, which is what deduplication on the SHA-256 requires.
    """
    assert CreateLinkRequest.model_validate({"url": url}).url == url


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "http://localhost:8000/admin",
        "http://user:secret@example.com/",
        "not a url at all",
        "",
    ],
)
def test_the_policy_is_not_enforced_here(url: str) -> None:
    """
    Given a URL the domain policy refuses,
    when the body is parsed,
    then it is accepted, because deciding this is the domain's job and its answer is 400 with a
    reason -- not the 422 a validating model would produce.
    """
    assert CreateLinkRequest.model_validate({"url": url}).url == url


def test_a_url_longer_than_the_domain_limit_still_parses() -> None:
    """
    Given a URL past the 2048-character limit the domain policy enforces,
    when the body is parsed,
    then it is accepted here, because one limit written in two places is two limits.
    """
    url = "https://example.com/" + "a" * MAX_TARGET_URL_LENGTH

    assert len(CreateLinkRequest.model_validate({"url": url}).url) > MAX_TARGET_URL_LENGTH


def test_a_missing_url_is_refused() -> None:
    """
    Given a body with no url,
    when it is parsed,
    then validation fails, which is what makes the endpoint answer 422.
    """
    with pytest.raises(ValidationError):
        CreateLinkRequest.model_validate({})


def test_an_unknown_field_is_refused() -> None:
    """
    Given a body carrying a field this API does not accept,
    when it is parsed,
    then validation fails instead of ignoring it, so a misspelled name is never silent.
    """
    with pytest.raises(ValidationError):
        CreateLinkRequest.model_validate({"url": "https://example.com/a", "alias": "mine"})


@pytest.mark.parametrize("url", [1, None, ["https://example.com/a"], {"href": "x"}])
def test_a_url_that_is_not_a_string_is_refused(url: object) -> None:
    """
    Given a url that is not a string,
    when the body is parsed,
    then validation fails rather than coercing it, so nothing reaches the domain as a fake URL.
    """
    with pytest.raises(ValidationError):
        CreateLinkRequest.model_validate({"url": url})
