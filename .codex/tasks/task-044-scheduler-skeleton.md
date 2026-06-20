# Codex Handoff Task

## Source Issue

Issue #64 (제목 Issue 44): `[BE] 스케줄러/잡 실행 구조 초안 추가`

## Task Summary

뉴스·공시·시세 데이터를 주기적으로 수집할 scheduler 구조의 초안을 만든다. scheduler module, job interface, mock job, 수동 실행 경로, 실행 결과 로그 구조를 도입한다. 실제 주기 실행·외부 API 연동은 후속 버전.

## Goal

- 향후 데이터 수집 자동화를 붙일 구조가 마련된다.
- 외부 API 연동 없이 mock job 실행 흐름을 확인할 수 있다.
- scheduler 구조의 책임 범위가 문서화된다.

## Background

- **설계문서 우선**: `docs/designs/044-scheduler-skeleton.md`를 먼저 읽고 따른다.
- **ADR 확정**: `docs/decisions/ADR-003-scheduler-approach.md`는 **Accepted**다. **rq-scheduler 채택** — 기존 RQ/Redis/worker 위에 시간 트리거만 더한다. 본 초안 단계는 실제 주기 등록을 mock으로 두고 인터페이스·구조만 확정한다.
- 기존 인프라: RQ worker(`app/worker/*`), `job_runs` 도메인(start/succeed/fail), 수동 enqueue endpoint(`POST /jobs/*`).
- 로깅은 #62(설계 042) 구조를 활용한다.

## Implementation Scope

- scheduler module(초안): 등록 job을 주기/수동으로 실행하는 진입점. 실제 주기 트리거는 mock.
- Job interface: `name` + `run()` 수준의 최소 인터페이스. 기존 함수형 job을 감싸는 수준.
- mock job: 외부 연동 없이 흐름 확인. `job_runs`에 기록.
- 수동 실행 경로(endpoint 또는 CLI)로 특정 job 1회 실행.
- 실행 결과 로그 구조(`job_runs` + 로깅).

## Out of Scope

- 실제 주기 등록·운영 적용(후속 버전).
- 실제 외부 provider 연동(공시·시세 수집).
- 기존 worker/job_runs 인프라 대체.

## Protected Files

변경하지 않는다: `AGENTS.md`, `CLAUDE.md`, `.github/workflows/ci.yml`, `docs/harness/`, `docs/decisions/`. ADR-003은 이미 Accepted로 확정됐으므로 추가 변경 불필요.

## Requirements

- job interface와 scheduler 구조가 후속 job을 붙일 수 있게 마련된다.
- mock job이 수동 실행으로 동작하고 `job_runs`에 기록된다.
- scheduler 책임 범위가 설계 044 + ADR-003에 문서화된다.

## Test Requirements

- mock job 수동 실행 → `job_runs` 기록 테스트.
- job interface 동작 단위 테스트.
- 전체 `uv run pytest` 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/designs/044-scheduler-skeleton.md`, `docs/decisions/ADR-003-scheduler-approach.md`.

## ADR Need

해소됨 — scheduler 기술 선택은 ADR-003(Accepted, rq-scheduler)으로 확정. 추가 ADR 불필요.

## Failure Record Need

없음(초안 단계).

## Risk Level

Low — 초안 구조. 실제 주기 실행/외부 연동 없음. priority:low.

## Expected Output

- scheduler/job interface/mock job/수동 실행/결과 로그 초안 + 테스트.
- lint/typecheck/pytest 통과. PR body에 `Closes #64`.

## Rules

- 스코프 유지(초안만). 검증 약화 금지.
- 기존 worker/job_runs 인프라 대체 금지.
- rq-scheduler(ADR-003) 전제 위에서 구현 — 다른 스케줄러 기술로 임의 변경 금지.
- 가정과 검증 결과 보고.
