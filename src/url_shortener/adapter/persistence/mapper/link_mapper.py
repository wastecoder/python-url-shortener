"""Between a row of `link` and a `Link`."""

from url_shortener.adapter.persistence.entity.link_entity import LinkEntity
from url_shortener.domain.model.link import Link
from url_shortener.domain.model.short_code import ShortCode
from url_shortener.domain.service.url_hash import UrlHash


def to_domain(entity: LinkEntity) -> Link:
    """Rebuild the domain object a row describes.

    Nothing here is defensive, and that is deliberate: the constructors are. `ShortCode` refuses
    anything that is not seven characters of the base 62 alphabet, and `Link` refuses a naive
    `created_at`. A row that violates either raises `ValueError` right here, which becomes a 500 --
    the honest answer, because a corrupt row is a bug in this system and not a missing link. The
    `try` in `require_link` wraps exactly one expression precisely so that it cannot swallow this
    and answer 404 instead.
    """
    return Link(
        id=entity.id,
        code=ShortCode(entity.code),
        url=entity.url,
        created_at=entity.created_at,
    )


def to_values(link: Link, *, url_hash: UrlHash) -> dict[str, object]:
    """The column values of the row this link becomes.

    A mapping rather than a `LinkEntity`, because the repository inserts with Core -- the statement
    has to be an `INSERT ... ON CONFLICT DO NOTHING`, which the unit of work has no way to express.

    The digest arrives as a keyword argument instead of being read off the link, because `Link` has
    no `url_hash` field: the hash is a fixed-size index key, and the caller computed this exact one
    a few lines earlier for the lookup that decided a row was needed at all.

    `id` is included, and that is the whole shape of this project's id generation: the value was
    taken from the sequence *before* this call, so the row goes in with its code already computed,
    in one statement, instead of an insert followed by an update.
    """
    return {
        "id": link.id,
        "code": str(link.code),
        "url": link.url,
        "url_hash": url_hash,
        "created_at": link.created_at,
    }
