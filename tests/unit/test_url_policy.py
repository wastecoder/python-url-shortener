"""The target URL policy: what this shortener agrees to point at, decided from the string alone."""

import pytest

from url_shortener.domain.exception.invalid_target_url_error import InvalidTargetUrlError
from url_shortener.domain.exception.rejection_reason import RejectionReason
from url_shortener.domain.service.url_policy import MAX_TARGET_URL_LENGTH, validate_target_url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/a?b=1#c",
        "http://example.com",
        "https://example.com:8443/path",
        "https://example.com./",
        "https://localhost.example.com/",
        "https://xn--e1afmkfd.xn--p1ai/",
        "http://8.8.8.8/",
        "http://172.32.0.1/",
        "http://[2001:4860:4860::8888]/",
        "http://[::ffff:8.8.8.8]/",
    ],
)
def test_a_public_http_url_is_accepted(url: str) -> None:
    """
    Given a URL naming something reachable on the public internet,
    when the policy is applied,
    then it is accepted and nothing about it is rewritten.
    """
    assert validate_target_url(url) is None


def test_a_url_at_the_length_limit_is_still_accepted() -> None:
    """
    Given a URL exactly at the limit,
    when the policy is applied,
    then it is accepted, so the limit refuses only what is past it.
    """
    url = "https://example.com/" + "a" * (MAX_TARGET_URL_LENGTH - len("https://example.com/"))

    assert len(url) == MAX_TARGET_URL_LENGTH
    assert validate_target_url(url) is None


def test_a_url_past_the_length_limit_is_refused() -> None:
    """
    Given a URL longer than the limit,
    when the policy is applied,
    then it is refused before it is ever parsed.
    """
    url = "https://example.com/" + "a" * MAX_TARGET_URL_LENGTH

    with pytest.raises(InvalidTargetUrlError) as caught:
        validate_target_url(url)

    assert caught.value.reason is RejectionReason.URL_TOO_LONG


@pytest.mark.parametrize(
    "url",
    [
        "http://exa mple.com/",
        "http://example.com/\npath",
        "http://example.com/\tpath",
        "http://example.com/\rpath",
        "\x00http://example.com/",
        "http://example.com/\x7f",
    ],
)
def test_a_url_carrying_a_control_character_or_a_space_is_refused(url: str) -> None:
    """
    Given a URL with a raw control character or a space,
    when the policy is applied,
    then it is refused on the raw string, because the parser silently deletes tabs and newlines
    and would otherwise approve a different URL from the one that gets stored.
    """
    with pytest.raises(InvalidTargetUrlError) as caught:
        validate_target_url(url)

    assert caught.value.reason is RejectionReason.FORBIDDEN_CHARACTER


@pytest.mark.parametrize(
    "url",
    [
        "http://пример.рф/",
        # The first two characters are the full-width L and O. The linter is told to allow them
        # here because the whole point of the row is that they are not the letters they resemble.
        "http://ＬＯcalhost/",  # noqa: RUF001
    ],
)
def test_a_host_that_is_not_ascii_is_refused(url: str) -> None:
    """
    Given a host written in another script, or in characters that merely look like ASCII,
    when the policy is applied,
    then it is refused: an internationalised domain has to arrive already as punycode, which is
    the form that cannot pretend to be a different host.
    """
    with pytest.raises(InvalidTargetUrlError) as caught:
        validate_target_url(url)

    assert caught.value.reason is RejectionReason.FORBIDDEN_CHARACTER


@pytest.mark.parametrize("url", ["http://example.com:99999/", "http://[::1/", "http://[not-ipv6]/"])
def test_a_url_the_parser_refuses_becomes_a_refusal_and_not_a_crash(url: str) -> None:
    """
    Given a URL the standard parser itself rejects,
    when the policy is applied,
    then the failure comes back as a refusal, not as an unhandled error answered with a 500.
    """
    with pytest.raises(InvalidTargetUrlError) as caught:
        validate_target_url(url)

    assert caught.value.reason is RejectionReason.MALFORMED_URL


