"""The deduplication key is a digest of the URL exactly as it arrived."""

import hashlib

import pytest

from url_shortener.domain.service.url_hash import hash_url


def test_the_hash_of_a_url_is_its_sha256_in_lower_case_hexadecimal() -> None:
    """
    Given a target URL,
    when it is hashed,
    then the value is the SHA-256 of its UTF-8 bytes, written as hexadecimal.
    """
    assert hash_url("https://example.com") == (
        "100680ad546ce6a577f42f52df33b4cfdca756859e664b8d7de329b150d09ce9"
    )


def test_the_same_url_always_hashes_to_the_same_value() -> None:
    """
    Given one URL hashed twice,
    when the two values are compared,
    then they are equal, which is what makes the value usable as a lookup key.
    """
    assert hash_url("https://example.com/a") == hash_url("https://example.com/a")


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("https://example.com", "https://example.com/"),
        ("https://example.com", "HTTPS://example.com"),
        ("https://example.com", "https://Example.com"),
        ("https://example.com/a?b=1&c=2", "https://example.com/a?c=2&b=1"),
        ("https://example.com/a", "https://example.com/a#top"),
    ],
)
def test_urls_that_differ_by_one_character_are_different_keys(first: str, second: str) -> None:
    """
    Given two URLs a normaliser would fold into one,
    when both are hashed,
    then the values differ, because the policy normalises nothing and neither does this.
    """
    assert hash_url(first) != hash_url(second)


def test_a_non_ascii_url_is_hashed_over_its_utf8_bytes() -> None:
    """
    Given a URL carrying a character outside ASCII,
    when it is hashed,
    then the encoding is UTF-8 and not whatever the platform would have chosen.
    """
    url = "https://example.com/café"

    assert hash_url(url) == hashlib.sha256(url.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("url", ["h", "https://example.com", "https://example.com/" + "a" * 4000])
def test_the_key_has_a_fixed_size_whatever_the_url_costs(url: str) -> None:
    """
    Given URLs of wildly different lengths, including one past a btree entry limit,
    when each is hashed,
    then every key is the same 64 characters, which is the reason the index is on the hash.
    """
    key = hash_url(url)

    assert len(key) == 64
    assert set(key) <= set("0123456789abcdef")
