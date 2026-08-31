"""Follow a short code to its destination, recording the access."""

from ipaddress import IPv4Address, IPv6Address

from url_shortener.application.port.outbound.click_repository import ClickRepository
from url_shortener.application.port.outbound.clock import Clock
from url_shortener.application.port.outbound.link_repository import LinkRepository
from url_shortener.application.usecase.link_lookup import require_link
from url_shortener.application.viewmodel.redirect_result import RedirectResult
from url_shortener.domain.model.click import Click


class ResolveLinkUseCaseImpl:
    """The hot path: one lookup, one append, and the destination back."""

    def __init__(self, links: LinkRepository, clicks: ClickRepository, clock: Clock) -> None:
        self._links = links
        self._clicks = clicks
        self._clock = clock

    def resolve(
        self,
        code: str,
        *,
        user_agent: str | None,
        referer: str | None,
        ip: IPv4Address | IPv6Address | None,
    ) -> RedirectResult:
        """Resolve the code and append one click."""
        # The lookup comes first, so a code that names nothing writes nothing. A click pointing at
        # a link that does not exist would be a row the foreign key refuses anyway.
        link = require_link(self._links, code)

        # Nothing catches this. A failure to record the access fails the redirect, and that is the
        # decision rather than an oversight: there is no queue and no outbox here, so swallowing it
        # would turn a database failure on the only write path of this route into a log line with
        # no second alarm behind it. A link that quietly stops being measured is exactly what
        # answering 302 instead of 301 exists to prevent.
        self._clicks.record(
            Click(
                link_id=link.id,
                occurred_at=self._clock.now(),
                user_agent=user_agent,
                referer=referer,
                ip=ip,
            )
        )

        return RedirectResult(target_url=link.url)
