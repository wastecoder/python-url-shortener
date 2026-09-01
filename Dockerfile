# syntax=docker/dockerfile:1

# Two stages: one that has uv and builds the virtualenv, one that has no uv at all and only runs
# what the first produced.
#
# Both start from the SAME base image, and uv arrives as a binary copied in rather than as the
# `ghcr.io/astral-sh/uv:python3.13-bookworm-slim` base. A virtualenv records the absolute path of
# the interpreter that created it, so a builder and a runtime whose Pythons differ produce a
# `.venv` that copies over cleanly and then fails to start. One `FROM` for both makes that a fact
# of this file instead of a coincidence between two tags that happen to agree today.

FROM python:3.13-slim-bookworm AS builder

# Pinned to the uv this repository is developed with. `latest` here would mean `uv.lock` is read by
# whichever version the build happened to pull that morning.
COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /usr/local/bin/uv

# `UV_COMPILE_BYTECODE` so the `.pyc` files ship inside the image, instead of the first request
# after every container start paying for compiling them.
# `UV_LINK_MODE=copy` because the cache below is a mount and therefore a different filesystem, where
# uv's default hardlinking cannot work; without it uv warns and falls back to this anyway.
# `UV_PYTHON_DOWNLOADS=never` is the one that is load-bearing: left alone, uv is free to download an
# interpreter of its own and build the virtualenv against it, which is exactly the mismatch the
# shared base image above exists to prevent.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# The dependencies, alone, in a layer of their own -- because they and the source change at very
# different rates. Nothing from `src/` is in the context of this instruction, so editing the
# application does not re-resolve, re-download or reinstall anything.
#
# `--mount=type=bind` rather than `COPY`: these two files are read to resolve the environment and are
# not needed *in this layer* afterwards, so binding them keeps the layer's inputs down to the two
# files themselves. They are copied in properly further down, where the project is installed.
# `--locked` fails if `uv.lock` disagrees with `pyproject.toml`, which turns a stale lock file into
# a build error rather than an image built from a resolution nobody reviewed.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-install-project --no-dev

COPY pyproject.toml uv.lock README.md ./
COPY src/ src/

# `--no-editable` installs the project as a built wheel instead of a link back to `src/`. That is
# what lets the stage below copy the virtualenv and nothing else: with the default editable install
# the `.venv` would point at a directory that does not exist in the final image, and the failure
# would be an `ImportError` at container start rather than anything a build reports.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable


FROM python:3.13-slim-bookworm AS runtime

# The virtualenv goes on `PATH` instead of being activated: `activate` is a script that a shell has
# to source, and the exec-form `CMD` at the bottom of this file deliberately runs no shell.
# `PYTHONDONTWRITEBYTECODE` because the virtualenv's `.pyc` files were compiled into the image by the
# builder, and `migrations/` -- the one tree here that arrives as plain source -- is read by a user
# that does not own it, so the write would fail silently anyway. The flag turns a pointless failed
# write per migration run into no write at all.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# A system user with a fixed uid, no home and no login shell. Fixed because ownership on a mount is
# a number and not a name, so a uid the distribution happens to allocate can move between base
# image releases and take a volume's permissions with it. Root is the default and there is no
# reason to accept it: nothing in this image writes to disk.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

# Copied without `--chown`: root owns them, mode 0755/0644, which is exactly the read and execute
# the user below needs. Handing them to that user would let the process rewrite the code it is
# running, and nothing here writes.
COPY --from=builder /app/.venv /app/.venv

# The migration runs from this same image, as its own service in `compose.yml`, so the image
# carries what Alembic reads. `src/` is deliberately absent -- the application itself is installed
# in the virtualenv above, and `migrations/env.py` imports it from there.
COPY alembic.ini ./
COPY migrations/ migrations/

USER app

EXPOSE 8000

# `urllib` from the standard library, because a slim image has no curl and adding one would be
# paying attack surface for a convenience. A `503` from `/health` raises `HTTPError`, which exits
# non-zero, which is what an unhealthy container is -- so this check reports the database being
# down and not merely the process being up. The port is written out because `HEALTHCHECK` has no
# access to the port `CMD` was given; both are 8000 and changing one means changing the other.
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]

# One uvicorn process and no `--workers`: a container is one process, and how many of them run is a
# replica count, which belongs to whatever schedules the containers and not to the image. Exec form
# so uvicorn is pid 1 and receives the `SIGTERM` that `docker compose down` sends, instead of a
# shell receiving it and exiting without passing it on -- which is the difference between a
# graceful stop and a ten-second wait followed by `SIGKILL`.
CMD ["uvicorn", "url_shortener.main:app", "--host", "0.0.0.0", "--port", "8000"]
