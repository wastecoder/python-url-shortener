"""What the application needs a store of links to be able to do."""

from typing import Protocol

from url_shortener.domain.model.link import Link
from url_shortener.domain.model.short_code import ShortCode
from url_shortener.domain.service.url_hash import UrlHash


class LinkRepository(Protocol):
    """The four questions the use cases ask of stored links.

    A `Protocol` and not an ABC: the adapter satisfies this structurally, without importing or
    inheriting anything from `application`, which is what keeps the dependency arrow pointing
    inward. It is deliberately not `@runtime_checkable` either -- an `isinstance` check against a
    runtime-checkable Protocol compares method *names* and nothing about signatures, so it would
    happily accept a `save` that returns a string. The check that means something is `mypy`.

    There is no `commit` and no `flush` here, and no `UnitOfWork` beside it. That is decided now
    rather than discovered later: a use case able to commit is a use case able to commit half a
    flow, and the method would mean nothing at all to an in-memory implementation. The transaction
    belongs to the request edge, in the adapter.
    """

    def next_id(self) -> int:
        """Take the next value of the link id sequence, before anything is inserted.

        Reading the id first is what allows the code to be computed in the pure domain and the
        row to be written with `code NOT NULL` in a single statement. A value taken here is spent
        whether or not a row follows, so a rolled-back request leaves a gap -- expected, and
        harmless: the sequence is an id generator, not a count of links.
        """
        ...

    def find_by_code(self, code: ShortCode) -> Link | None:
        """The link that answers to this code, or `None`.

        It takes a `ShortCode` and not a `str` on purpose. By the time the question is worth
        asking, the string has been proved to be a code, so the garbage that reaches the catch-all
        redirect route never becomes a database round trip.
        """
        ...

    def find_by_url_hash(self, url_hash: UrlHash) -> Link | None:
        """The link already pointing at the URL behind this digest, or `None`.

        This is both step 2 of the deduplication flow -- the fast path, before any id is spent --
        and step 4, the re-read that finds whoever won the race.
        """
        ...

    def save(self, link: Link, *, url_hash: UrlHash) -> bool:
        """Insert the link, doing nothing if its URL already has one. `False` means it already did.

        `False` says exactly one thing: the unique index on the digest refused this row because
        another request got there first. It is an ordinary outcome of a correct concurrent system,
        not a failure, which is why it is a return value and not an exception -- an exception would
        put the deduplication path in every stack trace, and an `IntegrityError` crossing this port
        would drag the database driver into `application`.

        The digest travels beside the link rather than inside it because `Link` has no `url_hash`
        field: the hash is a fixed-size index key, and the caller computed this exact one a few
        lines earlier for the lookup. It is keyword-only because that is what makes a type checker
        verify the *name* against an implementation -- for an ordinary positional parameter, mypy
        checks the type and lets the name drift.

        The implementation resolves the conflict on `url_hash` and never on `code`: a duplicate
        code is impossible by construction, so a collision there must stay loud.
        """
        ...
