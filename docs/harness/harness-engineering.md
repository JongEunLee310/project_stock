# Harness Engineering

Harness Engineering is the practice of building a repeatable engineering system around AI agents so that their work is scoped, reviewable, verifiable, and documented.

## Instructions

Repository instructions define how agents behave, what they may change, and when they must stop. `AGENTS.md`, `CLAUDE.md`, and `.codex/instructions.md` are the primary instruction files.

## External Skills

External skills may extend agent capability. They should be installed manually, reviewed before use, and documented when they become part of the project workflow.

## Hooks

Hooks provide local checkpoints. In this template they are safe placeholders that print what they would check and exit successfully.

## ADR

Architecture Decision Records preserve decisions that affect future implementation, workflow, or governance.

## Failure Records

Failure records capture approaches that failed, why they failed, and when they may be retried.

## Knowledge Base

The knowledge base keeps workflow, glossary, and domain knowledge close to the project.

## Feedback Loop

The feedback loop connects issue planning, Codex implementation, PR creation, CI results, Claude local review, and human merge.

## Garbage Collection

Garbage collection keeps docs, prompts, hooks, and records from becoming stale or duplicated.

## Documentation Drift Guard

Directory README files, documentation impact checks, and review policies reduce drift between workflow reality and written guidance.

## GitHub Governance

GitHub issues, PR templates, CODEOWNERS, CI, and branch protection provide visible checkpoints for human approval and project-specific verification.
