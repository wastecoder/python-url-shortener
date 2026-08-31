"""The `link` table, behind the `LinkRepository` port."""

from typing import Final

from sqlalchemy import ColumnElement, Select, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import ReturningInsert

from url_shortener.adapter.persistence.entity.link_entity import LINK_ID_SEQUENCE, LinkEntity
from url_shortener.adapter.persistence.mapper import link_mapper
from url_shortener.domain.model.link import Link
from url_shortener.domain.model.short_code import ShortCode
from url_shortener.domain.service.url_hash import UrlHash

# `SELECT nextval('link_id_seq')`. A `Select` is immutable once built, so one is enough for the
# life of the process.
NEXT_ID_STATEMENT: Final[Select[tuple[int]]] = select(LINK_ID_SEQUENCE.next_value())


def insert_link_statement(values: dict[str, object]) -> ReturningInsert[tuple[int]]:
    """`INSERT ... ON CONFLICT (url_hash) DO NOTHING RETURNING link.id`.

    Built by a named function rather than inline in `save`, so that the one statement carrying this
    project's deduplication argument can be compiled and read in a unit test. Asserting it through
    a real database would need the Docker that the fast suite exists to do without, and asserting
    it by reading the source is not asserting it.

    **The conflict target is `url_hash`, and never `code`.** A duplicate code is impossible by
    construction -- a monotonic sequence through a bijective encoding -- so a collision there has to
    stay loud. Widening this to `on_conflict_do_nothing()` with no target would silence it.

    **`RETURNING`, and never `rowcount`.** They are not two ways to learn the same thing here. For
    an `INSERT` without `RETURNING`, SQLAlchemy does not memoise the row count and soft-closes the
    cursor, and psycopg resets its `rowcount` to `-1` on close -- so the value would be read off a
    dead cursor and would never be the `0` that a suppressed conflict is supposed to produce. The
    returned id is a row or an absence, and an absence is unambiguous.
    """
    return (
        insert(LinkEntity)
        .values(**values)
        .on_conflict_do_nothing(index_elements=[LinkEntity.url_hash])
        .returning(LinkEntity.id)
    )


class LinkRepositoryImpl:
    """The four questions of the port, answered by PostgreSQL.

    It does not inherit from `LinkRepository`, and cannot: the port is a `Protocol` in
    `application`, and importing it here would point the dependency arrow outward. Conformance is
    structural, and `dependencies.py` is where a type checker reads it -- the provider returning
    this class is annotated with the port.

    There is no `commit` here and no `flush`. The transaction is opened and closed at the request
    edge, one per request, and this object only ever writes into the one it was handed. ADR-0007.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def next_id(self) -> int:
        """Take the next value of the sequence, before anything is inserted.

        Reading the id first is what lets the code be computed in the pure domain and the row be
        written with `code NOT NULL` in a single statement.

        A sequence does not obey rollback: this value is spent whether or not a row follows, so a
        request that fails afterwards leaves a gap. That is expected and harmless -- the sequence is
        an id generator, not a count of links -- and it is why the target URL is validated before
        this is ever called.
        """
        return self._session.execute(NEXT_ID_STATEMENT).scalar_one()

    def find_by_code(self, code: ShortCode) -> Link | None:
        """The link that answers to this code, or `None`."""
        return self._find(LinkEntity.code == str(code))

    def find_by_url_hash(self, url_hash: UrlHash) -> Link | None:
        """The link already pointing at the URL behind this digest, or `None`.

        Both step 2 of the deduplication flow -- the fast path, before any id is spent -- and step
        4, the re-read that finds whoever won the race.
        """
        return self._find(LinkEntity.url_hash == url_hash)

    def save(self, link: Link, *, url_hash: UrlHash) -> bool:
        """Insert the link unless its URL already has one. `False` means it already did.

        `False` is an ordinary outcome of a correct concurrent system and not a failure, which is
        why it is a return value: an exception would put the deduplication path in every stack
        trace, and letting an `IntegrityError` escape would drag the driver into `application`.

        The insert is issued here and now. Only the `COMMIT` waits for the request edge, so a
        constraint or connectivity failure still raises inside the use case that called this.
        """
        statement = insert_link_statement(link_mapper.to_values(link, url_hash=url_hash))
        return self._session.execute(statement).scalar_one_or_none() is not None

    def _find(self, criterion: ColumnElement[bool]) -> Link | None:
        """One row of `link` as a domain object, or `None`.

        `scalar_one_or_none` rather than `first`: both columns searched on are unique, so more than
        one row is an impossibility, and this is the call that says so out loud instead of quietly
        picking one.
        """
        entity = self._session.execute(select(LinkEntity).where(criterion)).scalar_one_or_none()
        return None if entity is None else link_mapper.to_domain(entity)
