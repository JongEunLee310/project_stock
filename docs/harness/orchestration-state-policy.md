# Orchestration State Policy

This document defines the workflow states from issue creation to merge.

## States

### Draft

The issue is created. Claude Code has not reviewed it yet.

Transition to: Review

### Review

Claude Code is analyzing the issue and assessing risk.

Transition to: Blocked (gate condition applies) or Ready (Low/Medium risk)

### Blocked

A human gate condition applies. Work cannot proceed until the human approves.

Transition to: Ready (after approval) or Cancelled (if rejected/deferred)

### Ready

Claude Code has created a Codex handoff task. Implementation can begin.

Transition to: In Progress

### In Progress

Codex is implementing.

Transition to: PR Open

### PR Open

A PR is open. CI runs. Claude Code runs a local review.

Transition to: PR Approved (CI passes, human approves) or PR Blocked (Claude review finds blocking issues)

### PR Blocked

Claude Code found blocking issues. Codex must respond.

Transition to: PR Open (after Codex addresses issues)

### PR Approved

The human has approved the PR.

Transition to: Merged

### Merged

Merged. Documentation impact assessed. ADRs, failure records, or knowledge updates created if needed.

### Cancelled

Work was rejected, deferred, or abandoned. Record reason in a failure record if worth remembering.

## Related

- `task-classification-policy.md`
- `human-gate-policy.md`
- `handoff-policy.md`
