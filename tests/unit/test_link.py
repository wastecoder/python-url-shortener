"""A link knows its id, its code, where it points and when it was created."""

import dataclasses
from datetime import UTC, datetime, timedelta, timezone

import pytest

from url_shortener.domain.model.link import Link
from url_shortener.domain.model.short_code import ShortCode

CODE = ShortCode("0000001")
CREATED_AT = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def test_a_link_keeps_what_it_was_built_with() -> None:
    """
    Given an id, a code, a target URL and an instant,
    when a Link is built,
    then it holds all four exactly as they were given.
    """
    link = Link(id=1, code=CODE, url="https://example.com/a", created_at=CREATED_AT)

    assert link.id == 1
    assert link.code == CODE
    assert link.url == "https://example.com/a"
    assert link.created_at == CREATED_AT


def test_a_link_is_built_by_keyword_only() -> None:
    """
    Given the four fields in the declared order,
    when a Link is built positionally,
    then construction fails, so no caller can silently transpose two of them.
    """
    with pytest.raises(TypeError):
        Link(1, CODE, "https://example.com", CREATED_AT)  # type: ignore[misc]


@pytest.mark.parametrize("link_id", [0, -1])
def test_a_link_id_comes_from_a_sequence_and_starts_at_one(link_id: int) -> None:
    """
    Given an id a sequence could never hand out,
    when a Link is built with it,
    then construction fails.
    """
    with pytest.raises(ValueError, match="starts at 1"):
        Link(id=link_id, code=CODE, url="https://example.com", created_at=CREATED_AT)


@pytest.mark.parametrize("url", ["", "   "])
def test_a_link_needs_somewhere_to_point(url: str) -> None:
    """
    Given a blank target URL,
    when a Link is built with it,
    then construction fails: a link with no destination is not a link.
    """
    with pytest.raises(ValueError, match="target URL"):
        Link(id=1, code=CODE, url=url, created_at=CREATED_AT)


def test_a_naive_created_at_is_refused() -> None:
    """
    Given a datetime with no timezone,
    when a Link is built with it,
    then construction fails, because a naive instant means a different moment on every machine.
    """
    with pytest.raises(ValueError, match="timezone aware"):
        Link(
            id=1,
            code=CODE,
            url="https://example.com",
            created_at=datetime(2026, 8, 30, 12, 0),
        )


def test_an_aware_instant_in_another_offset_is_accepted() -> None:
    """
    Given the same instant written with a -03:00 offset,
    when a Link is built with it,
    then it is accepted and equals its UTC twin: the rule is "unambiguous", not "labelled UTC".
    """
    in_brasilia = datetime(2026, 8, 30, 9, 0, tzinfo=timezone(timedelta(hours=-3)))

    link = Link(id=1, code=CODE, url="https://example.com", created_at=in_brasilia)

    assert link.created_at == CREATED_AT


def test_a_link_is_frozen_and_its_copies_are_validated_again() -> None:
    """
    Given a link,
    when a field is assigned, and when a copy is made with an impossible id,
    then both fail, so the invariants hold for every instance that exists.
    """
    link = Link(id=1, code=CODE, url="https://example.com", created_at=CREATED_AT)

    with pytest.raises(dataclasses.FrozenInstanceError):
        link.url = "https://elsewhere.com"  # type: ignore[misc]

    with pytest.raises(ValueError, match="starts at 1"):
        dataclasses.replace(link, id=0)


def test_a_link_does_not_carry_the_hash_of_its_url() -> None:
    """
    Given the fields of a link,
    when they are listed,
    then there is no url_hash: the hash is a fixed-size index key, computed before any link
    exists, and a second copy of the URL here could only ever disagree with the first.
    """
    assert [field.name for field in dataclasses.fields(Link)] == [
        "id",
        "code",
        "url",
        "created_at",
    ]
