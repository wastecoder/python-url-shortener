"""A click is written once, never read back one by one, and never updated."""

import dataclasses
from datetime import UTC, datetime, timedelta, tzinfo
from ipaddress import ip_address

import pytest

from url_shortener.domain.model.click import Click


class UnknownOffset(tzinfo):
    """A timezone that does not know its own offset, which is a legal thing for one to be."""

    def utcoffset(self, dt: datetime | None) -> timedelta | None:
        return None

    def tzname(self, dt: datetime | None) -> str | None:
        return None

    def dst(self, dt: datetime | None) -> timedelta | None:
        return None


OCCURRED_AT = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def test_a_click_needs_only_the_link_and_the_instant() -> None:
    """
    Given a link id and an instant,
    when a Click is built,
    then it is accepted and everything an HTTP client owes nobody is absent.
    """
    click = Click(link_id=1, occurred_at=OCCURRED_AT)

    assert click.link_id == 1
    assert click.occurred_at == OCCURRED_AT
    assert click.user_agent is None
    assert click.referer is None
    assert click.ip is None


def test_a_click_records_what_the_request_carried() -> None:
    """
    Given a request with a user agent, a referer and an address,
    when a Click is built from it,
    then all three are kept, the address already parsed rather than left as text.
    """
    click = Click(
        link_id=1,
        occurred_at=OCCURRED_AT,
        user_agent="curl/8.5.0",
        referer="https://example.com/",
        ip=ip_address("203.0.113.7"),
    )

    assert click.user_agent == "curl/8.5.0"
    assert click.referer == "https://example.com/"
    assert click.ip == ip_address("203.0.113.7")


def test_a_click_is_built_by_keyword_only() -> None:
    """
    Given the two adjacent optional strings, user_agent and referer,
    when a Click is built positionally,
    then construction fails, so the two can never be transposed in silence.
    """
    with pytest.raises(TypeError):
        Click(1, OCCURRED_AT, "curl/8.5.0", "https://example.com/")  # type: ignore[call-arg]


@pytest.mark.parametrize("link_id", [0, -1])
def test_a_click_points_at_a_real_link_id(link_id: int) -> None:
    """
    Given a link id a sequence could never hand out,
    when a Click is built with it,
    then construction fails.
    """
    with pytest.raises(ValueError, match="starts at 1"):
        Click(link_id=link_id, occurred_at=OCCURRED_AT)


def test_a_naive_occurred_at_is_refused() -> None:
    """
    Given a datetime with no timezone,
    when a Click is built with it,
    then construction fails, for the same reason a link's creation instant needs one.
    """
    with pytest.raises(ValueError, match="timezone aware"):
        Click(link_id=1, occurred_at=datetime(2026, 8, 30, 12, 0))


def test_a_click_has_no_id_of_its_own() -> None:
    """
    Given the fields of a click,
    when they are listed,
    then there is no id: clicks are append-only and the only question ever asked of them is
    how many there are for a link, which is why the table has no counter to update either.
    """
    assert [field.name for field in dataclasses.fields(Click)] == [
        "link_id",
        "occurred_at",
        "user_agent",
        "referer",
        "ip",
    ]


def test_a_timezone_that_does_not_know_its_offset_is_refused() -> None:
    """
    Given a datetime carrying a timezone whose offset is unknown,
    when a Click is built with it,
    then construction fails, for the same reason it does on a link.
    """
    with pytest.raises(ValueError, match="timezone aware"):
        Click(link_id=1, occurred_at=datetime(2026, 8, 30, 12, 0, tzinfo=UnknownOffset()))


def test_a_click_is_frozen() -> None:
    """
    Given a recorded click,
    when one of its fields is assigned,
    then the assignment fails: a click is written once and never touched again, and the model
    says so rather than trusting every caller to remember it.
    """
    click = Click(link_id=1, occurred_at=OCCURRED_AT)

    with pytest.raises(dataclasses.FrozenInstanceError):
        click.link_id = 2  # type: ignore[misc]
