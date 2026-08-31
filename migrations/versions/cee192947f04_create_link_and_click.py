"""create link and click

Revision ID: cee192947f04
Revises:
Create Date: 2026-08-31 16:27:26.717148

The whole schema of this project, in one revision: two tables and one index.

Three column choices carry the design, and none of them is incidental.

`link.id` is `BIGSERIAL`, which makes the sequence behind it the id generator: `nextval` is read
before the insert, the short code is base 62 of that value, and the row is written with
`code NOT NULL` in a single statement. `UNIQUE` on `code` is a safety net for an argument -- a
monotonic sequence through a bijective encoding cannot collide -- and not the mechanism.

`link.url_hash` is `CHAR(64)` and unique, and it is what deduplication actually rides on. The index
is on the digest rather than on `url` because a btree entry has a size limit near 2.7 KB while a URL
has no defined length. 64 is written as a literal: a migration describes the schema at one moment,
and a constant it imported could be edited afterwards.

Both timestamps are `TIMESTAMPTZ`. The domain refuses to hold a naive instant, and a column that
stores one anyway would be the place that silently reintroduces it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "cee192947f04"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "link",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("url_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_link")),
        sa.UniqueConstraint("code", name=op.f("uq_link_code")),
        sa.UniqueConstraint("url_hash", name=op.f("uq_link_url_hash")),
    )
    op.create_table(
        "click",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("link_id", sa.BigInteger(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("referer", sa.Text(), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.ForeignKeyConstraint(["link_id"], ["link.id"], name=op.f("fk_click_link_id_link")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_click")),
    )
    # The only way `click` is ever read is `count_by_link`, which filters on exactly this column.
    op.create_index(op.f("ix_click_link_id"), "click", ["link_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_click_link_id"), table_name="click")
    op.drop_table("click")
    op.drop_table("link")
