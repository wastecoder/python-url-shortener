"""The short code refuses to be anything other than seven base 62 characters."""

import dataclasses

import pytest

from url_shortener.domain.exception.domain_error import DomainError
from url_shortener.domain.model.short_code import ShortCode
from url_shortener.domain.service.base62 import MAX_ID


def test_seven_characters_of_the_alphabet_make_a_short_code() -> None:
    """
    Given a string of exactly seven characters taken from the base 62 alphabet,
    when a ShortCode is built from it,
    then it is accepted and the string is kept exactly as it arrived.
    """
    code = ShortCode("0000001")

    assert code.value == "0000001"
    assert str(code) == "0000001"


@pytest.mark.parametrize("value", ["", "0", "000000", "00000000", "0" * 100])
def test_a_code_of_the_wrong_length_is_refused(value: str) -> None:
    """
    Given a string whose length is not seven,
    when a ShortCode is built from it,
    then construction fails, so an invalid code cannot exist as an object.
    """
    with pytest.raises(ValueError, match="exactly 7 characters"):
        ShortCode(value)


@pytest.mark.parametrize("value", ["000000-", "000000_", "00 0000", "000/000", "000\u0660000"])
def test_a_code_carrying_a_character_outside_the_alphabet_is_refused(value: str) -> None:
    """
    Given a seven-character string with a character the alphabet does not contain,
    when a ShortCode is built from it,
    then construction fails, naming what the code is allowed to hold.
    """
    with pytest.raises(ValueError, match="base 62 alphabet"):
        ShortCode(value)


def test_a_malformed_code_is_a_value_error_and_not_a_domain_error() -> None:
    """
    Given a string that is not a code,
    when a ShortCode is built from it,
    then the failure is a ValueError: on the trusted paths this is a bug, not a rule the
    caller broke, and the untrusted path turns it into "not found" on purpose.
    """
    with pytest.raises(ValueError) as caught:
        ShortCode("nope")

    assert not isinstance(caught.value, DomainError)


@pytest.mark.parametrize(
    ("link_id", "expected"),
    [(0, "0000000"), (1, "0000001"), (62, "0000010"), (MAX_ID, "ZZZZZZZ")],
)
def test_a_short_code_is_built_straight_from_a_link_id(link_id: int, expected: str) -> None:
    """
    Given a link id read from the sequence,
    when a ShortCode is asked for it,
    then the code is the base 62 form of that id, so no caller has to know the encoding.
    """
    assert ShortCode.from_id(link_id).value == expected


def test_an_id_past_the_seven_character_range_produces_no_code() -> None:
    """
    Given an id that does not fit in seven characters,
    when a ShortCode is asked for it,
    then the refusal comes through instead of a code of the wrong length.
    """
    with pytest.raises(ValueError, match="does not fit"):
        ShortCode.from_id(MAX_ID + 1)


def test_codes_are_case_sensitive() -> None:
    """
    Given two codes that differ only in case,
    when they are compared,
    then they are different codes, because the alphabet holds both cases.
    """
    assert ShortCode("aaaaaaa") != ShortCode("AAAAAAA")


def test_a_short_code_is_frozen_and_usable_as_a_dictionary_key() -> None:
    """
    Given a short code,
    when it is mutated, and when it is used as a key,
    then mutation fails and two equal codes are the same key.
    """
    code = ShortCode("0000001")

    with pytest.raises(dataclasses.FrozenInstanceError):
        code.value = "0000002"  # type: ignore[misc]

    assert {code: "first"}[ShortCode("0000001")] == "first"


@pytest.mark.parametrize("value", [" 000001", "000001	", "000 001"])
def test_a_code_is_refused_rather_than_trimmed_into_shape(value: str) -> None:
    """
    Given a seven-character string padded with blanks instead of with zeros,
    when a ShortCode is built from it,
    then construction fails. Nothing here trims: a code that could be cleaned up into a valid
    one would let two different strings resolve the same link.
    """
    with pytest.raises(ValueError, match="base 62 alphabet"):
        ShortCode(value)
