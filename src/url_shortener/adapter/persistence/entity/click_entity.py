"""The `click` table."""

from datetime import datetime
from ipaddress import IPv4Address, IPv6Address

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from url_shortener.adapter.persistence.entity.base import Base


class ClickEntity(Base):
    """A row of `click`: written once, never updated, never deleted.

    There is no counter column on `link` to keep in step with this table, and that is the decision
    rather than an omission. A counter would be a write on the read path, on the same row, so two
    hits on a popular link would contend for one row lock; an insert contends with nothing. The
    total is a `COUNT` paid on the cold path.

    It carries an `id` the domain has no field for. The domain never reads a click back on its own
    -- the only question ever asked of clicks is how many belong to a link -- but a table still
    wants a primary key.
    """

    __tablename__ = "click"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # Indexed because `count_by_link` is the only way this table is ever read, and it filters on
    # exactly this column. The foreign key is what makes a click pointing at no link impossible.
    link_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("link.id"), index=True)

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user_agent: Mapped[str | None] = mapped_column(Text)
    referer: Mapped[str | None] = mapped_column(Text)

    # `INET`, and the annotation says what psycopg actually hands back rather than what SQLAlchemy
    # declares. `postgresql.INET` is typed `TypeEngine[str]` and carries no result processor, so
    # the value passes straight through from the driver -- and psycopg 3 registers loaders for
    # `ipaddress` by default, so what comes out of a `SELECT` is already an `IPv4Address`.
    #
    # This is why the mapper converts nothing in either direction. Calling `ip_address()` on the
    # value read back would raise `ValueError`, because it is not a string.
    ip: Mapped[IPv4Address | IPv6Address | None] = mapped_column(INET)
