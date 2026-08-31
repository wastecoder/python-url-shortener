"""The `click` table, behind the `ClickRepository` port."""

from sqlalchemy import Insert, Select, func, insert, select
from sqlalchemy.orm import Session

from url_shortener.adapter.persistence.entity.click_entity import ClickEntity
from url_shortener.adapter.persistence.mapper import click_mapper
from url_shortener.domain.model.click import Click


def insert_click_statement(values: dict[str, object]) -> Insert:
    """A plain `INSERT INTO click`, with nothing conditional about it.

    `sqlalchemy.insert` and deliberately not the PostgreSQL one next door, because there is no
    `ON CONFLICT` here and there must never be: two identical accesses to the same link *are* two
    accesses, and a conflict clause on this table would silently discard the second. The only
    statement in this project that suppresses a conflict is the one that deduplicates links.
    """
    return insert(ClickEntity).values(**values)


def count_statement(link_id: int) -> Select[tuple[int]]:
    """`SELECT count(*) FROM click WHERE link_id = ...`.

    A `COUNT` over the rows that exist, and never a column on `link`. The number is therefore
    derived and cannot drift from the rows it summarises -- a maintained counter can, and it hides
    a double count behind a value that always looks plausible.

    The price is a scan of one link's rows on the read path, which the index on `click(link_id)`
    keeps small, and it is paid on `GET /links/{code}` rather than by every redirect contending for
    one row lock.
    """
    return select(func.count()).select_from(ClickEntity).where(ClickEntity.link_id == link_id)


class ClickRepositoryImpl:
    """Append one access, count the accesses of a link. There is nothing else to do to a click.

    The port offers no way to read a click back, update one or delete one, and neither does this.
    Append-only is not a convention here -- it is what makes the write path of a redirect contend
    with nothing.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def record(self, click: Click) -> None:
        """Append one access.

        `session.execute(insert(...))` and never `session.add`. The distinction is the whole
        promise of this method: `add` stages an object and issues nothing until something flushes,
        so a failure would surface later, at the commit, attached to no particular call. Executing
        the statement here means a foreign key violation or a dead connection raises inside
        `ResolveLinkUseCaseImpl` -- which is where the decision that a lost click fails the redirect
        actually lives.
        """
        self._session.execute(insert_click_statement(click_mapper.to_values(click)))

    def count_by_link(self, link_id: int) -> int:
        """How many accesses this link has had."""
        return self._session.execute(count_statement(link_id)).scalar_one()
