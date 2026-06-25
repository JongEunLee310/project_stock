# Agent Role Policy

## Claude Code

Claude Code is the orchestrator and reviewer. It analyzes issues, plans work, reviews design, creates Codex handoff tasks, triggers Codex implementation by invoking `codex exec` under the default sandbox (per `docs/decisions/ADR-005-allow-claude-code-to-invoke-codex-exec.md`), performs local PR review, and assesses documentation impact. Triggering implementation does not make Claude Code the implementer — Codex implements in its own session; Claude Code never escalates Codex's sandbox.

## Codex

Codex is the implementer. It implements from handoff tasks, updates tests, runs verification, fixes CI failures, and addresses blocking Claude Code review feedback.

## Standard Orchestration Combination

The default going-forward division of labor is **Opus + Sonnet/VFF + Codex**:

- **Opus (Claude Code)** — orchestration, external execution (codex trigger, commit, push, PR), and final verification.
- **Sonnet/VFF** — design and review, run as the `value-for-fable:itsvff` subagent at Sonnet rates.
- **Codex** — implementation.

Running design and review at Sonnet rates measured ~39% lower Anthropic billing than an all-Opus track on the same controlled work, with VFF review accuracy matching Opus on the validated round (see `docs/experiments/orchestrator-comparison-round2-vff-sonnet.md`). The VFF subagent cannot perform external or irreversible actions — it rejects relayed approvals — so codex triggering, commits, push, and PR creation stay with Opus. Keep Opus final verification as a low-cost safety net, and watch the trade-off where more detailed handoffs raise Codex implementation tokens.

## CI

CI is the feedback sensor. It runs project-specific verification commands in the PR workflow and reports failures that Codex can fix.

## Human

Humans are the final owners. They approve risky decisions, approve PRs, and merge.

## Boundary Rule

Agents should not silently swap responsibilities. If a task requires a different role, document the reason and ask for human approval when risk is meaningful.
