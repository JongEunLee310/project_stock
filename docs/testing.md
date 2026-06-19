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

## Verification

Run lint, type checks, and tests before opening a pull request:

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```
