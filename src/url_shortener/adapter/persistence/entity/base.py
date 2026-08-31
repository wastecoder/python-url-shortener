"""The declarative base every table in this adapter hangs from."""

from typing import Final

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Every constraint and index gets a deterministic name instead of one PostgreSQL invents.
#
# The reason is concrete and it arrives later, not now: `op.drop_constraint` takes a *name*, so a
# constraint the server named is one a future migration cannot touch without first going to look it
# up in the catalogue. Five lines decided once, against a migration that cannot be written from the
# model alone.
#
# It binds only what is created from this metadata. The names PostgreSQL derives on its own are
# untouched -- `link_id_seq`, the sequence behind `BIGSERIAL`, is the one that matters here, and it
# is named in `link_entity.py` for exactly that reason.
NAMING_CONVENTION: Final[dict[str, str]] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """The metadata Alembic compares the database against.

    Two tables hang from it and nothing else. It is deliberately never used to build a schema --
    `Base.metadata.create_all()` appears nowhere in this project, not even in a test, because a
    schema created from the models is a schema no migration was ever run against. From Fase 5 the
    integration tests will run the same migrations production runs, which is the only way the
    migrations get tested at all; today the equivalence is checked by hand, with `alembic check`
    against a live database.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
