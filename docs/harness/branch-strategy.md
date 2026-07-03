# Branch Strategy

## Purpose

This project develops on a single long-lived branch (`main`) plus short-lived feature branches derived from it. This document explains the branch roles and the rules for deriving work branches.

## Branches

- `main` — the single source of truth. Always releasable. Protected: no direct pushes; all changes land through reviewed PRs.
- Feature branches — short-lived branches derived from the latest `main` for a single unit of work, merged back via PR and deleted after merge.

## Feature Branch Naming

Use a `type/topic` prefix matching the commit type of the work:

- `feat/<topic>` — new functionality
- `fix/<topic>` — bug fix
- `docs/<topic>` — documentation
- `refactor/<topic>`, `test/<topic>`, `chore/<topic>` — as appropriate

## Rules

- Always branch from the latest `main`. Before handing work off, confirm the feature branch is up to date with `main`; pull or rebase if it is behind.
- One feature branch per unit of work. Keep branches narrow and short-lived.
- Direct pushes to `main` are forbidden. Integrate only through PRs.
- When review feedback arrives, push fixes to the same feature branch (updating the existing PR) rather than opening a new PR. See `docs/harness/local-review-policy.md`.
- Stacked PR을 만들 때는 base 브랜치에 주의한다. base를 중간 feature 브랜치로 두면 그 PR이 중간 브랜치에만 머지되어 `main`에는 코드가 반영되지 않을 수 있다. 각 PR의 base를 `main`으로 두거나, 선행 PR이 `main`에 머지된 뒤 후속 PR의 base를 `main`으로 retarget한다.
- Delete feature branches after merge to avoid stale-branch drift.
