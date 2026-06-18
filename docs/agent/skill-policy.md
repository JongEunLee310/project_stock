# Agent Skill Policy

## Default Rule

Installed skills are available as references only.
Agents must not activate autonomous behavior unless this file explicitly allows it.

## Allowed Skills

### continuous-agent-loop

Allowed modes:
- sequential
- quality-gate
- failure-recovery for local test/lint/build errors only

Not allowed:
- continuous-pr without explicit human approval
- rfc-dag without explicit human approval
- infinite loop
- automatic merge
- automatic deployment
- production environment changes

### autonomous-agent-harness

Allowed features:
- task queue reading
- shared task notes
- local memory summary
- dry-run planning

Not allowed:
- scheduled execution
- background operation
- external account operation
- credential access
- production infrastructure mutation