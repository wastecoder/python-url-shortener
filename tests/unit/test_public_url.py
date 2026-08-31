"""Joining the configured origin to a path, and the trailing slash that would spoil it."""

import pytest

from url_shortener.adapter.web.public_url import link_details_url, short_url

BASE_URL = "https://sho.rt"
CODE = "000000b"


def test_the_short_url_is_the_origin_and_the_code() -> None:
    """
    Given a configured origin,
    when the short URL of a code is built,
    then it is the origin followed by the code, with nothing else between them.
    """
    assert short_url(CODE, base_url=BASE_URL) == "https://sho.rt/000000b"


def test_the_details_url_points_at_the_links_collection() -> None:
    """
    Given a configured origin,
    when the details URL of a code is built,
    then it names the link's resource under /links, which is not where the redirect answers.
    """
    assert link_details_url(CODE, base_url=BASE_URL) == "https://sho.rt/links/000000b"


@pytest.mark.parametrize("configured", ["https://sho.rt/", "https://sho.rt//"])
def test_a_trailing_slash_in_the_setting_never_reaches_the_url(configured: str) -> None:
    """
    Given BASE_URL set with one trailing slash or more, which is the ordinary operational typo,
    when either URL is built,
    then the result is the same as with a clean origin, and never carries a doubled slash.
    """
    assert short_url(CODE, base_url=configured) == "https://sho.rt/000000b"
    assert link_details_url(CODE, base_url=configured) == "https://sho.rt/links/000000b"


def test_an_origin_carrying_a_path_prefix_keeps_it() -> None:
    """
    Given an origin that already carries a path, as it does behind a proxy mounting a prefix,
    when the short URL is built,
    then the prefix survives, because the origin is joined and never parsed.
    """
    assert short_url(CODE, base_url="https://sho.rt/s") == "https://sho.rt/s/000000b"
