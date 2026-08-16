# Shorty

Shorty turns a long URL into `<domain>/<subpart>`. You can choose the `subpart` and
see how many times each link was opened. The service has no authentication. Instead,
an anonymous signed-cookie session identifies the browser and limits the list to links
created in that session.

## Features

- The web UI combines a creation form with a paginated table of the current session's
  links and click counts.
- A custom `subpart` is optional. The API returns `409 Conflict` if it is already taken.
- Server-side redirect (`307`) from `/<subpart>` to the original URL.
- Redis stores only the `subpart -> url` mapping. New links are written through to the
  cache, and redirects populate it after a miss. Views and querysets are not cached.
- A standalone scheduler process purges expired links from Postgres and Redis in
  bounded keyset pages, one aggregate transaction at a time.
- FastAPI, SQLAlchemy 2.0 with asyncpg, redis.asyncio, and APScheduler's async executor
  provide asynchronous I/O.
- `docker compose up --build` starts the API, cleanup scheduler, Postgres, and Redis,
  then applies migrations automatically.
- Interactive API docs at `/docs` (Swagger UI) and `/redoc`.
- Service health endpoint at `/health`.
- Unit, integration, end-to-end, and deployment smoke tests with a 100% coverage gate
  (see [Testing](#testing)).

## Architecture

Shorty uses a hexagonal, ports-and-adapters structure. The domain model has no
persistence dependencies and emits domain events. A framework-independent application
interface handles commands, message dispatch, cache-aside reads, and transaction
retries. Plain Python ports define the storage interfaces, with SQLAlchemy and Redis as
their implementations. FastAPI and APScheduler call the application interface without
passing sessions, tables, or cache clients into route functions. Optimistic version
numbers prevent lost updates, and every retry uses a fresh Unit of Work.

The CQRS read path queries Postgres through a SQLAlchemy read-model adapter and returns
plain projections without building domain aggregates. JSON and HTML routes use the same
application interface. Cache entries keep the link's original expiry time after a miss.

- `alembic/` - database migrations.
- `src/shorty/` - application package.
  - `adapters/` - SQLAlchemy repository, Unit of Work, ORM/read model, Redis cache,
    and startup connection checks.
  - `domain/` - Link aggregate, domain events, and commands, with no framework imports.
  - `entrypoints/` - FastAPI and scheduled-cleanup entrypoints.
    - `routers/` - JSON API, FastAPI dependencies, service health, web UI, and redirect.
  - `service_layer/` - application interface, plain ports, handlers, and message bus.
    - `dto/` - framework-independent query projections and use-case results.
  - `templates/` - Jinja2 template for the single UI page.
  - `bootstrap.py` - composition root that wires adapters into the application.
  - `config.py` - environment-driven settings.
  - `exceptions.py` - framework-independent domain and application errors.
- `tests/` - test suites grouped by scope.
  - `e2e/` - full API and web UI flows against the real app over an in-process ASGI
    transport.
  - `integration/` - repository, Unit of Work, Redis cache, optimistic locking, and CQRS
    read-model tests using real Postgres and Redis services.
  - `smoke/` - network checks against the production image in isolated Docker Compose.
  - `unit/` - application, domain, handlers, and message bus tests using in-memory fakes.

## Running with Docker (recommended)

```bash
docker compose up --build
```

The Compose file includes development defaults for Postgres, Redis, the API, and the
standalone scheduler. The API waits for its dependencies and applies Alembic migrations.
Before accepting work, the API and scheduler verify their Postgres and Redis connections.
Each client has a separate configurable connection timeout. Startup checks make up to
three attempts with a short delay. Once the API is ready:

- Web UI: http://localhost:8020/
- Swagger UI: http://localhost:8020/docs
- ReDoc: http://localhost:8020/redoc

`Makefile` shortcuts: `make up`, `make down`, `make stop`, `make start`.

## Running locally without Docker

Requires [`uv`](https://docs.astral.sh/uv/) and running Postgres and Redis services.

```bash
docker compose up -d postgres redis
uv sync --locked
export DATABASE_URL=postgresql+asyncpg://admin:pswd3131@localhost:5432/shorty
export REDIS_URL=redis://localhost:16379/0
uv run alembic upgrade head
uv run uvicorn shorty.entrypoints.fastapi_app:app --reload
```

See `.env.example` for every configuration variable (link retention, cleanup interval
and batch size, session secret, default page size).

## Testing

```bash
make tests
```

This command runs the full suite in a disposable Compose project with its own Postgres,
Redis, network, and test image. Alembic migrates a clean database, and network smoke
tests check `/health` and `/` on the production image before the whole test stack and
its data are removed.

For fast feedback without external services, run the unit suite locally:

```bash
uv sync --locked
uv run pytest tests/unit
```

Unit tests use in-memory fakes for application ports and need no external services. In
the Compose stack, integration and e2e tests use the Postgres and Redis adapters and the
ASGI app against an Alembic-managed test schema. Individual tests clear data but never
create or drop application tables. Deployment smoke tests use `DEPLOYED_API_URL` to
check the production container over its network interface.

Run all configured static checks with:

```bash
make linters
```

GitHub Actions runs the linters and isolated test stack for pushes and pull requests
targeting `main` or `dev`, then uploads the coverage report to Codecov.
