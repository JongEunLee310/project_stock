# ADR-009: Cloud Data Boundary / CloudSafe DTO

## Status

Proposed

## Context

The hybrid design routes several tasks to a cloud LLM at launch (ADR-008). Those
tasks operate over financial data the user reasonably expects to stay private:
portfolio holdings, account balances, individual trades, and identifiers. The
spec (§3) requires that no raw domain entity ever leaves the process toward a
cloud provider, while still letting cloud tasks reason over enough context to be
useful (e.g. concentration, sector mix, recent moves) without exposing absolute
positions or identity.

The question is *how* to enforce that boundary durably, given ADR-007 placed a
single choke point (`LLMGateway`) in front of every cloud call:

1. **What may cross the boundary**, expressed as a contract, not a per-call
   judgment call.
2. **How leakage is prevented** — by removing fields from a known object
   (redaction/denylist) or by building a separate object that only ever contains
   allowed fields (whitelist).
3. **A shared vocabulary of sensitivity** so routing and review can reason about
   risk consistently.

## Decision

Forbid raw entities at the cloud boundary and require a purpose-built CloudSafe
DTO built by whitelist.

1. **No raw entity to cloud, ever.** ORM/domain entities — `Portfolio`,
   `Account`, `Holding`, `Trade`, and equivalents — must not be serialized into a
   cloud `LLMRequest`. The gateway's privacy gate (`PrivacyGate`, #135) rejects
   any cloud-routed request whose payload is not a registered CloudSafe DTO.
2. **Whitelist, not redaction.** A CloudSafe DTO is a separate type that, by
   construction, contains only explicitly allowed, aggregated/anonymized fields
   (e.g. weights, ratios, buckets, derived signals — not absolute quantities,
   balances, account numbers, or user identity). We do **not** take an entity and
   strip fields (denylist), because a denylist fails open: a newly added entity
   field leaks by default. A whitelist fails closed: a new field is absent until
   someone deliberately adds it to the DTO.
3. **Sensitivity grades** as the shared vocabulary, used by routing (ADR-008) and
   the privacy gate:
   - `RAW` — original entity / PII / absolute positions. Never leaves to cloud.
   - `SEMI` — partially identifying or partially aggregated. Cloud only after
     transformation into a CloudSafe DTO.
   - `AGGREGATED` — anonymized aggregates/derived metrics. Cloud-eligible.
   - `PUBLIC` — already-public data (e.g. market news text). Cloud-eligible.
   Cloud routing is allowed only for `AGGREGATED` / `PUBLIC` payloads (or `SEMI`
   once converted). `RAW` is local-only.
4. **Enforcement at one choke point.** The boundary is checked inside the gateway
   before transport selection, so no call site can bypass it (consistent with
   ADR-008 fail-closed routing). Local-routed tasks are exempt from the DTO
   requirement, since data does not leave the process.
5. **Canonical, English `UPPER_SNAKE` enums** for the sensitivity grade, matching
   the repo's wire-enum convention (ADR-002 / C8).

## Alternatives

- **Redaction / denylist on entities.** Rejected: fails open. Every new entity
  field, relationship, or `__repr__` change risks silently shipping private data;
  the safe default must be "not sent."
- **Trust each caller to pass safe data.** Rejected: distributes a security
  decision across many call sites with no enforcement; one mistake is a leak.
- **Encrypt/tokenize raw data and send it.** Rejected: the cloud model cannot
  reason over ciphertext, and tokenization still ships structure/identity; it
  solves transport secrecy, not the "model sees private positions" problem.
- **Free-form dict payloads with runtime field checks.** Rejected: loses static
  typing and makes the whitelist implicit; a typed DTO makes the allowed surface
  reviewable in one place.

## Consequences

- Easier: the allowed cloud surface is a small set of reviewable DTO types;
  adding a field is a deliberate, diff-visible act; routing and review share one
  sensitivity vocabulary; the boundary has a single testable choke point.
- Harder / riskier: each cloud task needs a hand-built DTO and a mapping from its
  source entities — more upfront work than dumping an entity; aggregation logic
  must itself avoid re-identifying small/edge portfolios (callers' responsibility,
  noted for the briefing-feature design).
- No DB change. Introduces DTO types and the `PrivacyGate`; documentation-only at
  this ADR stage. This is a privacy-sensitive boundary — implementation (#135)
  warrants explicit human review before merge.

## Follow-up

- #133 — define the `Sensitivity` enum (and `TaskType`/`Risk`) used here.
- #135 — implement `PrivacyGate` and the first CloudSafe DTOs at the gateway
  boundary; add tests that a raw entity routed to cloud is rejected.
- Briefing-feature design (Phase 2) — define aggregation that avoids
  re-identification on small portfolios before any portfolio briefing ships.

## Related Documents

- `JongEunLee310/project_stock#132` (this ADR), Epic `#141`
- `docs/decisions/ADR-007-llm-provider-abstraction.md`
- `docs/decisions/ADR-008-llm-task-routing-policy.md`
- `docs/decisions/ADR-002-domain-error-code-enum.md` (wire-enum convention)