@pytest.mark.parametrize("url", ["example.com/path", "//example.com/path", "/just/a/path"])
def test_a_url_without_a_scheme_is_refused(url: str) -> None:
    """
    Given something that is not an absolute URL,
    when the policy is applied,
    then it is refused, because a redirect target has to say which protocol it speaks.
    """
    with pytest.raises(InvalidTargetUrlError) as caught:
        validate_target_url(url)

    assert caught.value.reason is RejectionReason.MISSING_SCHEME


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,<h1>hi</h1>",
        "ftp://example.com/x",
        "mailto:someone@example.com",
    ],
)
def test_a_scheme_other_than_http_and_https_is_refused(url: str) -> None:
    """
    Given a URL whose scheme is not http or https,
    when the policy is applied,
    then it is refused: a short link that can hand a browser a script or a local file is a
    weapon pointed at whoever clicks it.
    """
    with pytest.raises(InvalidTargetUrlError) as caught:
        validate_target_url(url)

    assert caught.value.reason is RejectionReason.UNSUPPORTED_SCHEME


@pytest.mark.parametrize(
    "url",
    [
        "https://user:secret@example.com/",
        "https://user@example.com/",
        "https://@example.com/",
        "https://:secret@example.com/",
    ],
)
def test_a_url_carrying_credentials_is_refused(url: str) -> None:
    """
    Given a URL with anything in front of the host,
    when the policy is applied,
    then it is refused, the empty user name included, which is why the check is against absence
    and not against truthiness.
    """
    with pytest.raises(InvalidTargetUrlError) as caught:
        validate_target_url(url)

    assert caught.value.reason is RejectionReason.CREDENTIALS_IN_URL


@pytest.mark.parametrize("url", ["http://", "http:///path", "https://:8080/"])
def test_a_url_with_no_host_is_refused(url: str) -> None:
    """
    Given an http URL with an empty authority,
    when the policy is applied,
    then it is refused, because there is nowhere to redirect to.
    """
    with pytest.raises(InvalidTargetUrlError) as caught:
        validate_target_url(url)

    assert caught.value.reason is RejectionReason.MISSING_HOST


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://127.0.0.1:5432/",
        "http://127.0.0.1./",
        "http://127.0.0.1../",
        "http://0.0.0.0/",
        "http://10.0.0.1/",
        "http://172.16.0.1/",
        "http://192.168.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.64.0.1/",
        "http://240.0.0.1/",
        "http://255.255.255.255/",
        "http://224.0.0.1/",
        "http://[::1]/",
        "http://[::]/",
        "http://[fc00::1]/",
        "http://[fe80::1]/",
        "http://[ff02::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://[::ffff:10.0.0.1]/",
    ],
)
def test_an_address_that_is_not_publicly_routable_is_refused(url: str) -> None:
    """
    Given a URL pointing straight at an address literal only the server itself can reach,
    when the policy is applied,
    then it is refused: otherwise the shortener becomes a way of asking the server to fetch its
    own network, the cloud metadata endpoint included.
    """
    with pytest.raises(InvalidTargetUrlError) as caught:
        validate_target_url(url)

    assert caught.value.reason is RejectionReason.NON_PUBLIC_ADDRESS


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://localhost:8000/",
        "http://LOCALHOST/",
        "http://api.localhost/",
        "http://printer.local/",
        "http://db.internal/",
        "http://router.home.arpa/",
        "http://intranet/",
        "http://2130706433/",
        "http://0x7f000001/",
        "http://127.1/",
    ],
)
def test_a_hostname_that_can_only_be_local_is_refused(url: str) -> None:
    """
    Given a name that can only mean something on the caller's own network, or an address in a
    form the address parser does not read but a browser does,
    when the policy is applied,
    then it is refused. No name is resolved to reach this answer, and that limit is deliberate.
    """
    with pytest.raises(InvalidTargetUrlError) as caught:
        validate_target_url(url)

    assert caught.value.reason is RejectionReason.NON_PUBLIC_HOST


def test_the_refusal_names_what_was_wrong() -> None:
    """
    Given a URL refused for its scheme,
    when the error is read,
    then the message names the offending scheme, so a caller can fix the URL without guessing.
    """
    with pytest.raises(InvalidTargetUrlError) as caught:
        validate_target_url("file:///etc/passwd")

    assert "file" in caught.value.message
