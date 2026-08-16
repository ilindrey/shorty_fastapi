FROM python:3.14.7-alpine3.24 AS base
FROM base AS production-builder

COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /uvx /bin/
ENV \
    UV_CACHE_DIR=/cache \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_LOCKED=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_SYSTEM_PYTHON=1

WORKDIR /app

RUN --mount=type=cache,target=/cache \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --no-dev --no-editable --no-install-project

FROM production-builder AS test-builder

RUN --mount=type=cache,target=/cache \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --no-editable --no-install-project

FROM base AS test

COPY --from=test-builder /app/.venv/ /app/.venv/
COPY . /app/

WORKDIR /app
ENV \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src"

FROM base AS production

COPY --from=production-builder /app/.venv/ /app/.venv/
COPY . /app/

WORKDIR /app
ENV \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src"
