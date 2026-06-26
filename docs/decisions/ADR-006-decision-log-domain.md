# ADR-006: Decision-Log Journaling Domain (Snapshots, Lifecycle, Canonical Enums)

## Status

Proposed

## Context

The frontend has an investment decision journal screen (`/decision-log`) with no
backend counterpart; entries live only in client-local mock data. The API
contract-alignment work (`docs/api/contract-alignment.md`, gap **G10**, derived
item **N1**, decision **Q7**) confirmed that this journal must be persisted by a
new backend domain so decisions survive across sessions and devices.

A persistence domain for human/AI investment decisions raises a few durable
choices that affect future work:

1. **What to capture at decision time.** A decision is only meaningful with the
   context it was made in (valuation, news, portfolio state, AI analysis). That
   context is heterogeneous and will evolve faster than a relational schema
   should.
2. **How a decision evolves.** A logged decision is later reviewed and closed —
   it is not a static record. This needs a lifecycle.
3. **Enum representation across the FE/BE boundary**, consistent with the rest of
   the contract (`C8`).

## Decision

Add a new `decision_logs` domain following the existing domain pattern
(`model` / `repository` / `service` / `schema` + router), with:

1. **Context snapshots as nullable free-form JSON.** `valuation_snapshot`,
   `news_snapshot`, `portfolio_snapshot`, `ai_analysis_snapshot`, and
   `cognitive_risks` are stored as JSON (objects / string array) with **no fixed
   sub-schema** at MVP. The backend does not validate or interpret their shape.
2. **Explicit lifecycle** `decision_status`: `OPEN → REVIEWED → CLOSED`, paired
   with `decided_at` / `reviewed_at` / `closed_at`. `PATCH` drives transitions;
   the corresponding timestamp is stamped on first entry into a state. MVP does
   **not** enforce forward-only ordering (see Follow-up).
3. **Canonical enums in English `UPPER_SNAKE`** on the wire (`decision_type`,
   `decision_status`, `created_by`), localized to Korean in the FE presentation
   layer — same rule as every other contract enum (`C8`).
4. **Ownership** by `user_id`; all endpoints require auth and only expose the
   caller's own rows (`*_FORBIDDEN` on cross-user access).

The frozen field/enum/endpoint contract lives in
`docs/designs/decision-log-domain.md` (§ 계약 확정). A new Alembic migration
creates the table.

## Alternatives

- **Typed columns for every snapshot field.** Rejected for MVP: the captured
  context is heterogeneous and unstable; pinning it to columns forces a migration
  on every shape change. Free-form JSON defers that cost; columns can be promoted
  later if a field proves stable and queryable.
- **No snapshots (store only the decision text).** Rejected: loses the rationale
  context that makes a decision journal worth keeping, and a later add-back is a
  schema migration anyway. The columns are zero-logic and nullable, so the cost
  now is negligible.
- **No lifecycle (immutable log).** Rejected: the FE already models review/outcome
  state; `OPEN→REVIEWED→CLOSED` is the minimum that supports it.
- **Korean enum values on the wire.** Rejected: inconsistent with `C8`; mixing
  display language into the contract leaks presentation into the API.

## Consequences

- Easier: the journal becomes durable and multi-device; snapshot shape can evolve
  without migrations; FE adapts via its enum-label mapping (already the pattern).
- Harder / riskier: free-form JSON is not queryable or schema-guaranteed — callers
  must tolerate missing/loose snapshot fields. Lifecycle without forward-only
  enforcement allows out-of-order status edits at MVP.
- New DB table (`decision_logs`) ⇒ this work is a **human-gate** item
  (`human-gate-policy.md`: DB schema) and requires human approval before the
  automated Codex implementation step runs (ADR-005 #6).

## Follow-up

- Enforce forward-only lifecycle transitions (reject `CLOSED → OPEN` etc.) with a
  dedicated error code if the journal gains edit UI.
- Promote any snapshot field that becomes stable + queryable to a typed column.
- FE adapter (`ticker↔symbol`, `reason↔rationale`, `decision_status↔outcome`,
  `cognitive_risks↔cognitiveRisks`) is FE-track scope (FE#48 follow-up), not this ADR.

## Related Documents

- `docs/designs/decision-log-domain.md` (작업지도 + 계약 확정)
- `docs/api/contract-alignment.md` (G10, N1, Q7)
- `JongEunLee310/project_stock#102`
- `docs/decisions/ADR-002-domain-error-code-enum.md`
- `docs/decisions/ADR-005-allow-claude-code-to-invoke-codex-exec.md`
