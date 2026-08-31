"""Turning a path segment into a link, which is the one step both read use cases share."""

import pytest

from tests.fakes import InMemoryLinkRepository
from tests.mothers import LinkMother
from url_shortener.application.usecase.link_lookup import require_link
from url_shortener.domain.exception.link_not_found_error import LinkNotFoundError
from url_shortener.domain.model.link import Link
from url_shortener.domain.model.short_code import ShortCode
from url_shortener.domain.service.url_hash import hash_url


class _RepositoryWithACorruptRow(InMemoryLinkRepository):
    """A store whose row cannot be turned into a link, the way a naive timestamp would do it.

    This is a bug and not a missing link, so it must not come out of here as "not found".
    """

    def find_by_code(self, code: ShortCode) -> Link | None:
        raise ValueError("occurred_at must be timezone aware")


def test_a_stored_code_yields_the_link_it_names() -> None:
    """
    Given a stored link,
    when its code is looked up,
    then the link comes back.
    """
    links = InMemoryLinkRepository()
    link = LinkMother.first()
    links.save(link, url_hash=hash_url(link.url))

    assert require_link(links, str(link.code)) is link


def test_a_malformed_code_becomes_not_found_and_keeps_the_original_failure() -> None:
    """
    Given a path segment that is not a code,
    when it is looked up,
    then it becomes LinkNotFoundError, with the ValueError that rejected it still on the chain --
    the answer is "not found", and the reason is not thrown away.
    """
    with pytest.raises(LinkNotFoundError) as caught:
        require_link(InMemoryLinkRepository(), "favicon.ico")

    assert isinstance(caught.value.__cause__, ValueError)


def test_a_well_formed_code_that_names_nothing_has_no_cause_to_chain() -> None:
    """
    Given a code that parses but matches no row,
    when it is looked up,
    then it is also LinkNotFoundError, and this one chains nothing: the two failures give the
    caller one answer while staying two different things inside.
    """
    with pytest.raises(LinkNotFoundError) as caught:
        require_link(InMemoryLinkRepository(), "0000009")

    assert caught.value.__cause__ is None


def test_a_failure_from_the_repository_is_not_dressed_up_as_not_found() -> None:
    """
    Given a store that raises ValueError while reading a row,
    when a valid code is looked up,
    then that ValueError travels on untouched: only the parse is inside the try, so a corrupt row
    stays the internal error it is instead of becoming a 404 that hides it.
    """
    with pytest.raises(ValueError, match="timezone aware"):
        require_link(_RepositoryWithACorruptRow(), "0000001")
