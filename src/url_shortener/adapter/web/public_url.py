"""Building the URLs this API publishes, from the origin it was told it answers on.

The application never guesses its own public host. It cannot: behind a proxy the `Host` header,
the socket it is bound to and the address a caller typed are three different things, and only one
of them belongs in a link this API hands out. So the origin arrives as the `BASE_URL` setting, and
this module is the single place that joins it to a path.

Two URLs come out of it, and they are not the same URL. The short one is the product -- what a
caller pastes into a browser, and what `GET /{code}` answers on. The details one is the link's own
resource inside this API, which is what the `Location` header of a `201` points at.
"""


def short_url(code: str, *, base_url: str) -> str:
    """The public short URL of a code."""
    return f"{_origin(base_url)}/{code}"


def link_details_url(code: str, *, base_url: str) -> str:
    """The URL of the link's resource in this API's own collection."""
    return f"{_origin(base_url)}/links/{code}"


def _origin(base_url: str) -> str:
    """`BASE_URL` without its trailing slash.

    `.env.example` documents the setting as carrying none, and this strips it anyway. A trailing
    slash in an environment variable is the most ordinary operational typo there is, and the URL
    it produces here -- `https://sho.rt//abcdefg` -- is built without complaint, stored in
    nothing, and noticed only by whoever clicks it.
    """
    return base_url.rstrip("/")
