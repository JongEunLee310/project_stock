# Agent Skill Policy

## Default Rule

Installed skills are available as references only.
Agents must not activate autonomous behavior unless this file explicitly allows it.

## Allowed Skills

### Backend reference skills

`fastapi-patterns`, `python-testing`, `api-design`은 이 백엔드 프로젝트에서 구현·리뷰 시 참조로 사용한다. 자율 워크플로를 발동시키지 않으며, 판단 근거를 제시하는 참조 자료로만 활용한다.

- Claude Code — `.claude/settings.json`의 `skillOverrides`에서 `on`으로 활성화됨.
- Codex — `.codex/instructions.md`가 이 스킬들을 참조하도록 배선함.

`coding-standards`는 내용이 프론트엔드(React/TypeScript) 중심이라 이 프로젝트에서 비활성 유지한다.

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