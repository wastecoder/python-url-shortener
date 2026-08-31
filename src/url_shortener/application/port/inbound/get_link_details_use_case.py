"""Read what is known about a link."""

from typing import Protocol

from url_shortener.application.viewmodel.link_details_result import LinkDetailsResult


class GetLinkDetailsUseCase(Protocol):
    """Report a link's destination, its age and how often it has been followed."""

    def get_details(self, code: str) -> LinkDetailsResult:
        """Read the link named by the code, together with its click total.

        Raises `LinkNotFoundError` when the code names no link, exactly as resolving does.

        Reading the details records nothing. Asking how many times a link was followed is not
        following it, and if it counted, the number would be changed by the act of asking for it.
        """
        ...
