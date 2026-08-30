# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project context
**url-shortener** is a small HTTP API that turns a long URL into a 7-character code and redirects
that code back to the original URL, recording every access. It is a **learning/portfolio project**
built to practice **Python, FastAPI, SQLAlchemy, PostgreSQL, Testcontainers, Docker and CI** — and
to be defended, decision by decision, in a technical interview.

**The project is small on purpose, and that is the point.** It is not judged by how much it does;
it is judged by how well every decision can be justified. Four routes with integration tests
against a real database, a CI that blocks merge, and a README that explains the trade-offs are
worth more here than twenty routes without any of that.

The short-code design follows chapter 8 ("Design a URL Shortener") of Alex Xu's *System Design
Interview* — **62-character alphabet, length 7, sequential id converted to base 62** — with the
pieces that only exist there because of scale (distributed id generator, Redis cache, bloom
filter, sharding) **deliberately removed**. Knowing which pieces were removed and why is the most
valuable output of this project.

The step-by-step build order lives in `docs/PROGRESS-V1.md` (the minimum viable scope) and
`docs/PROGRESS-V2.md` (everything cut on purpose). The root `README.md` is the primary artifact a
reviewer reads: problem in three sentences, flow diagram, one command to run it, a **decisions**
section, and the **what was left out** table. `docs/adr/` holds short numbered ADRs.

## Scope guard
**In scope (V1):** create link, redirect, read link metadata, health. Nothing else.

**Deliberately out of V1 — do not add these unless explicitly asked:** web UI, message queue,
link expiration, custom alias, statistics/aggregation endpoints, authentication, rate limiting,
Redis cache, distributed id generation, sharding, any LLM. Each one has a prepared answer in the
"what was left out" table of the README; adding one silently destroys that answer.

If a change looks like it needs one of the above, **say so and stop** — it belongs in
`docs/PROGRESS-V2.md`, not in the code.

## Language convention
- **Code** — modules, packages, classes, functions, variables, database tables and columns,
  comments, logs, commit messages, branch names, PR titles/descriptions — is written in **English**.
- **Documentation** — everything under `docs/` (including `docs/adr/`) and the root `README.md` — is
  written in **Portuguese**.
- **This file** (`CLAUDE.md`) is written in **English**.

The design brief this project derives from uses Portuguese identifiers (`dominio`, `clique`,
`criado_em`, `quando`). **Do not copy them.** The equivalents here are `domain`, `click`,
`created_at`, `occurred_at`.

## Repository layout
Single Python package, `src` layout, managed by **uv**.

```
url-shortener/
├─ CLAUDE.md                  # this file
├─ README.md                  # problem, diagram, how to run, decisions, what was left out
├─ pyproject.toml             # deps + ruff, mypy, pytest, coverage config
├─ uv.lock
├─ .python-version            # 3.13
├─ .env.example               # versioned; .env is gitignored
├─ .importlinter              # hexagonal layer contracts, enforced in CI
├─ compose.yml                # api + postgres
├─ Dockerfile                 # multi-stage
├─ alembic.ini
├─ migrations/                # Alembic (versions/)
├─ .github/workflows/ci.yml
├─ docs/
│  ├─ PROGRESS-V1.md          # minimum scope, phase by phase
│  ├─ PROGRESS-V2.md          # what was cut on purpose
│  ├─ adr/000N-*.md           # short numbered ADRs, Portuguese
│  └─ learning/               # one note per finished phase — GITIGNORED, not part of the repo
├─ src/url_shortener/         # see Architecture below
└─ tests/
   ├─ conftest.py
   ├─ mothers.py              # Object Mother fixtures
   ├─ unit/                   # no Docker, no database, fast
   └─ integration/            # Testcontainers, marked `integration`
```

`docs/` stays minimal on purpose. The README carries architecture and API; splitting them into
`ARCHITECTURE.md` / `API.md` is only worth it if the project grows past V1.

## Architecture (hexagonal / ports & adapters — horizontal layout)
Dependencies point **inward**: `adapter -> application -> domain`.

- `domain` imports **only the standard library**. No FastAPI, no SQLAlchemy, no Pydantic, no
  Starlette. It is testable with no infrastructure running at all.
