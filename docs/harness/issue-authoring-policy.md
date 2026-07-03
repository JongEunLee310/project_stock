# Issue Authoring Policy

Large work is organized as a **strategy (Epic) issue** plus **sub-issues**, not as one flat issue. The Epic holds the overall strategy and tracks progress; each sub-issue is one narrow, implementable slice. The canonical example is the BE `[Data Pipeline]` Epic (#174) and its per-stage sub-issues.

## Issue Types

- **Epic (strategy) issue** — one per initiative. It owns the goal, the current-state gap, the ordered breakdown into stages, the whole-initiative completion criteria, and what is out of scope. Title carries a domain tag and an `[Epic]` marker, e.g. `[Data Pipeline][Epic] LLM 사전 데이터 수집·가공 파이프라인 v0.1`.
- **Sub-issue** — one per stage/slice under an Epic. It owns the scope of that stage only, what it deliberately excludes, and its own completion criteria. Title carries the same domain tag and a stage marker, e.g. `[Data Pipeline] 7단계 · LLM Gateway 분석 오케스트레이션 (BE)`.

Sub-issues are created just before a stage is started, not all upfront. The Epic lists the planned stages, and each is expanded into its own sub-issue when work on it begins.

## Epic (Strategy) Issue Content

An Epic issue uses these sections, in order:

- `## 개요` (Overview) — the higher-level goal and the reference document(s) the work is based on.
- `## 현재 상태` (Current state vs. the plan) — what is already implemented and what gap remains, so the Epic starts from reality rather than a blank slate.
- `## 구현 우선순위` (Ordered breakdown) — the stages as a checklist; each line links its sub-issue number and design doc once they exist.
- `## 완료 조건` (Completion criteria) — the whole-Epic done conditions as a checklist.
- `## 범위 밖` (Out of scope) — what this version explicitly excludes.
- `## 후속` (Follow-up) — how each stage is decomposed (design skeleton → Codex handoff → PR → local review), and the note that sub-issues are created just before each stage.

## Sub-Issue Content

A sub-issue uses these sections, in order:

- `## 배경` (Background) — the parent Epic and stage, the preceding stage/PR, and what already exists and is reused.
- `## 범위` (Scope) — the new entities this stage adds (files and their one-line responsibility).
- `## 비포함` (Out of scope) — what this stage deliberately does not touch (reused, or deferred to a later stage).
- `## 완료 조건` (Completion criteria) — this stage's done conditions plus the verification/CI expectation.
- A closing line referencing the design doc and handoff task for the stage.

Keep both levels skeleton-level and prose-lean, consistent with `design-record-policy.md`: name the entities and responsibilities, not implementation code.

## Metadata Is Required

Both issues and milestones must carry their metadata — do not leave them bare.

- **Every issue** — assignee (`@me`), milestone, labels (by area/type), and the GitHub Project. This is the issue-metadata rule already stated in `completion-commit-policy.md` Step 3. A sub-issue inherits its Epic's milestone; the Epic itself sits on the initiative's milestone.
- **Every milestone** — a title and a description that summarizes the initiative's scope. The `데이터 수집 파이프라인 — 백엔드` milestone (#5) is the example. A strategy initiative gets its own milestone, and its Epic and sub-issues all attach to it.

## Related

- `docs/knowledge/workflow.md` — step 1 (Issue Creation) follows this structure.
- `completion-commit-policy.md` — issue and PR metadata.
- `design-record-policy.md` — the skeleton-level design each stage references.
- `handoff-policy.md` — the Codex handoff each sub-issue is decomposed into.
