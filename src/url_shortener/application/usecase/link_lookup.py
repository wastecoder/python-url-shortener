"""Finding the link a path segment names -- the one thing both read use cases do the same way."""

from url_shortener.application.port.outbound.link_repository import LinkRepository
from url_shortener.domain.exception.link_not_found_error import LinkNotFoundError
from url_shortener.domain.model.link import Link
from url_shortener.domain.model.short_code import ShortCode


def require_link(links: LinkRepository, code: str) -> Link:
    """The link this code names, or `LinkNotFoundError` carrying the value that was asked for.

    Two different failures collapse into one answer here, on purpose: "that is not a code" and
    "that code has no link" are indistinguishable to the caller. Keeping them apart would tell
    somebody enumerating codes which of their guesses were at least well formed.

    Parsing before querying is not only about the error. Building the `ShortCode` rejects
    `/favicon.ico`, `/robots.txt` and every scanner probe *before* any repository call, so the
    catch-all route at the root costs zero database round trips for garbage.

    It lives in one place rather than in both read use cases because of how narrow the `try` has
    to be. It wraps exactly one expression, and that is the guarantee: `DomainError` deliberately
    extends `Exception` and not `ValueError`, so this `except` provably cannot swallow an
    `InvalidTargetUrlError` and answer 404 to something that deserved 400 -- and a one-expression
    `try` also cannot swallow a `ValueError` raised by `Link.__post_init__` on a corrupt row, which
    would be a bug reported as a missing link. Two copies of that reasoning are two chances to
    widen it by one line.
    """
    try:
        short_code = ShortCode(code)
    except ValueError as malformed:
        raise LinkNotFoundError(code) from malformed

    link = links.find_by_code(short_code)
    if link is None:
        raise LinkNotFoundError(code)
    return link