- `application` imports **only `domain` plus stdlib/typing**. Ports are `typing.Protocol`.
- `adapter` may import everything. It is the only layer that knows a framework exists.

Packages below are relative to `src/url_shortener/`.

| Layer | Package | Naming / examples |
|---|---|---|
| Domain model | `domain.model` | frozen dataclasses — `Link`, `Click`, `ShortCode` |
| Domain services (pure) | `domain.service` | `base62.py` (`encode`/`decode`), `url_policy.py` (target validation + reserved codes) |
| Domain errors | `domain.exception` | `DomainError` base; `InvalidTargetUrlError`, `LinkNotFoundError`, `ReservedCodeError` |
| Driving ports | `application.port.inbound` | `Protocol` — `CreateLinkUseCase`, `ResolveLinkUseCase`, `GetLinkDetailsUseCase` |
| Driven ports | `application.port.outbound` | `Protocol` — `LinkRepository`, `ClickRepository`, `Clock` |
| Use cases | `application.usecase` | `CreateLinkUseCaseImpl` in `create_link_use_case.py`, one file per use case |
| Boundary DTOs | `application.viewmodel` | frozen dataclasses — `CreateLinkCommand`, `LinkResult`, `RedirectResult` |
| Web adapter (in) | `adapter.web` | `link_controller.py`, `redirect_controller.py`, `health_controller.py`; Pydantic v2 models in `dto/request/` and `dto/response/`; `handler/problem_details.py` and `handler/problem_type.py` |
| Persistence adapter (out) | `adapter.persistence` | `link_repository_impl.py`, `click_repository_impl.py` at the root; SQLAlchemy models in `entity/`, entity-to-domain conversion in `mapper/`, engine/session in `database/` |
| Config | `adapter.config` | `settings.py` (pydantic-settings), `dependencies.py` (FastAPI `Depends` wiring), `clock.py` (`SystemClock`) |

`main.py` builds the FastAPI app: registers exception handlers, then routers **in the order
required below**.

### Python-specific rules for this layout
- **`inbound`/`outbound`, not `in`/`out`.** `in` is a reserved keyword — `application.port.in` is a
  syntax error on import. This is the only intentional deviation from the Java package names.
- **Ports are `typing.Protocol`, not ABCs.** Adapters do not inherit from them; mypy verifies the
  shape structurally. This keeps the adapter free of any import from `application`.
- **The `...Impl` suffix is kept** for use-case and repository implementations. It is un-Pythonic
  and intentional: it mirrors the Java project this layout comes from and makes the port/adapter
  pair obvious at a glance.
- **Controllers depend on inbound ports, never on `...Impl`.** Wiring happens exactly once, in
  `adapter/config/dependencies.py`.
- **No Pydantic in `domain` or `application`.** Pydantic belongs to the web adapter
  (request/response DTOs) and to `settings.py`. Crossing that line is the most likely way to
  accidentally break the hexagon.

### Enforcement
The dependency rule is checked by **import-linter** (`.importlinter`) and runs in CI. Contracts:

1. **Layers:** `url_shortener.adapter` -> `url_shortener.application` -> `url_shortener.domain`.
2. **Forbidden:** `url_shortener.domain` must not import `fastapi`, `starlette`, `sqlalchemy`,
   `pydantic`, `alembic`.
3. **Forbidden:** `url_shortener.application` must not import `fastapi`, `starlette`, `sqlalchemy`,
   `pydantic`, `alembic`.

If a contract fails, **fix the import — do not relax the contract.** Changing `.importlinter`
requires an ADR.

## Runtime model — synchronous, on purpose
**Every endpoint is `def`, never `async def`.** The ports are sync, the use cases are sync,
SQLAlchemy is used in sync mode over `psycopg`, and the tests use `fastapi.testclient.TestClient`.
There is no `pytest-asyncio` in this project.

FastAPI runs `def` endpoints in a threadpool, which is the right shape at this scale — the
bottleneck is a PostgreSQL round trip, not concurrency in the process. The failure this rule
prevents is the classic one: a **sync driver called from inside `async def` blocks the event
loop**, which is measurably worse than staying sync.

