# Codex Handoff Task

## Source Issue

Link or identifier: (placeholder — create issue `feat: add version endpoint` on the `fastapi` branch before opening this handoff)

## Task Summary

Add a `GET /version` endpoint to the FastAPI starter app.

## Goal

`GET /version` returns `{"version": "0.1.0"}` with HTTP 200, mirroring the existing `/health` endpoint's style and test coverage.

## Background

`app/main.py` currently exposes only `GET /health`. `pyproject.toml` declares the project version as `0.1.0` (`[project] version = "0.1.0"`). The version returned by the endpoint should match this value.

## Implementation Scope

- `app/main.py` — add the `/version` route.
- `tests/test_health.py` or a new `tests/test_version.py` — add a test asserting the response.

## Out of Scope

- Do not change `/health` behavior.
- Do not add a dependency to read the version dynamically from `pyproject.toml` unless trivial; a literal `"0.1.0"` constant is acceptable for this starter.
- Do not change `pyproject.toml`, CI, or lint/type configuration.

## Protected Files

None required. Do not modify `.claude/`, `.codex/`, `.github/`.

## Requirements

- `GET /version` returns exactly `{"version": "0.1.0"}`.
- Return type is annotated consistently with the existing `health_check` function (`dict[str, str]`).

## Test Requirements

- A passing test asserting status code 200 and the exact JSON body for `GET /version`.

## Verification Commands

```bash
uv sync
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

Update the FastAPI branch README "FastAPI Starter" section to mention `GET /version` alongside `GET /health`.

## ADR Need

No. Additive, non-architectural change.

## Failure Record Need

No.

## Risk Level

Low. Additive endpoint, no existing behavior changed, fully covered by existing CI checks.

## Expected Output

A PR adding the endpoint, test, and README mention, with ruff, mypy, and pytest passing in CI, and a Claude Code local review comment.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
