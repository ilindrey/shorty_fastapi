FROM python:3.13.3-alpine3.21 as base

FROM base as builder

# install UV
COPY --from=ghcr.io/astral-sh/uv:0.7.8 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --no-dev --frozen

FROM base

COPY --from=builder /app/.venv /app/.venv
COPY . /app/

WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH"
