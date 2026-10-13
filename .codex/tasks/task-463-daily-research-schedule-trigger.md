# Codex Handoff Task

## Source Issue

#463 — [BE] 에이전트1: 스케줄·트리거 전환과 기존 관심종목 분석 흐름 제거 (에픽 #459)

## Task Summary

일일 리서치 에이전트(`DailyResearchAgent`)를 worker job으로 감싸 정기 스케줄, 관심종목 추가 트리거, 워커 API
수동 실행에 연결한다. 기존 관심종목 분석 흐름(`WatchlistAnalysisService`, 분석 job, 분석 스케줄 4개,
`ANALYSIS_SCHEDULE_ENABLED`)은 제거한다(ADR-020 §4).

## Goal

- 평일 07:30 KST(`30 22 * * 0-4` UTC)에 전 관심종목 일일 브리프가 생성된다.
- 관심종목에 종목을 추가하면 그 종목만 즉시 에이전트가 실행된다.
- `POST /api/v1/worker/jobs/analysis`는 경로·요청(`{"watchlist_id": int}`)·응답·rate limit을 그대로 유지하고,
  해당 관심목록 종목들에 대해 에이전트를 실행한다(FE `triggerAnalysis`가 이 계약을 쓴다).
- 제거한 코드의 참조가 남지 않는다.

## Background

- 결정 정본: `docs/decisions/ADR-020-task-agents-fixed-workflow.md` §4, 설계 `docs/designs/459-daily-research-agent.md`.
  **반드시 먼저 읽는다.**
- 에이전트: `app/domains/agents/daily_research/service.py` — `DailyResearchAgent(db, embedder, vector_store,
  gateway, now=..., obsidian_writer=None).run(asset_ids=None, brief_date=None)`. 수동 스크립트
  `scripts/run_daily_research.py`가 조립 예시다(이미 `get_obsidian_writer()`를 넘긴다).
- 기존 흐름: `app/worker/jobs/analysis.py`(`enqueue_watchlist_analysis_safe`, `analyze_watchlist_job`,
  `analyze_all_watchlists_job`), `app/domains/analysis/`, `app/scheduler/registry.py`의 `analysis_*` 4개,
  `app/core/config.py`의 `ANALYSIS_SCHEDULE_ENABLED`, `.env.example`, 엔드포인트 `app/api/v1/endpoints/worker.py`
  (`enqueue_analysis_job`), `app/api/v1/endpoints/watchlists.py`(`add_watchlist_item`).
- job 패턴 참고: `app/worker/jobs/rag.py`(`JobRunService` start/succeed/fail), `analysis.py`의
  `_record_partial_failures`.
- PR #468 리뷰 S1: `_run_asset`이 종목마다 `while EmbeddingIndexer(...).run().has_more`로 임베딩 backlog를 끝까지
  처리한다. backlog가 크면 첫 종목에서 오래 걸리고 종목마다 반복한다.
- 의존성 추가는 없다. `uv add`, `uv sync`, 네트워크, `git fetch`, docker 명령을 하지 않는다.

## Implementation Scope

1. **job**(`app/worker/jobs/agents.py` 신규)
   - `run_daily_research_job(asset_ids: list[int] | None = None) -> None` — `JobRunService`로
     `daily_research_agent` 실행 기록(metadata에 `asset_ids`). 실행 전 임베딩 backlog를 한 번 끝까지 처리하고
     (`EmbeddingIndexer`; `EmbeddingError`면 경고 로그 후 계속 — 과거 맥락만 비는 것을 허용), 이어서
     `DailyResearchAgent(..., obsidian_writer=get_obsidian_writer()).run(asset_ids)`를 실행한다. 결과의 `failed`·
     `note_failures`는 job metadata `partial_failures`에 기록한다. 예외는 job 실패로 기록하고 다시 던진다.
   - `enqueue_daily_research_safe(asset_ids: list[int]) -> None` — enqueue 실패는 경고 로그만 남긴다(기존
     `enqueue_watchlist_analysis_safe`와 같은 정책).
