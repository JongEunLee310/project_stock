# Codex Handoff Task

## Source Issue

Link or identifier: (placeholder — create issue `feat: add version endpoint` on the `spring-boot` branch before opening this handoff)

## Task Summary

Add a `GET /version` endpoint to the Spring Boot starter app.

## Goal

`GET /version` returns `{"version": "0.1.0"}` with HTTP 200, mirroring the existing `/health` endpoint's style and test coverage.

## Background

`src/main/java/com/example/template/HealthController.java` currently exposes only `GET /health` via `@RestController`. `build.gradle` declares `version = '0.1.0'`. The endpoint should return this same value.

## Implementation Scope

- Add a new controller (e.g. `VersionController.java`) or extend `HealthController.java` with a `/version` mapping, following the existing controller's structure.
- Add a corresponding MockMvc test in `src/test/java/com/example/template/`, following the structure of `HealthControllerTests.java`.

## Out of Scope

- Do not change `/health` behavior.
- Do not wire the version dynamically from `build.gradle`/`BuildProperties` unless trivial; a literal `"0.1.0"` constant is acceptable for this starter.
- Do not change `build.gradle`, `settings.gradle`, or CI configuration.

## Protected Files

None required. Do not modify `.claude/`, `.codex/`, `.github/`.

## Requirements

- `GET /version` returns exactly `{"version": "0.1.0"}`.
- Controller style (package, annotations, return type `Map<String, String>`) matches `HealthController.java`.

## Test Requirements

- A passing MockMvc test asserting status 200 and `$.version` equals `"0.1.0"` for `GET /version`.

## Verification Commands

```bash
chmod +x ./gradlew
./gradlew build
```

## Documentation Impact

Update the Spring Boot branch README "Spring Boot Starter" section to mention `GET /version` alongside `GET /health`.

## ADR Need

No. Additive, non-architectural change.

## Failure Record Need

No.

## Risk Level

Low. Additive endpoint, no existing behavior changed, fully covered by `./gradlew build`.

## Expected Output

A PR adding the endpoint, test, and README mention, with `./gradlew build` passing in CI, and a Claude Code local review comment.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
