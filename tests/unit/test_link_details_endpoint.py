"""`GET /links/{code}`: the link, its age, and the click total derived from rows.

The clicks are written straight into the store here rather than earned by following the link. This
endpoint is being tested, not the redirect: driving one endpoint through another would make these
assertions fail for reasons that have nothing to do with them. The two are joined up in the
redirect suite, which follows a link and then reads the total back.
"""

from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from tests.fakes import InMemoryClickRepository
from tests.unit.conftest import BASE_URL, NOW, NOW_ON_THE_WIRE
from url_shortener.domain.model.click import Click
from url_shortener.domain.service.base62 import decode

TARGET = "https://example.com/a"


def _create(client: TestClient, url: str = TARGET) -> str:
    return str(client.post("/links", json={"url": url}).json()["code"])


def _record(clicks: InMemoryClickRepository, code: str, times: int) -> None:
    for _ in range(times):
        clicks.record(Click(link_id=decode(code), occurred_at=NOW))


def test_a_known_code_answers_with_the_link_and_a_zero_total(client: TestClient) -> None:
    """
    Given a link nobody has followed,
    when its details are read,
    then the body carries the five fields of the contract and a total of zero -- zero because no
    row exists, and not because a counter was initialised.
    """
    code = _create(client)

    response = client.get(f"/links/{code}")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "code": code,
        "short_url": f"{BASE_URL}/{code}",
        "url": TARGET,
        "created_at": NOW_ON_THE_WIRE,
        "total_clicks": 0,
    }


def test_the_total_counts_the_rows_that_exist(
    client: TestClient, clicks: InMemoryClickRepository
) -> None:
    """
    Given a link with three clicks recorded against it,
    when its details are read,
    then the total is three, because it is a count over rows and not a stored number.
    """
    code = _create(client)
    _record(clicks, code, times=3)

    assert client.get(f"/links/{code}").json()["total_clicks"] == 3


def test_the_total_counts_only_this_links_clicks(
    client: TestClient, clicks: InMemoryClickRepository
) -> None:
    """
    Given two links, only one of which has clicks,
    when both are read,
    then each total covers its own rows.
    """
    followed = _create(client)
    ignored = _create(client, "https://example.com/b")
    _record(clicks, followed, times=2)

    assert client.get(f"/links/{followed}").json()["total_clicks"] == 2
    assert client.get(f"/links/{ignored}").json()["total_clicks"] == 0


def test_reading_the_details_records_nothing(
    client: TestClient, clicks: InMemoryClickRepository
) -> None:
    """
    Given a link,
    when its details are read twice,
    then no click was recorded: asking how often a link was followed is not following it, and a
    read that counted would change the number by being asked for it.
    """
    code = _create(client)

    client.get(f"/links/{code}")
    client.get(f"/links/{code}")

    assert clicks.recorded == ()


def test_the_location_of_a_created_link_is_the_url_that_reads_it(client: TestClient) -> None:
    """
    Given the Location header of a 201,
    when that path is requested,
    then it answers with the link's details -- which is what makes the header the address of the
    resource that was created rather than a decoration.
    """
    created = client.post("/links", json={"url": TARGET})
    path = created.headers["location"].removeprefix(BASE_URL)

    response = client.get(path)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["code"] == created.json()["code"]


@pytest.mark.parametrize(
    "code",
    ["zzzzzzz", "short", "waytoolongforacode", "abcdef!", "0000001x", "0000-01"],
)
def test_an_unknown_or_malformed_code_answers_404(client: TestClient, code: str) -> None:
    """
    Given a code that names no link, or a value that is not a code at all,
    when the details are read,
    then both answer the same 404 problem document -- telling them apart would tell somebody
    enumerating codes which of their guesses were at least well formed.
    """
    response = client.get(f"/links/{code}")

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "link-not-found"


def test_the_code_is_case_sensitive(client: TestClient) -> None:
    """
    Given the tenth link, whose code carries a letter,
    when the same code is read with that letter in upper case,
    then it answers 404: base 62 is case sensitive, so `000000a` and `000000A` are two different
    codes -- and the second one is the code of link 36, which does not exist.
    """
    codes = [_create(client, f"https://example.com/{index}") for index in range(10)]
    lettered = codes[-1]

    assert lettered == "000000a"
    assert client.get(f"/links/{lettered}").status_code == HTTPStatus.OK
    assert client.get(f"/links/{lettered.upper()}").status_code == HTTPStatus.NOT_FOUND
