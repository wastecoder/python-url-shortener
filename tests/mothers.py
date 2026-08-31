"""Object Mothers: the scenarios this project's tests keep needing, each one named once.

A mother hands back a **finished object in a named scenario** -- `LinkMother.first()`,
`TargetUrlMother.refused()` -- and never a half-built one a caller has to finish. That is the whole
difference from a builder, and it is why there is no builder here: a builder moves the arrangement
into the test and hands every test the freedom to spell the same scenario differently, which is how
`Link(id=1, code=ShortCode.from_id(1), ...)` came to appear in six files.

**Shape, and what it costs to translate.** The Java pattern this project mirrors is a final class
with a private constructor and static factories. Python has neither keyword, so both are written
out: `@final` is enforced by `mypy` rather than by the interpreter, and the private constructor is
an `__init__` that raises -- there is nothing here worth instantiating, and the exception says so
at the moment somebody tries rather than handing back a useless object.

**What is deliberately not here.** The values the SQL tests compile against are dicts of columns,
not domain objects, and `test_link.py` and `test_click.py` build their subjects by hand because the
constructor's own refusals are what they test. A mother in either place would hide the thing under
test.
"""

from datetime import UTC, datetime
from ipaddress import IPv4Address
from typing import Final, NoReturn, final

from url_shortener.domain.model.click import Click
from url_shortener.domain.model.link import Link
from url_shortener.domain.model.short_code import ShortCode

# The instant every link and click below is stamped with, exported so a test can assert against it
# without asking an object what it was given. Microseconds and a non-zero minute on purpose: an
# assertion against a whole second survives a mapper that truncates, and `TIMESTAMPTZ` keeps them.
CREATED_AT: Final = datetime(2026, 8, 31, 12, 34, 56, 789012, tzinfo=UTC)

# An id whose base 62 code carries letters of **both** cases. It exists because the obvious id, 1,
# encodes to `0000001` -- all digits -- and every assertion about a code would survive a mapper or
# a repository that upper-cased or lower-cased it. Base 62 is case sensitive here: `aaaaaaa` and
# `AAAAAAA` are two different links.
MIXED_CASE_ID: Final = 999_999_999_999
MIXED_CASE_CODE: Final = "hBxM5A3"


def _no_instances(owner: str) -> NoReturn:
    """Refuse to build a mother, and say what to do instead."""
    raise TypeError(f"{owner} is a namespace of scenarios; call its factories, do not instantiate")


@final
class TargetUrlMother:
    """The target URLs, each named by what the domain policy does with it."""

    def __init__(self) -> None:
        _no_instances(type(self).__name__)

    @staticmethod
    def accepted() -> str:
        """A URL the policy accepts: https, a public host, nothing unusual in it."""
        return "https://example.com/a-fairly-long-target"

    @staticmethod
    def another_accepted() -> str:
        """A second accepted URL, different from the first byte for byte.

        Different *as a string*, which is the only thing deduplication compares -- the policy
        normalises nothing, so two spellings of one address really are two links.
        """
        return "https://example.org/somewhere-else"

    @staticmethod
    def refused() -> str:
        """The cloud metadata address, refused with `non-public-address`.

        Not an arbitrary bad URL. `169.254.169.254` is the address that makes an open shortener a
        way of asking a server to fetch its own instance credentials, so it is the refusal worth
        naming.
        """
        return "http://169.254.169.254/latest/meta-data/"


@final
class LinkMother:
    """Links in the states this project's tests actually need."""

    def __init__(self) -> None:
        _no_instances(type(self).__name__)

    @staticmethod
    def first() -> Link:
        """The link a database with nothing in it produces: id 1, code `0000001`."""
        return LinkMother.with_id(1)

    @staticmethod
    def with_id(link_id: int, *, url: str | None = None) -> Link:
        """The link that id produces, with its code derived rather than written out.

        Derived through `ShortCode.from_id`, which is what production does. Writing the expected
        code here instead would make every test that uses this mother agree with the encoder by
        construction, and none of them would notice it changing.
        """
        return Link(
            id=link_id,
            code=ShortCode.from_id(link_id),
            url=url if url is not None else TargetUrlMother.accepted(),
            created_at=CREATED_AT,
        )

    @staticmethod
    def pointing_at(url: str) -> Link:
        """The first link of a database, pointing wherever the test needs it to."""
        return LinkMother.with_id(1, url=url)

    @staticmethod
    def with_a_mixed_case_code() -> Link:
        """The link whose code carries upper and lower case letters and digits at once.

        The scenario that catches a boundary normalising case, which `first()` cannot: its code is
        `0000001`, and every assertion about it survives an `.upper()`.
        """
        return LinkMother.with_id(MIXED_CASE_ID)


@final
class ClickMother:
    """Accesses to a link, from the bare one to the one carrying everything."""

    def __init__(self) -> None:
        _no_instances(type(self).__name__)

    @staticmethod
    def on(link: Link) -> Click:
        """An access with nothing but the two things a click cannot exist without."""
        return ClickMother.on_link_id(link.id)

    @staticmethod
    def on_link_id(link_id: int) -> Click:
        """The same bare access, for a test that has an id and no link object."""
        return Click(link_id=link_id, occurred_at=CREATED_AT)

    @staticmethod
    def fully_described(link: Link) -> Click:
        """An access carrying every optional field, so a boundary dropping one is visible.

        An HTTP client owes none of the three, which is why the bare scenario above exists too --
        and why a test asserting the round trip has to use this one, since a mapper that silently
        dropped `referer` would pass against a click that never had one.
        """
        return Click(
            link_id=link.id,
            occurred_at=CREATED_AT,
            user_agent="curl/8.5.0",
            referer="https://example.net/whence",
            ip=IPv4Address("203.0.113.7"),
        )
