"""The `link` table."""

from datetime import datetime
from typing import Final

from sqlalchemy import CHAR, BigInteger, DateTime, Sequence, Text
from sqlalchemy.orm import Mapped, mapped_column

from url_shortener.adapter.persistence.entity.base import Base

# The sequence that `BIGSERIAL` creates, written down once.
#
# PostgreSQL derives the name from the table and the column -- `<table>_<column>_seq` -- so this
# string is a *claim about what the database did*, not a declaration. It lives here, beside the
# column it describes, rather than inside the repository that reads it, so the claim and its
# subject cannot drift apart across two files.
#
# The object stays detached from `Base.metadata` on purpose. Attaching it would make SQLAlchemy
# emit `CREATE SEQUENCE` and turn the column into `BIGINT DEFAULT nextval(...)`, which is a
# different design: the sequence would stop being owned by the column, so dropping the table would
# leave it behind, and Alembic's autogenerate does not emit sequence DDL anyway. Detached, it is
# only a name -- and `next_value()` is only the `nextval('link_id_seq')` expression.
LINK_ID_SEQUENCE: Final[Sequence] = Sequence("link_id_seq")


class LinkEntity(Base):
    """A row of `link`.

    A different type from `domain.model.Link`, and the difference is the point of the `mapper`
    package next door. This one carries `url_hash`, which the domain has no field for: the digest
    is a fixed-size key for a unique index, which is a storage concern. The domain one refuses to
    exist with a naive `created_at`; this one only knows the column is `TIMESTAMPTZ`.
    """

    __tablename__ = "link"

    # `BigInteger` plus `primary_key=True` renders `BIGSERIAL` on PostgreSQL, which is the id
    # generator this project chose: transactional, free, and already in the database.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # Unique as a safety net and not as the mechanism. A duplicate code is impossible by
    # construction -- the sequence is monotonic and base 62 encoding is a bijection -- so this
    # index exists to make a violation of that argument loud instead of silent.
    code: Mapped[str] = mapped_column(Text, unique=True)

    url: Mapped[str] = mapped_column(Text)

    # The index deduplication actually rides on, and the reason it is on the digest rather than on
    # `url`: a btree entry has a size limit near 2.7 KB and a URL has no defined length. `CHAR(64)`
    # is the literal width of a SHA-256 in hexadecimal, written as a literal rather than derived
    # from a constant -- a migration describes the schema at one moment in time, and a constant it
    # imports can be edited afterwards.
    url_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)

    # `timezone=True`, never a bare `DateTime()`, which compiles to `TIMESTAMP WITHOUT TIME ZONE`
    # and would silently drop the offset the domain refuses to exist without.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
