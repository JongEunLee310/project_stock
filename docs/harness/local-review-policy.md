# Local Review Policy

Claude Code review happens after PR creation.

The review is local by default, not a GitHub Actions job. This template does not configure Claude GitHub Action.

## Review Scope

Claude Code should review:

- PR diff.
- Related issue.
- Codex handoff task.
- CI result.
- Protected file changes.
- Documentation impact.
- ADR need.
- Failure Record need.
- Domain knowledge impact.

## Review Records

The review is written to a durable, versioned file:

`docs/reviews/pr-<number>.md`

This file is committed, not a throwaway under `tmp/`. The PR conversation remains the place to publish the review for discussion, and reusable findings should still be promoted into docs, ADRs, failure records, or the knowledge base.

## Review Format

Every review record uses the same section order and headers:

1. `## Review Summary`
2. `## Blocking`
3. `## Suggestions`
4. `## Questions`
5. `## CI Result`
6. `## Documentation Impact`
7. `## Final Recommendation`

Use the fixed headers even when a section is empty (state "None").

## Handling Review Feedback

When the posted review comment contains a **Blocking** finding or any change the review says must be made, Claude Code does **not** stop and wait for the human. It drives the fix loop:

1. **Hand the required changes to Codex.** Claude Code does not edit implementation code itself (per `agent-role-policy.md`); it writes the review findings into a Codex handoff (or `.codex/prompts/`) stating what must change and why, and triggers Codex.
2. **Codex pushes to the same feature branch.** It does **not** open a new PR — the push updates the existing PR. Do not fragment a single review cycle across multiple PRs.
3. **Claude Code re-reviews the updated PR** and posts the follow-up review as a **new comment on the same PR** (`docs/reviews/pr-<number>.md` updated, then `gh pr comment`).
4. **Repeat** from step 1 while the latest review still has a Blocking finding or required change.
5. **Then wait.** Once the review converges to no blocking change, Claude Code stops and waits for the human to approve and merge.

This loop is bounded by the review converging. If the same finding recurs without progress after a few cycles, stop the loop and escalate to the human instead of continuing — do not run an unbounded fix loop.

A review with no Blocking finding and no required change goes straight to the wait step; there is nothing to hand to Codex.

## Approval

Claude Code must not approve PRs automatically. Human reviewers own final approval.
