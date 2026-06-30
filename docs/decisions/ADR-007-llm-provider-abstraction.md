# ADR-007: LLM Provider Abstraction (Transport vs. Gateway, Sync Convention)

## Status

Proposed

## Context

The backend is moving toward a real AI investment assistant built on a
local/cloud hybrid LLM design (Epic #141). Today `app/adapters/llm/` already
provides a transport layer: `LLMClient` (ABC) with `OpenAIClient` and
`MockLLMClient` implementations, structured output via `complete_json`, prompt
separation under `prompts/`, and constructor-based DI. Provider selection for
the other adapters follows a settled pattern — `adapters/factory.py`
`get_X_provider()` switching on a `settings.X_PROVIDER` value.

The hybrid spec (§1) introduces orchestration concerns that do not belong in a
transport client: routing a task to a provider, enforcing a data boundary
before a cloud call, and (later) caching, fallback, and output validation. Two
naming/convention questions must be fixed before any of #133–#136 is built:

1. **Where orchestration lives.** The spec sketches an `LLMProvider` interface
   that mixes transport with routing/policy. This collides with the repo's
   existing meaning of `LLMClient` (transport) and `XxxProvider` (factory-level
   external adapter), and would overload one object with two responsibilities.
2. **Sync vs. async.** The spec proposes `async def generate(...)`. The entire
   repository — services, repositories, routers, workers — is synchronous.
   Introducing async for one subsystem would force `async`/`await` coloring
   across call sites or bridge code at every boundary.

## Decision

Keep the transport layer as-is and add a distinct orchestration layer above it.

1. **Two layers, two responsibilities.**
   - **Transport** stays `LLMClient` (ABC) + concrete clients
     (`OpenAIClient`, `MockLLMClient`, and a future local client). It only knows
     how to call one model endpoint (`complete` / `complete_json`).
   - **Orchestration** is a new `LLMGateway` — the single entry point that
     callers (services, workers) use. It owns routing, the privacy boundary,
     and (Phase 2) cache/fallback/validation, delegating the actual model call
     to an `LLMClient`.
2. **Naming.** Use `LLMGateway` for the orchestrator, not the spec's
   `LLMProvider`. This preserves the repo convention: `LLMClient` = transport,
   `XxxProvider` = factory-level external adapter. The per-target stub that
   represents "a local model backend" is `LocalLLMProvider` (transport-side, an
   `LLMClient`), introduced in #133.
3. **Sync is retained.** No `async def` is introduced. `LLMGateway` and all
   `LLMClient` methods stay synchronous, consistent with the rest of the repo.
   The spec's `async def generate` is rejected. Concurrency, if ever needed, is
   handled at the worker/job level, not by coloring the LLM API.
4. **DI and selection unchanged.** `LLMGateway` is assembled via the existing
   factory pattern; transport selection moves behind a new `LLM_PROVIDER`
   setting (ADR-008). Construction is explicit constructor injection, matching
   the current adapters.

## Alternatives

- **Single `LLMProvider` mixing transport + policy (spec as written).**
  Rejected: overloads one object with two reasons to change, collides with the
  repo's `LLMClient`/`XxxProvider` vocabulary, and makes the privacy boundary
  harder to test in isolation.
- **Adopt async (`async def generate`).** Rejected: the repo is uniformly sync;
  async would propagate `await` across services/workers or require bridging at
  every call site, for no concurrency benefit at current scale.
- **Put routing inside `LLMClient` implementations.** Rejected: a transport
  client would then need to know about other clients, inverting the dependency
  and duplicating routing logic per backend.

## Consequences

- Easier: callers depend on one stable `LLMGateway` surface; transport backends
  (cloud → local) can be swapped without touching call sites; the privacy
  boundary and routing become unit-testable separately from any real model.
- Harder / riskier: one extra layer to assemble and document; contributors must
  learn the `LLMClient` (transport) vs. `LLMGateway` (orchestration) split and
  resist re-adding async.
- No new runtime dependency or DB change; this ADR is documentation-only and
  unblocks the typed-boundary work in #133.

## Follow-up

- #133 — TaskType/Sensitivity/Risk enums, `LLMRequest`/`LLMResponse`, and the
  `LocalLLMProvider` stub on the transport side.
- #134 — `LLMRouter` + factory and `LLM_PROVIDER` selection (ADR-008).
- #136 — `LLMGateway` assembly and Phase 1 tests.
- ADR-NNN (Phase 2, #137) — fallback/escalation, cache, and output validation
  inside the gateway, deferred until a briefing consumer exists.

## Related Documents

- `JongEunLee310/project_stock#132` (this ADR), Epic `#141`
- `docs/designs/013-llm-adapter.md` (existing transport layer)
- `docs/decisions/ADR-008-llm-task-routing-policy.md`
- `docs/decisions/ADR-009-cloud-data-boundary-cloudsafe-dto.md`