Async is not forbidden forever, but it is **all or nothing**: making one controller `async def`
means the use case, both repository ports and both repository implementations become `async def`
too, because the port signatures are what carry it. Anything less is the bug above. Switching is a
V2 decision and needs an ADR.

## Domain rules and invariants
These are the load-bearing decisions. Changing any of them changes what this project is.

**1. Short code generation.** `id = nextval(link_id_seq)`, then `base62(id)`, then left-padded with
`0` to **exactly 7 characters**. The id is read from the sequence **before** the insert, so the
code can be computed in the pure domain and the row is inserted with `code NOT NULL` in a single
statement. The alphabet is `0-9a-zA-Z` (62 chars); `62^7` is roughly `3.52e12`. Sequence gaps from
rolled-back transactions are expected and harmless.

**2. Codes are fixed-length 7, so reserved words cannot be generated.** None of `docs`, `redoc`,
`openapi.json`, `health` and `links` is exactly 7 characters long — four are shorter and
`openapi.json` is 12 — which makes collision structurally impossible. The reserved-code list in `domain.service.url_policy` **still exists** as
a guard for any future path that *chooses* a code instead of generating one (custom alias, import,
bug in the generator). It is a safety net, not the mechanism — and knowing the difference is the
point.

**3. Route registration order is load-bearing.** `GET /{code}` is a catch-all at the root. It must
be registered **last**, after `/links`, `/health`, `/docs`, `/redoc` and `/openapi.json`, or it
swallows all of them. This and rule 2 are the same problem seen from two sides: one solved in
routing, the other in the generator.

**4. The redirect is `302`, never `301`, never `307`.** Starlette's `RedirectResponse` defaults to
`307` — always pass `status_code=302` explicitly. `301` is cached by the browser, which kills click
measurement and makes the destination impossible to change or disable afterwards. `307` preserves
the HTTP method, which is not what a short link means.

**5. Target URL validation.** Accept `http` and `https` only. Reject everything else (`file://`,
`javascript:`, `data:`), and reject `localhost`, loopback, private, link-local and otherwise
reserved IP ranges, plus URLs carrying credentials. A shortener that accepts anything becomes a
tool for attacking its own infrastructure and for laundering phishing links.

**6. Deduplication is guaranteed by a constraint, not by a check in Python.** The flow:

1. `url_hash = sha256(url).hexdigest()`
2. `SELECT` by `url_hash` — if found, return the existing link (`200`), fast path
3. otherwise `nextval`, then `base62`, then `INSERT ... ON CONFLICT (url_hash) DO NOTHING`
4. if the insert returned no row (a concurrent request won the race), `SELECT` by `url_hash` and
   return that one (`200`)

Steps 2 and 4 exist because between the `SELECT` that found nothing and the `INSERT`, another
request can insert. Only the unique constraint closes that window. **Never replace step 3 with a
check-then-insert.**

**7. The unique index is on `sha256(url)`, not on `url`.** A PostgreSQL btree entry has a size
limit (around 2.7 KB) and a URL has no defined length. Hashing gives a fixed-size key.

**8. Clicks are append-only.** `INSERT` into `click`; the total is a `COUNT` on read. **Never** add
a counter column to `link` and never `UPDATE link SET clicks = clicks + 1`: that is a write on the
read path, on the same row, and two simultaneous hits on a viral link contend for that row lock.
The `INSERT` contends with nothing. This trades contention on the hot path for work on the cold
path, and that is the correct trade here.

**9. Timestamps come from the `Clock` port, not from a database default.** The domain owns
`created_at` and `occurred_at`, which makes them freezable in tests. **Always `datetime.now(UTC)`,
never a naive datetime**, and the columns are `TIMESTAMPTZ`. A naive datetime crossing into the
database is the classic Python date bug and it is silent — it only shows up when two machines
disagree about what "now" was.

## Data model
Two tables. Column names in English.

| Table | Columns |
|---|---|
| `link` | `id BIGSERIAL PK` (the id generator), `code TEXT UNIQUE NOT NULL`, `url TEXT NOT NULL`, `url_hash CHAR(64) UNIQUE NOT NULL`, `created_at TIMESTAMPTZ NOT NULL` |
| `click` | `id BIGSERIAL PK`, `link_id BIGINT NOT NULL REFERENCES link(id)`, `occurred_at TIMESTAMPTZ NOT NULL`, `user_agent TEXT`, `referer TEXT`, `ip INET` |

