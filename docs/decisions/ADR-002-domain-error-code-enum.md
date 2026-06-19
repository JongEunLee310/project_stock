# ADR-002: Domain Error Code Enum

## Status

Accepted

## Context

API clients need stable error keys for branching and localized display behavior. HTTP status codes alone only describe broad protocol classes, while the current response body exposes human messages without a durable machine-readable code.

## Decision

Adopt a shared `ErrorCode(str, Enum)` with domain-specific string values and return it in the common error envelope:

- `data: null`
- `message`: user-facing message
- `error.code`: stable enum value
- `error.fields`: validation details when applicable
- `meta: null`

`AppException` requires an explicit `error_code`, and framework validation/unhandled exceptions are normalized through global handlers.

## Alternatives

- Use only HTTP status codes.
- Use ad hoc string codes at each raise site.
- Return only human-readable error messages.

## Consequences

Frontend error handling can branch on stable codes without parsing Korean display messages. Backend raise sites become slightly more verbose, but missing mappings are caught during implementation because `AppException` requires `error_code`.

The code list must be maintained when new domain errors are added.

## Follow-up

Keep new API errors on the common envelope and add enum values when a new client-visible error condition is introduced.

## Related Documents

- `docs/designs/027-error-handling.md`
- Issue #47
