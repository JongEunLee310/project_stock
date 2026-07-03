# Handoff Policy

Claude Code hands implementation work to Codex using `.codex/task-template.md`.

When the change introduces a new domain, table, external dependency, or architectural decision, a design record must exist before handoff, per `design-record-policy.md`. Reference it from the handoff task.

## Output Location

Completed handoffs are written to `.codex/tasks/task-<NNN>-<slug>.md`, using `.codex/task-template.md` as the section template. `<NNN>` is a zero-padded sequence number and `<slug>` is a short kebab-case summary. One file per handoff.

## Required Fields

- Source Issue
- Task Summary
- Goal
- Background
- Implementation Scope
- Out of Scope
- Protected Files
- Requirements
- Test Requirements
- Verification Commands
- Documentation Impact
- ADR Need
- Failure Record Need
- Risk Level
- Expected Output
- Rules

## Stop Conditions

Claude Code should stop instead of handing off when:

- The issue goal is unclear.
- Required decisions are architectural and unresolved.
- A design record is required per `design-record-policy.md` but has not been written.
- Protected file changes are needed but not approved.
- Verification expectations are missing.
- Risk is high and human approval is needed.
- The requested change conflicts with existing policy.

## Handoff Quality

A good handoff is narrow, testable, and explicit about what Codex must not change.

## Codex Execution

Claude Code may invoke `codex exec` automatically as the implementation step, **under the default sandbox only** (`read-only` / `workspace-write`), passing the handoff document as the brief (per `docs/decisions/ADR-005-allow-claude-code-to-invoke-codex-exec.md`). Automation does not remove the handoff: the written scope / out-of-scope / verification contract above is still produced and passed to Codex as the prompt. The current Codex CLI runs `codex exec` correctly, so no specific pinned version is required (see `.codex/CODEX_SETUP_NOTES.md`).

If an automated run appears to make no progress, confirm it is **actually hung** — no new output or file activity within a reasonable window, not merely a long-running step — before retrying. Cap retries at a small bounded number; if the run stays hung after those attempts, fall back to manual execution (ADR-004) instead of looping.

`--dangerously-bypass-approvals-and-sandbox` and `-s danger-full-access` must **never** be used in an automated Claude Code workflow. If Codex's default sandbox cannot run a task, stop and ask the human per `docs/harness/human-gate-policy.md` instead of escalating Codex's privileges — fall back to manual execution (ADR-004), never to elevated access. Mandatory human gate conditions still apply **before** the automated implementation step runs.

## PR Grouping

핸드오프 문서와 설계 문서는 그 자체로 단독 PR을 만들지 않는다. Codex가 해당 스코프를 구현한 뒤, 설계·핸드오프·구현을 하나의 PR로 함께 올린다. 그래야 리뷰어가 한 PR에서 근거와 구현을 같이 확인할 수 있고, 문서만 담긴 빈 PR이 남지 않는다. 핸드오프는 별도 PR을 기다리지 않고 위 Codex Execution 절차에 따라 바로 위임할 수 있다.
