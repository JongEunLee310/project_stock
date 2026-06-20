# 044 Scheduler Skeleton

## Scope

뉴스·공시·시세 데이터를 주기적으로 수집할 수 있도록 scheduler 구조의 초안을 만든다. scheduler module, job interface, mock job, 수동 실행 경로, 실행 결과 로그 구조를 정의한다. 실제 주기 실행·외부 API 연동·운영 적용은 후속 버전으로 분리한다.

## Current State

- RQ 기반 worker 존재: `app/worker/{connection,entrypoint}.py`, jobs `collect_news_job`/`analyze_watchlist_job`(plain function).
- `job_runs` 도메인으로 실행 이력 기록(start/succeed/fail).
- 수동 enqueue endpoint 존재: `POST /jobs/news`, `POST /jobs/analysis`.
- 주기적 스케줄링(cron-like) 구조 없음. 공식 Job interface 없음.

## Technology

**rq-scheduler 채택** (ADR-003 Accepted). 기존 RQ/Redis/worker 위에 시간 트리거만 더하는 최소 추가다. 본 초안 단계에서는 실제 주기 등록을 mock으로 두고 Job interface·스케줄 구조만 확정하며, 실제 트리거 등록은 후속 버전에서 rq-scheduler로 전환한다.

## Structure (초안)

| 요소 | 책임 |
| --- | --- |
| scheduler module | 등록된 job을 주기/수동으로 실행하는 진입점. rq-scheduler를 추상화해 감싸되, 본 범위에서는 구조만 두고 실제 주기 등록은 mock. |
| Job interface | `name`과 `run()` 수준의 최소 인터페이스. 기존 함수형 job(`collect_news_job`/`analyze_watchlist_job`)을 감싸는 수준. |
| schedule registry | job별 주기(cron-like 표현)와 enable 여부를 선언적으로 모아두는 단일 지점. 실제 등록은 후속. |
| mock job | 외부 연동 없이 흐름을 확인하는 job. `job_runs`에 기록. |
| 수동 실행 | endpoint 또는 CLI로 특정 job 1회 실행(기존 `POST /jobs/*` 흐름 재사용). |
| 결과 로그 | job 실행 결과를 `job_runs` + 로깅(설계 042)으로 남김. |

## Decisions

- **기술 확정: rq-scheduler** (ADR-003) — 기존 RQ/Redis 재사용, 스택 미증가. APScheduler(역할 중복·중복 실행 위험)·외부 cron(인프라 의존) 대비 우위.
- 실제 주기 등록·운영 적용은 범위 외(초안만) — 본 단계는 인터페이스·구조 고정.
- scheduler 구조의 책임 범위 문서화가 완료 조건 — 본 설계문서 + handoff + ADR로 충족.
- 기존 worker/job_runs 인프라를 대체하지 않는다 — 그 위에 얹는 구조.
- 작업 함수는 기존 동기 `def` job 패턴을 유지 — 스케줄 트리거만 추가해 재사용한다.
