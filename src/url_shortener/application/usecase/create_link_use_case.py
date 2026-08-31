"""Shorten a URL, or hand back the link it already has."""

from url_shortener.application.port.outbound.clock import Clock
from url_shortener.application.port.outbound.link_repository import LinkRepository
from url_shortener.application.viewmodel.create_link_command import CreateLinkCommand
from url_shortener.application.viewmodel.link_result import LinkResult
from url_shortener.domain.model.link import Link
from url_shortener.domain.model.short_code import ShortCode
from url_shortener.domain.service.url_hash import hash_url
from url_shortener.domain.service.url_policy import validate_target_url


class CreateLinkUseCaseImpl:
    """The four-step deduplication flow, and the order of its steps is the design.

    The ports arrive through the constructor and are stored privately. There is no framework doing
    this and no container: the wiring happens once, by hand, in the web adapter. It is deliberately
    not a frozen dataclass either -- in this project a frozen dataclass means "a value", and a use
    case is behaviour with collaborators, not a value whose `__eq__` compares two repositories.
    """

    def __init__(self, links: LinkRepository, clock: Clock) -> None:
        self._links = links
        self._clock = clock

    def create(self, command: CreateLinkCommand) -> LinkResult:
        """Shorten the URL, returning the existing link when this URL already has one."""
        # Refuse the target before anything is spent. First, and not merely early: `next_id` moves
        # a sequence even inside a transaction that rolls back, so validating later would let a
        # rejected URL burn a code that nothing will ever answer to.
        validate_target_url(command.url)

        # The fixed-size key the unique index is built on, and the only thing looked up by.
        url_hash = hash_url(command.url)

        # The fast path. A URL that already has a link comes straight back, with no id spent and
        # no write attempted -- which is what makes shortening the same URL twice cheap.
        existing = self._links.find_by_url_hash(url_hash)
        if existing is not None:
            return _as_result(existing, was_created=False)

        # Only now is an id taken. It comes back *before* the insert, which is what lets the code
        # be computed here, in the pure domain, and the row be written with `code NOT NULL` in a
        # single statement instead of an insert followed by an update.
        link_id = self._links.next_id()
        link = Link(
            id=link_id,
            code=ShortCode.from_id(link_id),
            url=command.url,
            created_at=self._clock.now(),
        )

        # `INSERT ... ON CONFLICT (url_hash) DO NOTHING`, and never a check-then-insert: between
        # the lookup above finding nothing and this statement, another request can insert the same
        # URL. Only the unique constraint closes that window, so the answer to losing is a value
        # to handle and not a failure.
        if self._links.save(link, url_hash=url_hash):
            return _as_result(link, was_created=True)

        # We lost. Read the winner and answer with it -- never with `link`, whose id and code were
        # never written and therefore name nothing. The sequence value spent above becomes a gap,
        # which is expected: the sequence is an id generator, not a count of links.
        winner = self._links.find_by_url_hash(url_hash)
        if winner is None:
            # Not reachable under READ COMMITTED, which the engine pins: `ON CONFLICT DO NOTHING`
            # waits on the conflicting inserter, so if that transaction aborted this insert
            # proceeds instead, and if it committed the next statement takes a fresh snapshot that
            # sees it -- and nothing in V1 ever deletes a link.
            #
            # Nor under REPEATABLE READ, and that correction was measured rather than reasoned.
            # This comment used to claim the opposite: that a repeatable-read snapshot would make
            # the re-read find nothing. It would not, because the re-read never happens -- there
            # the losing INSERT itself raises `SerializationFailure`, so the flow fails one line
            # earlier and answers 500. The isolation level is not a nuance of this branch; it is a
            # precondition of the whole deduplication design, which is why it is pinned on the
            # engine instead of inherited from a server default.
            #
            # So the guard covers no path this project can produce, and it stays: it costs one
            # branch, and without it a `None` would flow into `_as_result` and fail further away
            # from its cause. An `if` and not an `assert`, because `-O` removes assertions exactly
            # when they would matter.
            raise RuntimeError(
                f"the unique index refused the insert for url hash {url_hash}, "
                "and then no row carried that hash"
            )
        return _as_result(winner, was_created=False)


def _as_result(link: Link, *, was_created: bool) -> LinkResult:
    """Carry a link across the boundary, leaving the domain type behind.

    A module-private function and deliberately not a `LinkResult.from_link` classmethod. The
    viewmodel package exists so that a domain object never reaches an adapter; giving the viewmodel
    a constructor that reads a `Link` would make it import exactly what it is there to stop, and
    the boundary contract in `.importlinter` would break on that import.
    """
    return LinkResult(
        code=str(link.code),
        url=link.url,
        created_at=link.created_at,
        was_created=was_created,
    )
