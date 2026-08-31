"""Where a code sends the caller."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RedirectResult:
    """The destination of a resolved short link.

    One field, and still a type: in a URL shortener the target URL, the short URL and the code are
    all strings, and only a name tells them apart. A bare `str` return would be assignable to and
    from every other string this layer passes around.

    It carries no status code. That the redirect is `302` and not `301` -- so the destination stays
    changeable and every access is still measured -- is the web adapter's decision to state, and a
    domain that named a status would be a domain that knows what HTTP is.
    """

    target_url: str
