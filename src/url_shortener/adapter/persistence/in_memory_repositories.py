"""The driven ports, backed by dictionaries instead of PostgreSQL.

**Temporary, and deleted in Fase 4.** It exists so that Fase 3 has a process that actually runs:
the acceptance criterion of the phase is `uvicorn` answering a real `POST /links` followed by a
real `302`, and there is no schema, no migration and no engine yet. Fase 4 replaces the two
provider functions in `adapter/config/dependencies.py` and removes this file, and nothing under
`adapter/web/` changes -- which is the demonstration that phase promises.

**This is not the test fake, and it must not become one.** `tests/fakes.py` carries affordances
that exist to write assertions with -- `insert_before_next_save` to open the race window,
`issued_ids`, `rows` -- and production code has no business exposing them. Two small in-memory
implementations is the cost, and it is paid for one phase.

What this models and the fake does not is concurrency. FastAPI runs `def` endpoints in a
threadpool, so two requests really do touch these dictionaries at the same time, and the lock is
where PostgreSQL's `nextval` and its unique index would have been.

**The lock cannot be shown to fail on this interpreter, and that was measured rather than
assumed.** Under CPython 3.13's GIL the read-modify-write in `next_id` never interleaves: the
eval breaker is only checked at a few instruction boundaries, and none of them sits between the
load and the store. Removing every lock in this file and running 32 threads through 20 000
increments each, with `sys.setswitchinterval(1e-9)`, produced zero duplicate ids across repeated
runs. So no test here claims to prove the lock -- a check that cannot fail for the reason that
matters is worse than no check. The lock stays because GIL atomicity is an implementation detail
and not a language guarantee: on a free-threaded build the same code races, and this file would
then hand out one id twice, which means one code twice.

What it deliberately does *not* model is durability: restart the process and every link is gone.
"""

import threading

from url_shortener.domain.model.click import Click
from url_shortener.domain.model.link import Link
from url_shortener.domain.model.short_code import ShortCode
from url_shortener.domain.service.url_hash import UrlHash


class InMemoryLinkRepository:
    """The `link` table as two dictionaries, a counter and a lock.

    The two dictionaries are the two unique indexes that carry meaning: one on the URL digest,
    which deduplication rides on, and one on the code, which is how a redirect finds a link.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._issued_ids = 0
        self._by_hash: dict[UrlHash, Link] = {}
        self._by_code: dict[ShortCode, Link] = {}

    def next_id(self) -> int:
        """Take the next sequence value, spent whether or not a row follows.

        Under the lock because `+= 1` is a read, an add and a write, and two threads interleaving
        there hand out the same id twice -- which means the same code twice, and the unique index
        that would have caught it is the one below. A real sequence gets this atomicity from the
        database.
        """
        with self._lock:
            self._issued_ids += 1
            return self._issued_ids

    def find_by_code(self, code: ShortCode) -> Link | None:
        """The link answering to this code, or `None`."""
        with self._lock:
            return self._by_code.get(code)

    def find_by_url_hash(self, url_hash: UrlHash) -> Link | None:
        """The link already pointing at the URL behind this digest, or `None`."""
        with self._lock:
            return self._by_hash.get(url_hash)

    def save(self, link: Link, *, url_hash: UrlHash) -> bool:
        """Insert unless the digest is taken, exactly as `ON CONFLICT (url_hash) DO NOTHING` does.

        The check and the two writes are one critical section, for the same reason the real
        statement is one statement: split them and two requests both read "not taken" and both
        insert, which is the very race the unique index exists to close.
        """
        with self._lock:
            if url_hash in self._by_hash:
                return False
            self._by_hash[url_hash] = link
            self._by_code[link.code] = link
            return True


class InMemoryClickRepository:
    """The `click` table as a list, which is all an append-only table needs."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._recorded: list[Click] = []

    def record(self, click: Click) -> None:
        """Append one access. Nothing is ever updated or removed."""
        with self._lock:
            self._recorded.append(click)

    def count_by_link(self, link_id: int) -> int:
        """Count by scanning, never by keeping a running total.

        A maintained counter here would be the design the schema refuses, and it would hide a
        double count behind a number that always looks plausible.
        """
        with self._lock:
            return sum(1 for click in self._recorded if click.link_id == link_id)
