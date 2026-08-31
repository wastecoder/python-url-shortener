"""Follow a short code to its destination."""

from ipaddress import IPv4Address, IPv6Address
from typing import Protocol

from url_shortener.application.viewmodel.redirect_result import RedirectResult


class ResolveLinkUseCase(Protocol):
    """Find where a code points, and record that somebody went there."""

    def resolve(
        self,
        code: str,
        *,
        user_agent: str | None,
        referer: str | None,
        ip: IPv4Address | IPv6Address | None,
    ) -> RedirectResult:
        """Resolve the code and append one click.

        Raises `LinkNotFoundError` when the code names no link -- including when it is not a code
        at all, because this is the catch-all route at the root and any path in the world reaches
        it. Both cases give the same answer on purpose: telling them apart would tell somebody
        guessing codes which of their guesses were at least well formed.

        `code` is a plain `str` for the same reason. The value frequently is not a code, and that
        is the case that has to be answered rather than crashed on.

        The three request facts are keyword-only. `user_agent` and `referer` are adjacent
        `str | None`, which is the swap that `Click` is `kw_only` to prevent, and keyword-only is
        also what makes a type checker verify the names against an implementation. None of them
        has a default: the only caller is a controller holding a request, which always knows all
        three even when the answer is `None`, and a default would let a click lose its context by
        omission instead of by fact.

        `ip` is an address object rather than text, so the parsing -- and the decision that an
        unparseable client address becomes `None` -- happens in the web adapter, and a value this
        layer accepted cannot fail later against a column that stores addresses.
        """
        ...
