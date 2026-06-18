# Agent Autonomy Levels

## Level 0: Advisory

Allowed:
- Read files
- Explain architecture
- Suggest changes
- Write plan

Not allowed:
- Edit files

## Level 1: Local Edit

Allowed:
- Edit source files
- Add tests
- Run local verification

Not allowed:
- Commit
- Push
- Create PR

## Level 2: PR Assistant

Allowed:
- Create branch
- Commit changes
- Create PR

Not allowed:
- Merge PR
- Deploy

## Level 3: CI Recovery

Allowed:
- Read CI failure logs
- Push fixes to existing PR

Not allowed:
- Change unrelated files
- Disable tests
- Bypass quality gates

## Level 4: Autonomous Operation

Currently disabled.