# ADR-008: LLM Task Routing Policy (task_type → provider, Cloud-First)

## Status

Proposed

## Context

The hybrid LLM design (Epic #141, spec §2) needs a rule for deciding which model
backend serves a given piece of work. The same gateway must serve heterogeneous
tasks — portfolio briefings, dashboard briefings, watchlist observation notes,
news/disclosure summaries, tagging/sentiment, and a future agent — each with a
different privacy profile and a different long-term home (cloud vs. local).

Two facts constrain the policy:

1. **Local is stub-only at launch.** The initial release is cloud-first; the
   local backend exists as a `LocalLLMProvider` stub (#133) with no real
   inference. The routing layer must already model "this task's future primary
   is local" without that backend being live, so migration later is a config
   change, not a code change.
2. **Routing is a durable policy, not call-site logic.** If each service picked
   its own backend, the cloud→local migration would mean editing every call
   site, and the privacy boundary (ADR-009) could be bypassed per call.

ADR-007 placed routing in `LLMGateway` / `LLMRouter`. This ADR fixes *how* that
router decides.

## Decision

Route by **task type**, driven by configuration, with an explicit cloud-first
default and a recorded local target.

1. **`TaskType` is the routing key.** A canonical `TaskType` enum (defined in
   #133, English `UPPER_SNAKE`) identifies each kind of work. The router maps
   `task_type → provider`; callers pass a `task_type` on the `LLMRequest` and
   never name a backend directly.
2. **Config-driven mapping, not hard-coded branches.** The mapping lives in
   configuration, not in `if task_type == ...` chains. A new `LLM_PROVIDER`
   setting (`Literal["cloud", "local", "mock"]`, default `cloud`) selects the
   transport backend the factory builds, mirroring the existing
   `MARKET_PROVIDER` / `NEWS_PROVIDER` pattern. The per-task routing table is
   expressed as data the router reads, so retargeting a task is a config edit.
3. **Cloud-first with `future_primary`.** Each task carries two notions: its
   **current** provider (cloud or template at launch) and its **future primary**
   (where it should run once local matures). At launch every routed task
   resolves to cloud; `future_primary = local` is recorded for the migration-1
   candidates (watchlist notes first, then dashboard briefing, news summaries,
   tagging/sentiment) so the target is documented, not folklore.
4. **Initial routing table** (from Epic #141, authoritative there):

   | TaskType (intent)            | Launch          | Future primary            |
   | ---------------------------- | --------------- | ------------------------- |
   | Portfolio briefing           | Cloud           | Cloud (CloudSafe DTO)     |
   | Dashboard briefing           | Cloud           | Local + Cloud escalation  |
   | Watchlist observation note   | Cloud/Template  | Local (migration #1)      |
   | News / disclosure summary    | Cloud           | Local + validation        |
   | Tag / sentiment / dedup      | Local (goal)    | Local                     |
   | Agent (future)               | Cloud           | Cloud + local microtasks  |

5. **Unknown task types fail closed.** A `task_type` with no mapping is an error,
   not a silent default to cloud — a missing mapping must surface, because it
   may carry sensitive data with no privacy decision attached (ADR-009).

## Alternatives

- **Route per call site (caller picks the backend).** Rejected: scatters policy,
  makes cloud→local migration an N-file edit, and lets call sites bypass the
  privacy gate.
- **Hard-coded `if task_type` routing.** Rejected: every retarget is a code
  change and a deploy; config-driven data keeps migration to a setting flip.
- **Capability/cost-based dynamic routing now.** Rejected as premature: there is
  no live local backend or cost signal yet; this is Phase 2 escalation territory
  (#140), not launch.
- **Default unknown task types to cloud.** Rejected: fails open on the privacy
  boundary; an unmapped task could ship raw data to a cloud provider unnoticed.

## Consequences

- Easier: migrating a task from cloud to local is a config change once the local
  backend is real; the routing table doubles as living documentation of intent;
  the privacy gate has a single choke point to guard.
- Harder / riskier: the routing table and `future_primary` metadata must be kept
  in sync with Epic #141; fail-closed routing means adding a new task requires a
  deliberate mapping entry (intended friction).
- No DB change. Adds one setting (`LLM_PROVIDER`) and a routing config surface;
  documentation-only at this ADR stage.

## Follow-up

- #133 — define `TaskType` (and `Sensitivity`/`Risk`) enums consumed here.
- #134 — implement `LLMRouter`, the `LLM_PROVIDER` setting, factory wiring, and
  clean up `app/worker/jobs/analysis.py` constructing `MockLLMClient` directly so
  it goes through the factory/gateway.
- Phase 2 #140 — risk-based escalation that can override the static table at
  runtime (e.g. local primary → cloud on high-risk inputs).

## Related Documents

- `JongEunLee310/project_stock#132` (this ADR), Epic `#141`
- `docs/decisions/ADR-007-llm-provider-abstraction.md`
- `docs/decisions/ADR-009-cloud-data-boundary-cloudsafe-dto.md`
- `app/adapters/factory.py` (provider-selection pattern)
