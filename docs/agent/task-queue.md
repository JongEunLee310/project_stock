# Agent Task Queue

## TASK-001: Add health check endpoint

Status: approved
Allowed loop: sequential
Allowed skills:
- continuous-agent-loop: sequential only
- autonomous-agent-harness: shared-task-notes only

Scope:
- Add `/health`
- Add controller test
- Update API documentation

Forbidden:
- Do not change auth logic
- Do not change deployment files
- Do not add new dependencies

Exit Criteria:
- Test passes
- Lint passes
- Build passes
- No unrelated file changes