2. **에이전트 정리(PR #468 S1)** — `_run_asset`에서 인덱서 루프를 제거한다. 인덱서 실행은 job(과 수동 스크립트)이
   에이전트 실행 전에 한 번 맡는다. `DailyResearchAgent` 생성자 인자는 바꾸지 않는다. 스크립트
   `scripts/run_daily_research.py`도 실행 전에 같은 backlog 처리를 한다(job과 공용 함수로 둬도 된다).
3. **스케줄** — `daily_research_agent`(`30 22 * * 0-4`, `enabled=True`)를 등록하고 `analysis_*` 4개를 제거한다.
4. **트리거**
   - `add_watchlist_item`: 추가된 항목의 `asset_id` 하나로 `enqueue_daily_research_safe`를 호출한다.
   - `enqueue_analysis_job`: 경로·요청·응답·rate limit(키 이름 포함)·summary 문구 외 계약 유지. 요청한 사용자가
     소유한 관심목록인지 확인한 뒤(아니면 기존 관심목록 API와 같은 404 처리를 따른다) 그 관심목록의 asset id
     목록으로 `run_daily_research_job`을 enqueue한다. 종목이 없으면 enqueue하지 않고 기존 응답 형식을 쓸 수
     있는지 판단해 보고한다(가정으로 기록). description 문구는 일일 리서치 에이전트 실행으로 고친다.
5. **제거** — `app/domains/analysis/`, `app/worker/jobs/analysis.py`, `ANALYSIS_SCHEDULE_ENABLED`(config,
   `.env.example`, compose 파일 등 모든 참조), 관련 테스트(`tests/test_analysis_flow.py`와 다른 테스트의 분석 부분).
   `NewsAnalysisService.summarize`, `ThesisConflictService.analyze_conflict` 등 다른 도메인 함수는 남긴다(에이전트
   3에서 재검토). 제거 후 호출처가 없어지는 함수 목록을 최종 보고에 적는다.
6. **문서**
   - `docs/designs/019-watchlist-analysis-flow.md` 상단 상태를 대체됨(superseded by ADR-020, 설계 459)으로 표시한다.
     본문은 바꾸지 않는다.
   - 설계 459 §6(또는 트리거 절)에 job 이름, backlog 처리 위치, 워커 API 계약 유지를 반영한다.
   - 설계 459 OQ3: `news_items.summary` 사용처를 조사해 결과를 OQ3 행에 적는다. 이미 제목 fallback이 있는 곳
     (예: `high_impact_rule.py`), 빈 값이 그대로 노출되는 곳을 구분한다. 코드 수정은 BE 응답에서 빈 문자열/None이
     문제를 일으키는 경우에만 최소로 하고, 그렇지 않으면 문서 기록만 한다.

## Out of Scope

- FE 변경(경로·요청 계약을 유지하므로 불필요)
- `news_items.summary` 컬럼 삭제, 기존 리포트 데이터 정리
- 에이전트 2~4, 가설 충돌 신호 복구
- 에이전트 워크플로 로직 변경(인덱서 위치 이동 외)

## Protected Files

없음. (`docs/decisions/`는 수정하지 않는다.)

## Test Requirements

- job: 성공 시 job run succeed와 에이전트 호출 인자(`asset_ids`, obsidian writer 전달), backlog 처리가 에이전트보다
  먼저 1회 실행, `EmbeddingError`여도 에이전트 실행, 부분 실패 metadata 기록, 예외 시 fail 기록
- 에이전트: 종목 루프에서 인덱서를 호출하지 않음(기존 테스트 갱신)
- 스케줄: `daily_research_agent` cron, `analysis_*` 부재, 설정 필드 부재
- 관심종목 추가: 추가한 asset id로 enqueue, enqueue 실패해도 201
- 워커 API: 소유 관심목록 → asset id로 enqueue, 미소유 → 404, rate limit 429 유지
- 제거 확인: `grep -rnE "domains\.analysis|WatchlistAnalysis|ANALYSIS_SCHEDULE|analyze_watchlist_job|analyze_all_watchlists_job|enqueue_watchlist_analysis" app scripts tests .env.example docker-compose*.yml` 결과 0건

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

## ADR Need

불필요(ADR-020이 결정을 담고 있음).

## Failure Record Need

불필요.

## Risk Level

Medium — 코드 제거와 트리거 전환. 워커 API는 FE가 쓰는 계약을 유지한다.

## Expected Output

- 현재 브랜치 `feat/463-daily-research-schedule-trigger`에서 작업한다. 새 브랜치를 만들지 않는다.
- 커밋이 샌드박스에서 막히면 미커밋 상태로 두고 보고한다. push와 PR 생성은 하지 않는다.
- 최종 보고: 변경·삭제 파일 목록, 호출처가 없어진 함수 목록, OQ3 조사 결과, 가정, 검증 결과

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
