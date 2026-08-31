"""The two statements that carry this project's argument, compiled and read.

What these tests do *not* do is run anything: there is no database here, so nothing below proves
that PostgreSQL behaves as claimed. That is Fase 5's job, with Testcontainers. What they pin is the
half a passing integration test would not notice -- `INSERT ... ON CONFLICT DO NOTHING` and a
plain `INSERT` behave identically until two requests race, and a suite that never races would stay
green while the clause that closes the window quietly disappeared.

They are unit tests in the strict sense of this project: no Docker, no database, no network.
"""

from url_shortener.adapter.persistence.database.session import create_database_engine
from url_shortener.adapter.persistence.link_repository_impl import (
    NEXT_ID_STATEMENT,
    insert_link_statement,
)

# The dialect statements are compiled against is the application's own, taken off a real engine
# built from an unreachable DSN. Compiling against a bare `postgresql.dialect()` would test a
# driver this project does not use; building the engine connects to nothing.
DIALECT = create_database_engine(
    "postgresql+psycopg://nobody:nothing@203.0.113.7:5432/nowhere"
).dialect

VALUES: dict[str, object] = {
    "id": 7,
    "code": "0000007",
    "url": "https://example.com/a",
    "url_hash": "0" * 64,
    "created_at": None,
}


def _insert_sql() -> str:
    """The insert as PostgreSQL will receive it."""
    return str(insert_link_statement(VALUES).compile(dialect=DIALECT))


def test_the_id_comes_from_the_sequence_and_not_from_the_table() -> None:
    """
    Given the statement that takes the next id,
    when it is compiled,
    then it is `nextval` on the sequence -- not `max(id) + 1`, which two concurrent requests read
    identically, and not a value the insert assigns, which would arrive too late for the code to be
    computed from it.
    """
    sql = str(NEXT_ID_STATEMENT.compile(dialect=DIALECT))

    assert "nextval('link_id_seq')" in sql
    assert "FROM link" not in sql
    assert "max" not in sql.lower()


def test_the_insert_suppresses_a_conflict_on_the_digest() -> None:
    """
    Given the statement that saves a link,
    when it is compiled,
    then it carries `ON CONFLICT (url_hash) DO NOTHING`.

    This one clause is what closes the deduplication race. Between the SELECT that found nothing and
    this INSERT, another request can insert the same URL; only the unique index decides who wins,
    and only `DO NOTHING` turns losing into a value to handle instead of an IntegrityError.
    """
    assert "ON CONFLICT (url_hash) DO NOTHING" in _insert_sql()


def test_the_conflict_target_is_never_the_code() -> None:
    """
    Given the same statement,
    when it is compiled,
    then it names no other conflict target -- a duplicate code is impossible by construction, so a
    collision there is a broken invariant and has to keep failing loudly rather than being
    swallowed by a wider `ON CONFLICT`.
    """
    sql = _insert_sql()

    assert sql.count("ON CONFLICT") == 1
    assert "ON CONFLICT (code)" not in sql
    assert "ON CONFLICT DO NOTHING" not in sql


def test_the_insert_reports_what_it_did_with_returning() -> None:
    """
    Given the same statement,
    when it is compiled,
    then it ends in `RETURNING link.id`.

    `rowcount` is not an alternative here and the difference is not stylistic: for an INSERT without
    RETURNING, SQLAlchemy does not memoise the count and soft-closes the cursor, and psycopg resets
    `rowcount` to -1 on close -- so the value read back would be -1 rather than the 0 a suppressed
    conflict should produce, and `save` would report that it inserted a row it did not insert.
    """
    assert _insert_sql().rstrip().endswith("RETURNING link.id")


def test_the_insert_writes_every_column_of_the_table() -> None:
    """
    Given the values the mapper produces,
    when the statement is compiled,
    then the column list is exactly the table's -- the code is written by this one statement, so
    `code NOT NULL` never needs a follow-up UPDATE to be satisfied.
    """
    sql = _insert_sql()

    assert sql.startswith("INSERT INTO link (id, code, url, url_hash, created_at) VALUES")
