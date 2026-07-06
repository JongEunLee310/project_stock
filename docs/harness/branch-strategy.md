# Branch Strategy

## Purpose

This project develops on two long-lived branches — `dev` for integration and `main` for release — plus short-lived feature branches. This document explains the branch roles and the rules for deriving work branches.

## Branches

- `main` — the release/deploy branch. Always releasable. Every merge to `main` triggers the Docker image build and push (`.github/workflows/backend-image.yml`), so `main` is updated only by promoting `dev` through a dedicated release PR. Protected: no direct pushes.
- `dev` — the integration branch. Feature branches merge here first through reviewed PRs. Merges to `dev` do **not** build an image. Protected: no direct pushes.
- Feature branches — short-lived branches derived from the latest `dev` for a single unit of work, merged back into `dev` via PR and deleted after merge.

## Why two branches

Merging to `main` builds and pushes a new Docker image. Routing routine work — including docs-only changes — through `dev` first avoids producing an image for every merge. An image is built only when `dev` is deliberately promoted to `main`, which represents an intended release.

## Feature Branch Naming

Use a `type/topic` prefix matching the commit type of the work:

- `feat/<topic>` — new functionality
- `fix/<topic>` — bug fix
- `docs/<topic>` — documentation
- `refactor/<topic>`, `test/<topic>`, `chore/<topic>` — as appropriate

## Rules

- Always branch from the latest `dev`. Before handing work off, confirm the feature branch is up to date with `dev`; pull or rebase if it is behind.
- Feature PRs target `dev` as their base, never `main`.
- Promote `dev` to `main` through a dedicated release PR (base `main`) when a release/deploy is intended. That merge is what builds and pushes the image.
- One feature branch per unit of work. Keep branches narrow and short-lived.
- Direct pushes to `dev` and `main` are forbidden. Integrate only through PRs.
- When review feedback arrives, push fixes to the same feature branch (updating the existing PR) rather than opening a new PR. See `docs/harness/local-review-policy.md`.
- Be careful with the base branch when stacking PRs. If a PR's base is an intermediate feature branch, it merges into that branch and its code may never reach `dev`. Set each PR's base to `dev`, or retarget a follow-up PR's base to `dev` once the preceding PR has merged.
- Delete feature branches after merge to avoid stale-branch drift.

## CI and image build

- CI (`.github/workflows/ci.yml`) runs on every PR via the `pull_request` trigger, so PRs into both `dev` and `main` are gated by lint/typecheck/test.
- The image build (`.github/workflows/backend-image.yml`) runs only after CI succeeds on `main`, i.e. after a `dev` → `main` promotion.