`click` never receives an `UPDATE` or a `DELETE`. Index `click(link_id)` for the `COUNT`.

Schema changes go through **Alembic migrations only** — never `Base.metadata.create_all()`, not
even in tests. Tests run the same migrations production runs.

## API contract
| Method | Path | Success | Notes |
|---|---|---|---|
| `POST` | `/links` | `201 Created` (new) or `200 OK` (dedup hit) | body: `code`, `short_url`, `url`, `created_at`; `Location` header on `201` |
| `GET` | `/{code}` | `302 Found` | `Location: <long url>`; records the click |
| `GET` | `/links/{code}` | `200 OK` | body: `code`, `short_url`, `url`, `created_at`, `total_clicks` |
| `GET` | `/health` | `200 OK` / `503` | runs `SELECT 1` against the database from Fase 4 onward |

`201` versus `200` on `POST /links` is deliberate: `201` means a link was created, `200` means an
existing one was returned. The caller can tell the difference.

`/health` **checks its dependency** — a health check that always answers `200` is a lie, and it is
the difference between this endpoint and a real Actuator. Until persistence exists it returns a
static `{"status": "ok"}`; from Fase 4 it runs `SELECT 1` and answers `503` when the database is
unreachable.

`short_url` is built from the `BASE_URL` setting — the API never guesses its own public host.

The auto-generated `/docs` **is the project's UI**. There is no front-end because none is needed.

## Error handling
**Problem Details (RFC 7807)**, `application/problem+json`. Domain exceptions are HTTP-agnostic;
FastAPI exception handlers in `adapter/web/handler/` map them to responses using a `ProblemType`
enum taxonomy. A domain module must never import a status code.

| Situation | Status | `type` |
|---|---|---|
| Target URL rejected by the domain policy | `400` | `invalid-target-url` |
| Malformed request body (Pydantic) | `422` | `validation-error` |
| Unknown code on `GET /{code}` or `GET /links/{code}` | `404` | `link-not-found` |
| Anything unhandled | `500` | `internal-error` |

`400` versus `422` is the distinction between *the schema is fine but the business rule says no*
and *the payload is not even the right shape*. FastAPI's default validation response is replaced so
every error in the API has the same envelope.

## Commands
`uv` manages the interpreter, the virtualenv and the dependencies. `uv run` handles activation —
never activate `.venv` manually, and never call `pip` directly.

| Task | Command |
|---|---|
| Install / sync dependencies | `uv sync` |
| Add a dependency | `uv add <pkg>` — dev: `uv add --dev <pkg>` |
| Run the API locally (needs `docker compose up -d postgres`) | `uv run uvicorn url_shortener.main:app --reload` |
| Unit tests (fast, no Docker) | `uv run pytest` |
| Integration tests (Testcontainers, needs Docker) | `uv run pytest -m integration` |
| Everything | `uv run pytest -m ""` |
| Coverage | `uv run pytest --cov=src/url_shortener --cov-report=term-missing` |
| Lint | `uv run ruff check .` — fix: `uv run ruff check --fix .` |
| Format | `uv run ruff format .` |
| Types | `uv run mypy src` |
| Architecture contracts | `uv run lint-imports` |
| Apply migrations | `uv run alembic upgrade head` |
| New migration | `uv run alembic revision --autogenerate -m "<message>"` |
| Full local environment | `docker compose up -d` — stop: `docker compose down -v` |

`docker compose up` applies the migrations before starting the API.

**`ruff format` also processes Markdown**, formatting the Python code blocks inside it. So
`ruff format --check` in CI gates the snippets in `README.md` and in the ADRs, not just `src/` and
`tests/` — a badly formatted example in a document turns the pipeline red. `docs/learning/` is
skipped because it is gitignored.

