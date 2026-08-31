"""Shorten a URL."""

from typing import Protocol

from url_shortener.application.viewmodel.create_link_command import CreateLinkCommand
from url_shortener.application.viewmodel.link_result import LinkResult


class CreateLinkUseCase(Protocol):
    """Turn a target URL into a link, or hand back the link it already has."""

    def create(self, command: CreateLinkCommand) -> LinkResult:
        """Shorten the URL in the command.

        Raises `InvalidTargetUrlError` when the domain policy refuses the target, which the web
        adapter answers with `400`. The same URL asked for twice yields the same link, and
        `LinkResult.was_created` says which of the two happened.
        """
        ...
