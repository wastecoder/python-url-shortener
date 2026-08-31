"""In-memory stand-ins for the driven ports, so the use cases can be tested with nothing running.

**Fakes, not mocks.** A mock would let a test assert that `save` was called; these let a test
assert what is stored afterwards, which is the only thing the caller of the API can observe. The
difference stops being academic in the deduplication test: `POST` the same URL twice and the
question is "how many links exist", not "how many times was save called". A mock answers the
second question and calls it proof.

Nothing here inherits from a port. Conformance is structural, and it is checked by `mypy` at the
bottom of this file -- which is why `pyproject.toml` points `mypy` at `tests` as well as `src`.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from url_shortener.domain.model.click import Click
from url_shortener.domain.model.link import Link
from url_shortener.domain.model.short_code import ShortCode
from url_shortener.domain.service.url_hash import UrlHash


class InMemoryLinkRepository:
    """The `link` table as two dictionaries and a counter.

    The two dictionaries are the two unique indexes that matter: one on the URL digest, which is
    what deduplication rides on, and one on the code, which is how the redirect finds a link.
    """

    def __init__(self) -> None:
        self.issued_ids: list[int] = []
        self._by_hash: dict[UrlHash, Link] = {}
        self._by_code: dict[ShortCode, Link] = {}
        self._pending_rival: tuple[Link, UrlHash] | None = None

    def insert_before_next_save(self, rival: Link, *, url_hash: UrlHash) -> None:
        """Arrange for another request to commit `rival` inside the race window.

        In production the window is between the `SELECT` that found nothing and the `INSERT`. This
        drops a competing writer into exactly that gap, with no threads, no sleeps and nothing to
        go flaky.

        Note what it deliberately is *not*: a "make the next save return False" flag. A flag would
        only ever test the flag. Here the `False` falls out of this store's own uniqueness rule,
        at the same moment the database's unique index would have produced it. It fires once and
        clears itself, because a race is a moment and not a condition.
        """
        self._pending_rival = (rival, url_hash)

    def next_id(self) -> int:
        """Hand out the next sequence value, spent whether or not a row follows."""
        link_id = len(self.issued_ids) + 1
        self.issued_ids.append(link_id)
        return link_id

    def find_by_code(self, code: ShortCode) -> Link | None:
        """The link answering to this code, or `None`."""
        return self._by_code.get(code)

    def find_by_url_hash(self, url_hash: UrlHash) -> Link | None:
        """The link already pointing at the URL behind this digest, or `None`."""
        return self._by_hash.get(url_hash)

    def save(self, link: Link, *, url_hash: UrlHash) -> bool:
        """Insert unless the digest is taken, exactly as `ON CONFLICT (url_hash) DO NOTHING` does.

        The unique index on `code` is deliberately not modelled. `next_id` is monotonic and
        `ShortCode.from_id` is a bijection, so a code collision cannot happen here -- a branch for
        it would be dead code that the coverage gate then has to be told to ignore, and it would
        have to invent a failure the real repository signals in a completely different way.
        """
        if self._pending_rival is not None:
            rival, rival_hash = self._pending_rival
            self._pending_rival = None
            self._insert(rival, rival_hash)

        if url_hash in self._by_hash:
            return False

        self._insert(link, url_hash)
        return True

    @property
    def rows(self) -> tuple[Link, ...]:
        """Everything stored, in insertion order, as a tuple a test cannot edit."""
        return tuple(self._by_hash.values())

    def _insert(self, link: Link, url_hash: UrlHash) -> None:
        self._by_hash[url_hash] = link
        self._by_code[link.code] = link


class InMemoryClickRepository:
    """The `click` table as a list, which is all an append-only table needs."""

    def __init__(self) -> None:
        self._recorded: list[Click] = []

    def record(self, click: Click) -> None:
        """Append one access. Nothing is ever updated or removed."""
        self._recorded.append(click)

    def count_by_link(self, link_id: int) -> int:
        """Count the accesses of one link by scanning, never by keeping a running total.

        A maintained counter here would be the exact design the schema refuses, and it would hide
        a double count on the write path behind a number that always looks plausible.
        """
        return sum(1 for click in self._recorded if click.link_id == link_id)

    @property
    def recorded(self) -> tuple[Click, ...]:
        """Every click appended so far, in order, as a tuple a test cannot edit."""
        return tuple(self._recorded)


class FixedClock:
    """A clock stuck at one instant, so a test can assert the exact value that was written."""

    def __init__(self, instant: datetime) -> None:
        if instant.utcoffset() is None:
            raise ValueError(f"a fixed clock needs an aware instant, got {instant!r}")
        self._instant = instant

    def now(self) -> datetime:
        """The instant this clock was built with, every time."""
        return self._instant


if TYPE_CHECKING:
    # The conformance proof, and the reason `mypy` reads `tests` and not only `src`. These three
    # assignments never run -- `TYPE_CHECKING` is `False` at runtime -- so they cost nothing at
    # import time and nothing in coverage, and they exist so that a fake drifting away from its
    # port fails `uv run mypy` on the line that names the port, with the conflicting member and
    # both signatures printed.
    #
    # The alternative, `@runtime_checkable` plus `isinstance`, is worth less than it looks: it
    # checks that the methods exist and nothing about their signatures or return types, so it
    # would accept a `save` that returns a string. Instances rather than `type[Port] = Fake`,
    # because the instance form is the one that prints the conflicting member.
    #
    # There is no equivalent block for the driving ports: each use case test builds its subject
    # through a helper annotated with the inbound port, which is the same proof for free.
    from url_shortener.application.port.outbound.click_repository import ClickRepository
    from url_shortener.application.port.outbound.clock import Clock
    from url_shortener.application.port.outbound.link_repository import LinkRepository

    _links: LinkRepository = InMemoryLinkRepository()
    _clicks: ClickRepository = InMemoryClickRepository()
    _clock: Clock = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