**Known caveat — the repository sits inside a cloud-synced folder.** `.venv/` holds tens of
thousands of small files, so the sync client is slow over it and can occasionally lock a file
mid-write, which surfaces as a `uv sync` failure that looks like a bug in uv. If uv starts behaving
strangely, pause the sync and retry before debugging anything else. `UV_PROJECT_ENVIRONMENT` is
**not** used to work around this: it is a global variable, so pointing it at an absolute path would
make every uv project on the machine share one environment.

Prefer the commands above. **Do not run `git log --oneline` to infer commit conventions** — they are
documented in this file.

## Testing
- **Layout:** `tests/unit/` (no Docker, no database, no network) and `tests/integration/`
  (Testcontainers). Every integration test carries `@pytest.mark.integration`.
- `pyproject.toml` sets `addopts = -m "not integration"`, so a bare `uv run pytest` is always fast
  and always runnable without Docker. This mirrors the `test` / `integrationTest` split of the Java
  project.
- **Everything is synchronous**, so tests use `fastapi.testclient.TestClient`. There is no
  `pytest-asyncio` and no `async def` test — if one appears, the runtime model was broken somewhere
  upstream.
- **Integration tests use Testcontainers** with a real PostgreSQL container, session-scoped, with
  Alembic migrations applied to it. **Do not mock the repository in integration tests** — the whole
  point is verifying *database state*, not a return value. A mocked repository makes tests 2 and 3
  below prove nothing.
- **The three tests that carry this project:**
  1. Create a link and follow the redirect — `POST /links`, then `GET /{code}`, asserting `302` and
     the `Location` header.
  2. Deduplication — `POST` the same URL twice, asserting the same code comes back **and** that
     exactly one row exists in `link`.
  3. The redirect recorded the click — `GET /{code}`, then assert a row landed in `click`.
- **The test worth writing if there is time:** fire two concurrent `POST /links` with the same URL
  and assert exactly one link was created. It is impossible to write with a mock, because what is
  under test is the database's behaviour under concurrency.
- **Unit tests cover the domain properly, not decoratively.** `base62` edge cases (`0`, `1`, `61`,
  `62`, a large id, round-trip `decode(encode(n)) == n`, padding to 7) and every branch of
  `url_policy`. With this scope, the domain module is nearly the whole project.
- **Naming:** files `test_*.py`, functions `test_<behaviour>`. Every test has a docstring in
  Given / When / Then form — the equivalent of the Java project's `@DisplayName`.
- **Fixtures use the Object Mother pattern** in `tests/mothers.py`: a class with a private
  constructor and static scenario factories. No builders.
- **Coverage gate** in CI via `--cov-fail-under`. Mutation testing (the Pitest equivalent, run over
  `domain/` only) belongs to `docs/PROGRESS-V2.md`.

## CI
GitHub Actions on every pull request: `ruff check`, `ruff format --check`, `mypy`, `lint-imports`,
unit tests, integration tests, `docker build`. **Failed, no merge.**

Testcontainers needs a Docker daemon on the runner. `ubuntu-latest` already has one, so the
workflow does **not** declare `services:` — the test starts its own container. That difference is
deliberate and worth being able to explain.

## Secrets
No secret in code, ever. Configuration comes from environment variables through
`adapter/config/settings.py`. `.env.example` is versioned; `.env` is gitignored.

## Commits — Conventional Commits, strictly
Format: `<type>(<optional scope>): <imperative, lower-case summary>`

Accepted types: `feat`, `fix`, `refactor`, `test`, `docs`, `build`, `ci`, `chore`, `perf`, `style`.

Scopes follow the layout: `domain`, `application`, `web`, `persistence`, `config`, `db`, `deps`.

Examples:
- `feat(domain): add base62 encoding with fixed-length 7 output`
- `feat(web): add post /links endpoint returning 201 with location header`
- `feat(persistence): dedupe links through a unique index on the url hash`
- `fix(web): register the catch-all redirect route after /links and /health`
- `refactor(application): move code generation behind the LinkRepository port`
- `test(integration): assert the redirect records a row in click`
- `docs(adr): record why the redirect is 302 and not 301`
- `build(uv): add testcontainers to the dev dependency group`
- `ci(github): run mypy and lint-imports on pull requests`
- `chore(db): add an index on click(link_id)`

Commits are small and readable — **one concept per commit**, because the user reviews the diff, not
the finished file. **Never one giant commit**: the history is part of what is being reviewed.

