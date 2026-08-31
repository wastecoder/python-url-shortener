"""SQLAlchemy models, shaped by the database rather than by the domain.

They are deliberately a different type from `domain.model`: the domain must not inherit its shape
from the storage engine.

The two entities are re-exported here because a table only exists in `Base.metadata` once the
module declaring it has been imported. Alembic's `env.py` imports this package and gets both, which
is what makes `--autogenerate` compare the whole schema instead of half of it -- and an entity
added later without a line here would be a table autogenerate proposes to *drop*.
"""

from url_shortener.adapter.persistence.entity.base import Base
from url_shortener.adapter.persistence.entity.click_entity import ClickEntity
from url_shortener.adapter.persistence.entity.link_entity import LINK_ID_SEQUENCE, LinkEntity

__all__ = ["LINK_ID_SEQUENCE", "Base", "ClickEntity", "LinkEntity"]
