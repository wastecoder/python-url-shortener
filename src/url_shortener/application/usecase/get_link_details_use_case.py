"""Report what is known about a link."""

from url_shortener.application.port.outbound.click_repository import ClickRepository
from url_shortener.application.port.outbound.link_repository import LinkRepository
from url_shortener.application.usecase.link_lookup import require_link
from url_shortener.application.viewmodel.link_details_result import LinkDetailsResult


class GetLinkDetailsUseCaseImpl:
    """One lookup and one count.

    Two ports and no `Clock`: this use case only reads, so it has nothing to stamp. A constructor
    parameter that is stored and never read is a lie the wiring file then has to keep telling, and
    every constructor here advertises exactly what its use case touches.
    """

    def __init__(self, links: LinkRepository, clicks: ClickRepository) -> None:
        self._links = links
        self._clicks = clicks

    def get_details(self, code: str) -> LinkDetailsResult:
        """Read the link named by the code, together with its click total."""
        link = require_link(self._links, code)
        return LinkDetailsResult(
            code=str(link.code),
            url=link.url,
            created_at=link.created_at,
            # A `COUNT`, never a column on `link`. The number is derived from the rows that exist,
            # so it cannot drift from them, and the price is paid on this cold path rather than by
            # every redirect contending for one row lock.
            total_clicks=self._clicks.count_by_link(link.id),
        )
