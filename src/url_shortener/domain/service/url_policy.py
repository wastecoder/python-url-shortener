"""Decides which URLs this shortener agrees to point at.

Every decision is taken from the URL string itself, plus `ipaddress`. There is no name resolution
here and that is deliberate: a domain service does no I/O, a unit test that needs the network is
not a unit test, and resolving a name would still not settle the question -- the address behind a
name can change between the check and the redirect. What this module buys is the cheap half of the
problem, and the expensive half is named as a known limit rather than half-built.

A shortener that accepts anything is two things at once: a way of asking the server to fetch its
own private network, and a laundry for links whose real destination the reader cannot see.
"""

import ipaddress
from typing import Final
from urllib.parse import urlsplit

from url_shortener.domain.exception.invalid_target_url_error import InvalidTargetUrlError
from url_shortener.domain.exception.rejection_reason import RejectionReason

MAX_TARGET_URL_LENGTH: Final[int] = 2048

ALLOWED_SCHEMES: Final[frozenset[str]] = frozenset({"http", "https"})

# The paths the API answers on itself. Nothing in V1 can collide with them: a generated code has
# exactly seven characters and none of these does, so the list is a safety net and not the
# mechanism. It exists for the day a code is *chosen* instead of generated -- a custom alias, an
# import, a bug in the generator -- and it is cheaper to keep it now than to remember it then.
RESERVED_CODES: Final[frozenset[str]] = frozenset(
    {"docs", "redoc", "openapi.json", "health", "links"}
)

_NON_PUBLIC_HOSTS: Final[frozenset[str]] = frozenset({"localhost"})

# A tuple and not a frozenset: `str.endswith` takes a string or a tuple of strings, and mypy
# refuses anything else.
_NON_PUBLIC_SUFFIXES: Final[tuple[str, ...]] = (
    ".localhost",
    ".local",
    ".internal",
    ".home.arpa",
)

# Every C0 control, the space and DEL. The check runs on the raw string, before parsing, because
# the parser deletes tab, carriage return and newline from anywhere in the URL and strips the
# leading controls -- so a URL carrying them parses as one thing and gets stored as another.
_FORBIDDEN_CHARACTERS: Final[frozenset[str]] = frozenset(chr(code) for code in (*range(0x21), 0x7F))


def validate_target_url(url: str) -> None:
    """Accept `url` as a redirect target, or raise `InvalidTargetUrlError` saying why.

    It returns nothing and changes nothing. The URL is stored, hashed and redirected to exactly
    as it arrived: normalising it here would mean the row no longer holds what the caller sent,
    and two spellings of the same address would stop being two links.
    """
    if len(url) > MAX_TARGET_URL_LENGTH:
        raise InvalidTargetUrlError(
            RejectionReason.URL_TOO_LONG,
            f"the URL is {len(url)} characters long and the limit is {MAX_TARGET_URL_LENGTH}",
        )

    forbidden = _FORBIDDEN_CHARACTERS & frozenset(url)
    if forbidden:
        raise InvalidTargetUrlError(
            RejectionReason.FORBIDDEN_CHARACTER,
            f"the URL contains {min(forbidden)!r}, which has to be percent-encoded",
        )

    try:
        parts = urlsplit(url)
        # Reading the port is what validates it. Left unread, an impossible port surfaces much
        # later as an unhandled error instead of as a refusal.
        _ = parts.port
    except ValueError as error:
        raise InvalidTargetUrlError(RejectionReason.MALFORMED_URL, str(error)) from error

    if not parts.scheme:
        raise InvalidTargetUrlError(
            RejectionReason.MISSING_SCHEME,
            "the URL has no scheme; it has to start with http:// or https://",
        )

    if parts.scheme not in ALLOWED_SCHEMES:
        raise InvalidTargetUrlError(
            RejectionReason.UNSUPPORTED_SCHEME,
            f"the scheme {parts.scheme!r} is not accepted; only http and https are",
        )

    # Absence, not emptiness: "https://@example.com/" has an empty user name, which is still
    # someone writing credentials in front of the host.
    if parts.username is not None or parts.password is not None:
        raise InvalidTargetUrlError(
            RejectionReason.CREDENTIALS_IN_URL,
            "the URL carries credentials in front of the host",
        )

    host = parts.hostname
    if not host:
        raise InvalidTargetUrlError(RejectionReason.MISSING_HOST, "the URL has no host")

    if not host.isascii():
        raise InvalidTargetUrlError(
            RejectionReason.FORBIDDEN_CHARACTER,
            f"the host {host!r} is not ASCII; send an internationalised domain as punycode",
        )

    # The trailing dot is the DNS root label. It changes nothing about where the host points, but
    # it does make the address parser refuse "127.0.0.1.", which would then walk past the address
    # check below as if it were a name. `rstrip` and not `removesuffix`: "127.0.0.1.." exists too.
    host = host.rstrip(".")

    address = _parse_ip_literal(host)
    if address is not None:
        if not _is_publicly_routable(address):
            raise InvalidTargetUrlError(
                RejectionReason.NON_PUBLIC_ADDRESS,
                f"{host} is not a publicly routable address",
            )
        return

    if _is_non_public_hostname(host):
        raise InvalidTargetUrlError(
            RejectionReason.NON_PUBLIC_HOST,
            f"the host {host!r} can only name something on the caller's own network",
        )


def is_reserved_code(code: str) -> bool:
    """Whether `code` is a path the API itself owns.

    It is lower-cased before the comparison because a route is not case sensitive, while a code
    is: `aaaaaaa` and `AAAAAAA` are two different links, but `/DOCS` and `/docs` are one route.
    """
    return code.lower() in RESERVED_CODES


def _parse_ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """The host read as an address, or `None` when it is a name and not a literal."""
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _is_publicly_routable(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Whether the address is one the public internet can route to.

    `is_global` is the whole check and not four of them: it already excludes loopback, 0.0.0.0,
    10/8, 172.16/12, 192.168/16, link-local 169.254/16 -- and with it the cloud metadata address
    169.254.169.254 -- carrier NAT 100.64/10, 240/4, the broadcast address, ::1, ::, fc00::/7,
    fe80::/10, and the IPv4-mapped form of every one of them. Asking `is_private` instead would
    let carrier NAT through, because that range is neither private nor global. Multicast is the
    one range `is_global` still calls global, so it is excluded by hand.
    """
    return address.is_global and not address.is_multicast


def _is_non_public_hostname(host: str) -> bool:
    """Whether a name can only mean something on the caller's own network."""
    if host in _NON_PUBLIC_HOSTS or host.endswith(_NON_PUBLIC_SUFFIXES):
        return True

    # A single-label host ("intranet") names something local, and a last label made only of digits
    # is an address written in a form the address parser does not read but a browser does
    # ("2130706433" and "127.1" both reach 127.0.0.1). A real top-level domain is never all
    # digits, so refusing both costs nothing that a public URL needs.
    _, dot, top_level = host.rpartition(".")
    return not dot or top_level.isdigit()
