# Hook Policy

Hooks are local workflow checkpoints.

## Template Hooks

- `.claude/hooks/pre-implementation-check.sh`
- `.claude/hooks/pre-pr-check.sh`
- `.claude/hooks/protected-files-check.sh`
- `.claude/hooks/docs-consistency-check.sh`

## Rules

- Hooks must be safe by default.
- Hooks must not perform destructive behavior.
- Hooks should explain what they check.
- Project-specific templates may replace placeholders with real checks.

## Exclusions

The common template must not implement framework-specific lint, typecheck, build, structure drift, or code drift rules.
