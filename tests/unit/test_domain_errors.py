"""The domain errors: they carry a reason, and they know nothing about HTTP."""

import json

import pytest

from url_shortener.domain.exception.domain_error import DomainError
from url_shortener.domain.exception.invalid_target_url_error import InvalidTargetUrlError
from url_shortener.domain.exception.link_not_found_error import LinkNotFoundError
from url_shortener.domain.exception.rejection_reason import RejectionReason
from url_shortener.domain.exception.reserved_code_error import ReservedCodeError

DOMAIN_ERRORS: list[DomainError] = [
    InvalidTargetUrlError(RejectionReason.MISSING_HOST, "the URL has no host"),
    LinkNotFoundError("zzzzzzz"),
    ReservedCodeError("docs"),
]


@pytest.mark.parametrize("error", DOMAIN_ERRORS)
def test_every_domain_error_descends_from_domain_error(error: DomainError) -> None:
    """
    Given any error the domain raises,
    when its type is inspected,
    then it is a DomainError, so a single except clause catches the whole family.
    """
    assert isinstance(error, DomainError)
    assert isinstance(error, Exception)


def test_a_domain_error_is_not_a_value_error() -> None:
    """
    Given the base of the hierarchy,
    when it is compared to ValueError,
    then the two are unrelated, so catching one never swallows the other.
    """
    assert not issubclass(DomainError, ValueError)


@pytest.mark.parametrize("error", DOMAIN_ERRORS)
@pytest.mark.parametrize("attribute", ["status", "status_code", "http_status", "problem_type"])
def test_no_domain_error_knows_what_a_status_code_is(error: DomainError, attribute: str) -> None:
    """
    Given any error the domain raises,
    when it is asked for an HTTP attribute,
    then it has none: translating a domain error into a response belongs to the web adapter.
    """
    assert not hasattr(error, attribute)


@pytest.mark.parametrize("error", DOMAIN_ERRORS)
def test_the_message_is_readable_as_text_and_as_an_attribute(error: DomainError) -> None:
    """
    Given any error the domain raises,
    when it is rendered as text,
    then the rendering is the same message the error exposes as an attribute.
    """
    assert str(error) == error.message
    assert error.message != ""


def test_an_invalid_target_url_carries_the_reason_and_the_sentence() -> None:
    """
    Given a URL refused because of its scheme,
    when the error is inspected,
    then it carries the machine reason and a sentence naming the offending scheme.
    """
    error = InvalidTargetUrlError(
        RejectionReason.UNSUPPORTED_SCHEME,
        "the scheme 'file' is not accepted; only http and https are",
    )

    assert error.reason is RejectionReason.UNSUPPORTED_SCHEME
    assert "file" in error.message


def test_a_link_not_found_error_names_the_code_that_was_asked_for() -> None:
    """
    Given a code that resolves to nothing,
    when the error is inspected,
    then it carries the raw code, which is not required to be a valid short code.
    """
    error = LinkNotFoundError("not-a-code")

    assert error.code == "not-a-code"
    assert "not-a-code" in error.message


def test_a_reserved_code_error_names_the_code_the_api_keeps() -> None:
    """
    Given a code the API owns as a route,
    when the error is inspected,
    then it carries that code.
    """
    error = ReservedCodeError("health")

    assert error.code == "health"
    assert "health" in error.message


def test_a_rejection_reason_travels_as_a_plain_string() -> None:
    """
    Given a rejection reason,
    when it is serialised as JSON,
    then it comes out as its hyphenated value, with no custom encoder.
    """
    body = json.dumps({"reason": RejectionReason.CREDENTIALS_IN_URL})

    assert body == '{"reason": "credentials-in-url"}'


def test_the_rejection_reasons_are_a_hyphenated_wire_taxonomy() -> None:
    """
    Given every member of the taxonomy,
    when the values are inspected,
    then each is lower case and hyphenated, and no two members share a value.
    """
    # Read through __members__ and not by iterating the enum: two members declared with the same
    # value are not two members at all, they are one member and an alias, and iteration shows
    # only the first -- which would make an assertion about duplicates unable to ever fail.
    values = [member.value for member in RejectionReason.__members__.values()]

    assert len(set(values)) == len(RejectionReason.__members__)
    assert all(value == value.lower() for value in values)
    assert all("_" not in value for value in values)
