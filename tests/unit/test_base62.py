"""Base 62: a short code is a link id in disguise, always seven characters long."""

import pytest

from url_shortener.domain.service.base62 import ALPHABET, CODE_LENGTH, MAX_ID, decode, encode

KNOWN_CODES = [
    (0, "0000000"),
    (1, "0000001"),
    (9, "0000009"),
    (10, "000000a"),
    (35, "000000z"),
    (36, "000000A"),
    (61, "000000Z"),
    (62, "0000010"),
    (63, "0000011"),
    (3843, "00000ZZ"),
    (3844, "0000100"),
    (1_000_000_000, "015FTGg"),
    (56_800_235_583, "0ZZZZZZ"),
    (56_800_235_584, "1000000"),
    (3_521_614_606_206, "ZZZZZZY"),
    (3_521_614_606_207, "ZZZZZZZ"),
]


@pytest.mark.parametrize(("link_id", "expected"), KNOWN_CODES)
def test_encode_writes_the_id_in_base_62(link_id: int, expected: str) -> None:
    """
    Given a link id inside the seven-character range,
    when it is encoded,
    then it comes out as the expected base 62 code.
    """
    assert encode(link_id) == expected


@pytest.mark.parametrize(("link_id", "expected"), KNOWN_CODES)
def test_encode_always_pads_to_exactly_seven_characters(link_id: int, expected: str) -> None:
    """
    Given any link id inside the range,
    when it is encoded,
    then the code has exactly seven characters, all of them from the alphabet.
    """
    code = encode(link_id)

    assert len(code) == CODE_LENGTH
    assert set(code) <= set(ALPHABET)


@pytest.mark.parametrize(("link_id", "expected"), KNOWN_CODES)
def test_decode_reverses_encode(link_id: int, expected: str) -> None:
    """
    Given a link id inside the range,
    when it is encoded and decoded again,
    then the original id comes back.
    """
    assert decode(encode(link_id)) == link_id


@pytest.mark.parametrize(("link_id", "expected"), KNOWN_CODES)
def test_encode_reverses_decode(link_id: int, expected: str) -> None:
    """
    Given a seven-character code,
    when it is decoded and encoded again,
    then the same code comes back, so codes and ids are in bijection.
    """
    assert encode(decode(expected)) == expected


def test_the_alphabet_is_case_sensitive() -> None:
    """
    Given the alphabet, which runs digits, then lower case, then upper case,
    when two ids twenty-six apart are encoded,
    then they differ only in case, so folding a code would collapse two different links.
    """
    assert encode(10) == "000000a"
    assert encode(36) == "000000A"
    assert decode("000000a") != decode("000000A")


@pytest.mark.parametrize("link_id", [-1, -62, -3_521_614_606_207])
def test_encode_refuses_a_negative_id(link_id: int) -> None:
    """
    Given a negative id, which no sequence can produce,
    when it is encoded,
    then encoding fails instead of returning a code.
    """
    with pytest.raises(ValueError, match="negative"):
        encode(link_id)


@pytest.mark.parametrize("link_id", [MAX_ID + 1, 62**8])
def test_encode_refuses_an_id_that_would_need_an_eighth_character(link_id: int) -> None:
    """
    Given an id past 62**7 - 1,
    when it is encoded,
    then encoding fails instead of silently returning an eight-character code, which would
    break the fixed length that keeps the API's own routes ungeneratable.
    """
    with pytest.raises(ValueError, match="does not fit"):
        encode(link_id)


@pytest.mark.parametrize("code", ["", "0", "abc", "000000", "00000000", "zzzzzzzz"])
def test_decode_refuses_a_code_that_is_not_seven_characters(code: str) -> None:
    """
    Given a string whose length is not seven,
    when it is decoded,
    then decoding fails, because only a seven-character string is a code.
    """
    with pytest.raises(ValueError, match="exactly 7 characters"):
        decode(code)


@pytest.mark.parametrize("code", ["000000-", "000000_", "00000+0", "00 0000", "000\u0660000"])
def test_decode_refuses_a_character_outside_the_alphabet(code: str) -> None:
    """
    Given a seven-character string carrying a character outside the alphabet,
    when it is decoded,
    then decoding fails, naming the offending character.
    """
    with pytest.raises(ValueError, match="not a base 62 digit"):
        decode(code)


def test_the_padding_carries_no_value() -> None:
    """
    Given codes that differ only in their leading zeros,
    when they are decoded,
    then the padding contributes nothing, so the bijection is with the padded form alone.
    """
    assert decode("0000000") == 0
    assert decode("0000001") == 1


def test_the_alphabet_and_the_length_are_the_agreed_ones() -> None:
    """
    Given the two numbers the whole scheme rests on,
    when they are inspected,
    then the alphabet is 62 distinct characters and seven of them address 62**7 ids.
    """
    assert len(ALPHABET) == 62
    assert len(set(ALPHABET)) == 62
    assert ALPHABET.startswith("0123456789")
    assert CODE_LENGTH == 7
    assert MAX_ID == 62**7 - 1
