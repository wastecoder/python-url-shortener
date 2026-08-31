"""`POST /links`: the two success statuses, the two failure statuses, and what is stored."""

from http import HTTPStatus
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.fakes import InMemoryLinkRepository
from tests.unit.conftest import BASE_URL, NOW_ON_THE_WIRE

TARGET = "https://example.com/a"


def _post(client: TestClient, url: str) -> Any:
    return client.post("/links", json={"url": url})


def test_a_new_url_answers_201_with_the_link_that_was_created(
    client: TestClient, links: InMemoryLinkRepository
) -> None:
    """
    Given a URL nothing points at yet,
    when it is shortened,
    then the answer is 201 carrying the code, the short URL built from BASE_URL, the URL as it was
    sent, and the instant the frozen clock reported.
    """
    response = _post(client, TARGET)

    assert response.status_code == HTTPStatus.CREATED
    assert response.json() == {
        "code": "0000001",
        "short_url": f"{BASE_URL}/0000001",
        "url": TARGET,
        "created_at": NOW_ON_THE_WIRE,
    }
    assert len(links.rows) == 1


def test_a_created_link_points_the_location_header_at_its_own_resource(
    client: TestClient,
) -> None:
    """
    Given a URL that gets a new link,
    when it is shortened,
    then Location names the link's member of the /links collection -- the resource that was
    created -- and not the short URL, which the body already carries.
    """
    response = _post(client, TARGET)

    assert response.headers["location"] == f"{BASE_URL}/links/0000001"


def test_the_same_url_asked_for_twice_answers_200_with_the_same_link(
    client: TestClient, links: InMemoryLinkRepository
) -> None:
    """
    Given a URL that already has a link,
    when it is shortened again,
    then the answer is 200 and not 201, the code is the one that already existed, and the store
    still holds exactly one row.
    """
    first = _post(client, TARGET)
    second = _post(client, TARGET)

    assert first.status_code == HTTPStatus.CREATED
    assert second.status_code == HTTPStatus.OK
    assert second.json() == first.json()
    assert len(links.rows) == 1


def test_the_deduplicated_answer_carries_no_location(client: TestClient) -> None:
    """
    Given a URL that already has a link,
    when it is shortened again,
    then there is no Location header, because nothing was created for it to point at.
    """
    _post(client, TARGET)

    assert "location" not in _post(client, TARGET).headers


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("https://example.com/a", "https://example.com/a/"),
        ("https://example.com/a", "https://example.com/A"),
        ("https://example.com/a?x=1&y=2", "https://example.com/a?y=2&x=1"),
        ("https://example.com/a", "https://example.com/a#top"),
    ],
)
def test_urls_that_differ_by_one_byte_are_two_links(
    client: TestClient, links: InMemoryLinkRepository, first: str, second: str
) -> None:
    """
    Given two URLs a URL type would have normalised into one,
    when both are shortened,
    then each gets its own code and the store holds two rows -- which is the visible consequence
    of the body carrying a plain string. See ADR-0005.
    """
    created = _post(client, first)
    other = _post(client, second)

    assert other.status_code == HTTPStatus.CREATED
    assert other.json()["code"] != created.json()["code"]
    assert len(links.rows) == 2


def test_the_stored_url_is_the_string_that_was_sent(client: TestClient) -> None:
    """
    Given a URL with mixed case, a query string and a fragment,
    when it is shortened,
    then the URL in the answer is byte for byte the one that was sent, because nothing normalises
    it on the way in or on the way out.
    """
    url = "https://Example.com/A/b?z=1&a=2#Frag"

    assert _post(client, url).json()["url"] == url


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("javascript:alert(1)", "unsupported-scheme"),
        ("file:///etc/passwd", "unsupported-scheme"),
        ("http://localhost:8000/admin", "non-public-host"),
        ("http://127.0.0.1/", "non-public-address"),
        ("http://169.254.169.254/latest/meta-data/", "non-public-address"),
        ("http://user:secret@example.com/", "credentials-in-url"),
        ("example.com/a", "missing-scheme"),
    ],
)
def test_a_target_the_policy_refuses_answers_400_with_its_reason(
    client: TestClient, links: InMemoryLinkRepository, url: str, reason: str
) -> None:
    """
    Given a target URL the domain policy refuses,
    when it is shortened,
    then the answer is 400 -- not 422 -- carrying the machine-readable reason, and nothing was
    stored.
    """
    response = _post(client, url)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "invalid-target-url"
    assert response.json()["reason"] == reason
    assert links.rows == ()


def test_a_refused_target_never_spends_a_code(
    client: TestClient, links: InMemoryLinkRepository
) -> None:
    """
    Given a target URL the policy refuses,
    when it is shortened,
    then no id was taken from the sequence at all -- validation runs before anything is spent, so
    a rejected URL does not burn a code nothing will ever answer to.
    """
    _post(client, "javascript:alert(1)")

    assert links.issued_ids == []


@pytest.mark.parametrize(
    "body",
    [{}, {"url": None}, {"url": 1}, {"URL": TARGET}, {"url": TARGET, "alias": "mine"}],
)
def test_a_body_of_the_wrong_shape_answers_422(client: TestClient, body: dict[str, Any]) -> None:
    """
    Given a body that is missing the field, mistypes it or carries one this API does not accept,
    when it is posted,
    then the answer is 422 -- the payload is not even the right shape, so no business rule was
    consulted.
    """
    response = client.post("/links", json=body)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert response.json()["type"] == "validation-error"


def test_the_timestamp_is_rfc_3339_and_carries_an_offset(client: TestClient) -> None:
    """
    Given a created link,
    when its created_at is read off the wire,
    then it ends in Z: the instant is unambiguous, which is what rule 9 -- always aware, never a
    naive datetime -- buys once it reaches a client.
    """
    assert _post(client, TARGET).json()["created_at"].endswith("Z")


def test_the_codes_run_in_sequence(client: TestClient) -> None:
    """
    Given three different URLs,
    when each is shortened,
    then the codes are the first three ids in base 62, padded to seven characters.
    """
    codes = [_post(client, f"https://example.com/{index}").json()["code"] for index in range(3)]

    assert codes == ["0000001", "0000002", "0000003"]
