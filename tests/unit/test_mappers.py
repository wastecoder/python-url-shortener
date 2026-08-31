"""The conversion between rows and domain objects, which needs no database to be wrong.

These are pure functions over two plain objects, so the whole of this file runs with nothing up.
What it pins is the half of the persistence adapter that a Testcontainers test would exercise only
by accident: an integration test asserting that a redirect answers 302 passes just as well with a
mapper that silently drops `referer`.
"""

from datetime import datetime
from ipaddress import IPv4Address, IPv6Address

import pytest

from tests.mothers import CREATED_AT, MIXED_CASE_CODE, ClickMother, LinkMother, TargetUrlMother
from url_shortener.adapter.persistence.entity.click_entity import ClickEntity
from url_shortener.adapter.persistence.entity.link_entity import LinkEntity
from url_shortener.adapter.persistence.mapper import click_mapper, link_mapper
from url_shortener.domain.model.click import Click
from url_shortener.domain.model.link import Link
from url_shortener.domain.model.short_code import ShortCode
from url_shortener.domain.service.url_hash import hash_url

URL = TargetUrlMother.accepted()
DIGEST = hash_url(URL)

# The scenario every round trip here starts from: the link whose code carries digits and letters
# of both cases. `LinkMother.first()` would not do -- its code is `0000001`, and every assertion
# below would survive a mapper that upper-cased or lower-cased the column.
#
# The expected code is the mother's *literal*, while the link under test derives its own through
# `ShortCode.from_id`. Two independent statements of the same fact, which is what makes the
# comparison worth making.
CODE = MIXED_CASE_CODE


def _link() -> Link:
    """The link the round trips start from."""
    return LinkMother.with_a_mixed_case_code()


def _row(**overrides: object) -> LinkEntity:
    """A row of `link` as the database would hand it back, before any override."""
    values: dict[str, object] = {
        "id": _link().id,
        "code": CODE,
        "url": URL,
        "url_hash": DIGEST,
        "created_at": CREATED_AT,
    }
    return LinkEntity(**(values | overrides))


def test_a_link_survives_the_round_trip_unchanged() -> None:
    """
    Given a link written as a row,
    when that row is read back and converted,
    then it equals the link that was written -- the assertion that the two shapes really do carry
    the same facts, and not merely overlapping ones.
    """
    link = _link()

    values = link_mapper.to_values(link, url_hash=DIGEST)

    assert link_mapper.to_domain(LinkEntity(**values)) == link


def test_the_row_carries_every_column_the_table_has() -> None:
    """
    Given the columns of `link`,
    when the keys the mapper writes are compared against them,
    then they are the same set -- so a column added to the entity and forgotten here fails now,
    rather than as a NOT NULL violation on the first insert against a real database.
    """
    link = _link()

    written = set(link_mapper.to_values(link, url_hash=DIGEST))

    assert written == set(LinkEntity.__table__.columns.keys())


def test_the_digest_is_written_although_the_link_has_no_field_for_it() -> None:
    """
    Given a link, which carries no url_hash,
    when it is turned into a row,
    then the digest handed in beside it is what lands in the column -- the hash is an index key
    that persistence owns, and storing it on the domain object would be a second copy of it.
    """
    link = _link()

    assert link_mapper.to_values(link, url_hash=DIGEST)["url_hash"] == DIGEST
    assert not hasattr(link, "url_hash")


def test_the_code_is_written_as_text_and_read_back_as_a_short_code() -> None:
    """
    Given a link whose code is a ShortCode,
    when it crosses to the row and back,
    then the column holds a plain string and the domain object holds the checked type again.
    """
    link = _link()

    values = link_mapper.to_values(link, url_hash=DIGEST)

    assert values["code"] == CODE
    assert link_mapper.to_domain(LinkEntity(**values)).code == ShortCode(CODE)


def test_the_code_keeps_its_case_across_the_boundary() -> None:
    """
    Given two rows whose codes differ only in case,
    when each is converted,
    then they name two different links. Base 62 is case sensitive here, so a mapper that normalised
    the column would merge `hBxM5A3` and `HBXM5A3` into one link and send whoever followed the
    second one to somebody else's destination -- silently, and with every other test still green.
    """
    lower = link_mapper.to_domain(_row(code=CODE.lower()))
    upper = link_mapper.to_domain(_row(code=CODE.upper()))

    assert str(lower.code) == CODE.lower()
    assert str(upper.code) == CODE.upper()
    assert lower.code != upper.code


def test_a_row_whose_timestamp_lost_its_offset_is_refused() -> None:
    """
    Given a row whose created_at is naive,
    when it is converted,
    then Link refuses it -- which is what makes the TIMESTAMPTZ column and the Clock port one
    guarantee instead of two hopes. A naive instant reaching the domain is the classic silent date
    bug, and this is the boundary it would have to cross.
    """
    with pytest.raises(ValueError, match="timezone aware"):
        link_mapper.to_domain(_row(created_at=datetime(2026, 8, 31, 12, 0)))


def test_a_row_whose_code_is_not_a_code_is_refused() -> None:
    """
    Given a row carrying a code that is not seven base 62 characters,
    when it is converted,
    then ShortCode refuses it, and the failure is a ValueError rather than a DomainError -- a
    corrupt row is a bug in this system, so it must not be answerable as "no such link".
    """
    with pytest.raises(ValueError, match="exactly 7 characters"):
        link_mapper.to_domain(_row(code="nope"))


def test_a_click_is_written_without_an_id() -> None:
    """
    Given a click,
    when it is turned into a row,
    then no id is written: the column is BIGSERIAL and the database assigns it, and the domain has
    no field for it because nothing ever reads a click back.
    """
    click = ClickMother.on_link_id(7)

    written = set(click_mapper.to_values(click))

    assert "id" not in written
    assert written == set(ClickEntity.__table__.columns.keys()) - {"id"}


@pytest.mark.parametrize(
    "address",
    [IPv4Address("203.0.113.7"), IPv6Address("2001:db8::1"), None],
    ids=["ipv4", "ipv6", "absent"],
)
def test_the_address_crosses_unconverted(address: IPv4Address | IPv6Address | None) -> None:
    """
    Given a click carrying an address, of either family or none at all,
    when it is turned into a row,
    then the very same object is written -- psycopg understands `ipaddress` in both directions, so
    a `str()` here would only create the need for an `ip_address()` on the way back.
    """
    click = Click(link_id=7, occurred_at=CREATED_AT, ip=address)

    assert click_mapper.to_values(click)["ip"] is address


def test_the_optional_headers_are_written_as_they_arrived() -> None:
    """
    Given a click whose user agent is known and whose referer is not,
    when it is turned into a row,
    then both cross as they are -- an HTTP client owes neither header, and an absent one is a NULL
    rather than an empty string.
    """
    click = Click(link_id=7, occurred_at=CREATED_AT, user_agent="curl/8.5.0", referer=None)

    values = click_mapper.to_values(click)

    assert values["user_agent"] == "curl/8.5.0"
    assert values["referer"] is None