### Branching and pull requests
Work never lands directly on `main`. One branch and one pull request **per phase** of
`docs/PROGRESS-V1.md`, named `phase-N-<slug>` in English (`phase-0-foundation`,
`phase-1-domain`, `phase-4-persistence`, …). Outside the phase roadmap, use
`feat/<slug>` or `fix/<slug>`.

`main` is protected and requires the CI check to pass — **not** a review, which is impossible to
satisfy alone. This is what makes "the pipeline blocks the merge" a verifiable claim instead of a
sentence: an interviewer can open any pull request and see it. Merge with rebase, so the
one-concept-per-commit history survives on `main` instead of being squashed into one line.

### Co-authorship is PROHIBITED
Never add a `Co-Authored-By:` trailer to any commit — not Claude's
(`Claude <noreply@anthropic.com>`), not anyone's. Never add "Generated with Claude Code" or similar
trailers. Authorship of every commit belongs **exclusively to the user**.

## Progress tracking
When an item in `docs/PROGRESS-V1.md` (or `docs/PROGRESS-V2.md`) is completed, mark it done by
**checking the box and striking the text through**: `- [x] ~~item~~`. Keep `PROGRESS-V1.md` in sync
with reality as work advances.

A checked item is not done until it carries **bold sub-items saying what was actually built** —
decisions taken, module and class names, versions, and why. Every completed item needs a
`Verificado:` sub-item with concrete evidence (the command that ran green, the HTTP response
observed, the `git diff --stat`), plus `Fora deste item:` and `Caveats:` where they apply. **A
checked item with no sub-items does not count as done.**

## Learning notes (`docs/learning/`)
The user is building this project to learn Python, and reviews the code rather than typing it. So
**every finished phase ends with a learning note** at `docs/learning/fase-N-<slug>.md`, in
Portuguese, written before the next phase starts. Fixed structure, in this order:

1. **`## Perguntas`** — 3 to 5 questions in interview form about what the phase just produced
   ("por que 302 e não 301?", "duas requisições simultâneas com a mesma URL, o que acontece?").
   Each question carries **its own answer immediately below it**, wrapped in
   `<details><summary>Resposta</summary> … </details>`, so the user can attempt it before
   revealing. Never collect the answers into a separate section.
2. **`## O que foi feito`** — one section per phase item: the concept, then the **real code excerpt
   from this repository**, then the decision behind it. Retrospective, never a tutorial about the
   library.
3. **`## Exercício de 10 minutos`** — the statement, pointing at
   `docs/learning/exercicio_fase_N.py`: one small function with an empty body plus the test already
   written, runnable with `uv run pytest docs/learning/exercicio_fase_N.py`. The exercise never
   lives in `src/` and never leaves the repository red.
4. **`### Gabarito`** — the solution and why it is written that way, at the end of the same note.

Every note covers both the Python (idiom, stdlib, typing) and the design decision behind it,
because both are what the user is preparing to defend.

`docs/learning/` is in `.gitignore` and **must stay there** — it is the user's study material, not
part of the portfolio. Never commit it, and never reference it from `README.md` or the ADRs.
`docs/PROGRESS-V1.md` names the note that closes each phase; that is the one allowed reference.

## Decisions that must not be changed silently
Each of these has, or will have, a short ADR in `docs/adr/`. Changing one means writing an ADR
first, not editing the code first:

- `302` instead of `301` — measurement and control over cached load.
- Base 62 over the `BIGSERIAL` sequence instead of hashing the URL — no collision by construction;
  the cost is enumerable codes, addressed in V2.
- Deduplication enforced by a unique constraint on `sha256(url)`, never by a check in Python.
- `UNIQUE` on `code` is a safety net, not the mechanism — collision is impossible by construction.
- `click` is append-only; no counter column on `link`.
- No message queue. The click is the only candidate for one, and only at a scale this project does
  not have; link creation is synchronous on purpose, because the caller needs the code back in the
  same request.
- No cache. The repository sits behind a port, so when it is worth it, it goes there and nothing
  else changes.
- No LLM anywhere in the product. A URL is structured by definition; a model would add latency,
  cost and a failure mode without solving anything.
