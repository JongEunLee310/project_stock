# Testing

## Run the Suite

Run all tests:

```bash
uv run pytest
```

Run a single test file:

```bash
uv run pytest tests/test_auth.py
```

Run tests matching a keyword:

```bash
uv run pytest -k auth
```

## Test Database

Tests use an in-memory SQLite database with SQLAlchemy `StaticPool`. The shared
fixtures in `tests/conftest.py` create and drop the schema around each test that
uses `client` or `db`, so the suite does not require an external database,
Redis, or worker process.

Auth and HTTP integration tests exercise the real JWT path by registering a
user, logging in, and sending `Authorization: Bearer <token>` headers. Existing
domain API tests may still override the current user through the shared
`set_current_user` helper when the test is focused on domain behavior rather
than authentication.

## Major API Regression Coverage

The suite includes focused API tests for watchlists, asset detail, research
summary, portfolio summary, and alert candidates. These tests cover successful
responses, pagination metadata where applicable, representative 404 paths, and
alert candidate read/confirm status transitions.

Common error envelope tests live in `tests/test_error_responses.py` and verify
401, 404, and 422 responses keep the `{data: null, error: {code}}` shape.

API contract snapshot tests live in `tests/test_api_contract.py` and pin the
required keys and types of the common envelope and the frontend-facing
responses. Treat a contract change as intentional and update both the test and
`docs/api/frontend-api-spec.md` together.

## Verification

Run lint, type checks, and tests before opening a pull request:

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```
