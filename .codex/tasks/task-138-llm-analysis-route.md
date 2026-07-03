# Codex Handoff Task

## Source Issue

BE #198 (Epic BE #174 후속). 설계 `docs/designs/075-llm-analysis-route-trigger.md`. 기준 문서
`docs/knowledge/llm-data-pipeline.md`(§19 route는 마지막·얇게). 선행 설계
`docs/designs/074-llm-analysis-orchestration.md`(7단계 — 오케스트레이션·결과 영속, PR #192).

## Task Summary

7단계까지 완성된 `LLMAnalysisService.run_analysis`에 진입점을 배선한다. 실행은 RQ 워커 잡
(`run_llm_analysis_job`)으로, 트리거는 인증 사용자 기준 enqueue route로, 결과 확인은
`/llm-analysis/runs` 조회 route로 노출한다. 기존 워커 잡·enqueue route·factory·인증 선례를
그대로 잇고 새 패턴을 만들지 않는다.

## Goal

- 인증된 사용자가 `POST /api/v1/worker/jobs/llm-analysis`로 분석 잡을 enqueue할 수 있다.
- 잡 실행이 `JobRun`("llm_analysis")으로 기록되고, run.status=FAILED면 `JobRun`도 FAILED다.
- `GET /api/v1/llm-analysis/runs`·`/runs/{run_id}`가 본인 run만 반환한다(타 사용자 run 404).
- route에 비즈니스 로직이 없다(서비스·repository 호출만).
- CI 3종(ruff + mypy + pytest) 통과, alembic 단일 head 유지(마이그레이션 없음).

## Background

이미 존재하는 재사용 대상(수정 금지):

- 서비스: `app/domains/llm_analysis/service.py` `LLMAnalysisService(db, gateway,
  context_builder=None).run_analysis(task_type: LLMTaskType, user_id: int,
  symbols: list[tuple[str, str]]) -> LLMAnalysisRun`. 실패를 자체 처리해 status=FAILED run을
  반환한다(예외를 밖으로 던지지 않음).
- 게이트웨이 조립: `app/adapters/factory.py` `get_llm_gateway()` — `LLM_PROVIDER` 설정 기반
  (mock/cloud/local).
- 워커 잡 선례: `app/worker/jobs/analysis.py` `analyze_watchlist_job` — `SessionLocal()` +
  `JobRunService(db).start(name, payload)` / `succeed(id)` / `fail(id, message)` + finally close.
- enqueue route 선례: `app/api/v1/endpoints/worker.py` — `Queue("default",
  connection=get_redis_connection()).enqueue(job_fn, args...)`, `JobQueuedResponse`,
  `ApiResponse`/`success`(`app/core/response.py`).
- 인증: `app/api/v1/deps.py` `get_current_user` → `User`(`.id`). 인증 route 선례는
  `app/api/v1/endpoints/reports.py`.
- 모델: `app/domains/llm_analysis/model.py` `LLMAnalysisRun`(TimestampMixin — `created_at` 보유.
  필드: `user_id`, `task_type`, `related_symbols: list[str]`, `input_context_json`, `output_json`,
  `status`, `model_name`, `prompt_version`, `provider`, `related_decision_log_id`, `error_message`).
- enum: `app/adapters/llm/types.py` `LLMTaskType`(str Enum), `app/domains/llm_analysis/schema.py`
  `RunStatus`(PENDING/SUCCEEDED/FAILED).
- router 등록: `app/api/v1/router.py` `include_router(..., prefix=..., tags=[...])` 패턴.

## Implementation Scope

- 신설 `app/worker/jobs/llm_analysis.py`:
  - `run_llm_analysis_job(user_id: int, task_type: str, symbols: list[tuple[str, str]]) -> None`.
  - 절차: `SessionLocal()` → `JobRunService.start("llm_analysis", {"user_id": ..., "task_type":
    ..., "symbols": ...})` → `LLMAnalysisService(db, get_llm_gateway()).run_analysis(
    LLMTaskType(task_type), user_id, symbols)` → run.status가 SUCCEEDED면 `succeed`, FAILED면
    `fail(job_run_id, run.error_message)` → 래퍼 자체 예외는 `fail` 기록 후 재발생, finally에서
    `db.close()`.
- 수정 `app/api/v1/endpoints/worker.py`:
  - `SymbolRef(BaseModel)`: `symbol: str`, `market: str`.
  - `LLMAnalysisJobRequest(BaseModel)`: `task_type: LLMTaskType`,
    `symbols: list[SymbolRef] = Field(min_length=1)`.
  - `POST /jobs/llm-analysis`: `current_user: User = Depends(get_current_user)` 필수.
    `queue.enqueue(run_llm_analysis_job, current_user.id, payload.task_type.value,
    [(s.symbol, s.market) for s in payload.symbols])` → `JobQueuedResponse` 반환. 기존 두
    enqueue route와 동일한 얇은 형태.
- 수정 `app/domains/llm_analysis/schema.py`(additive):
  - `LLMAnalysisRunSummary`: `id`, `task_type`, `related_symbols`, `status`, `model_name`,
    `prompt_version`, `provider`, `error_message`, `created_at`. (`from_attributes` 구성)
  - `LLMAnalysisRunDetail`: Summary 필드 + `input_context_json`, `output_json`.
- 수정 `app/domains/llm_analysis/repository.py`(additive):
  - `list_by_user(user_id: int, limit: int = 20) -> list[LLMAnalysisRun]` — `created_at`(동률 시
    `id`) 내림차순.
  - `get_by_id_for_user(run_id: int, user_id: int) -> LLMAnalysisRun | None` — 소유권 필터 포함.
- 신설 `app/api/v1/endpoints/llm_analysis.py` + `app/api/v1/router.py` 등록
  (`prefix="/llm-analysis"`, `tags=["llm-analysis"]`):
  - `GET /runs` → `ApiResponse[list[LLMAnalysisRunSummary]]`, `limit` query(기본 20, 상한 100).
  - `GET /runs/{run_id}` → `ApiResponse[LLMAnalysisRunDetail]`, 부재·타 사용자 소유 시 404.
  - 두 route 모두 `get_current_user` 필수, repository 호출만.

## Out of Scope

- `LLMAnalysisService.run_analysis`·`ContextBuilder`·게이트웨이 코어·factory 변경.
- 주기 스케줄 등록(scheduler registry·cron), `app/scheduler/*` 변경.
- LLM 실 어댑터(`LocalLLMProvider` 등) 구현.
- 기존 `analyze_watchlist_job`·`app/domains/analysis/*` 변경.
- decision-log 연결·알림 등 결과 후처리, FE 연동.
- 신규 alembic revision — 스키마 변경 없음.

## Protected Files

- `app/domains/llm_analysis/model.py` — 변경 금지.
- `app/domains/llm_analysis/service.py` — 변경 금지(소비만).
- `app/domains/llm_analysis/schema.py`·`repository.py` — **추가만** 허용, 기존 심볼 불변.
- `app/adapters/llm/*`·`app/adapters/factory.py` — 참조만.
- `app/domains/llm_context/*`·`app/domains/analysis/*`·`app/scheduler/*` — 참조만.
- `alembic/versions/*` — 신규 revision 금지.

## Requirements

- 반환·중간 타입 이름에 `Dto`를 쓰지 않는다(projection 네이밍).
- `user_id`는 요청 본문이 아니라 인증 사용자에서 얻는다(설계 075 Decision RR).
- 목록 응답에 `input_context_json`·`output_json`을 포함하지 않는다(Decision TT).
- 타 사용자 run은 존재 여부를 구분하지 않고 404로 답한다.
- run.status=FAILED를 잡 래퍼가 삼키지 않고 `JobRun` FAILED로 승격한다(Decision QQ).
- 타입 주석 완전화(mypy `no-untyped-def` 회피).

## Test Requirements

`tests/test_worker_jobs.py` 스타일(전용 sqlite engine + `SessionLocal` monkeypatch)과
`tests/conftest.py`의 `client`·`set_current_user` 선례를 따른다. RQ enqueue는 기존 worker route
테스트처럼 큐를 대체(monkeypatch)해 검증한다.

- 잡 래퍼: run SUCCEEDED → `JobRun` succeeded / run FAILED → `JobRun` failed + `error_message`
  전파 / 래퍼 예외 → `JobRun` failed 후 재발생. 게이트웨이는 `MockLLMClient` 구성 또는
  `LLM_PROVIDER=mock` 경로 사용.
- enqueue route: 인증 사용자로 성공 + `JobQueuedResponse`, 미인증 401, `symbols` 빈 리스트 422.
  enqueue 인자에 `current_user.id`가 전달되는지 검증.
- 조회 route: 본인 run 목록 최신순·요약 필드만(`input_context_json` 부재 확인), 상세는
  입력·출력 포함, 타 사용자 run 404, 미인증 401.
- repository: `list_by_user` 정렬·limit, `get_by_id_for_user` 소유권 필터.
- 외부 API 호출 없이 통과한다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`
- `uv run alembic heads`  # 단일 head 확인(마이그레이션 없음)

## Documentation Impact

설계 `docs/designs/075-llm-analysis-route-trigger.md`·본 핸드오프가 같은 PR에 포함된다. 지침서
갱신 불필요(§19 route 서술과 정합).

## ADR Need

불필요. 기존 워커 잡·enqueue route·인증 선례를 잇는 배선이며 경계·아키텍처 변경이 없다
(설계 075 §7).

## Failure Record Need

불필요. 신규 배선이며 알려진 실패 패턴 대응이 아니다.

## Risk Level

Low–Medium. 신규 파일·additive 수정 위주라 회귀 위험은 제한적이다. 핵심 검증 지점은 세 가지다:
조회 route의 소유권 필터(타 사용자 run 노출 금지), run FAILED의 `JobRun` 승격(실패 가시성),
목록 projection에서 입력·출력 원문 제외.

## Expected Output

`app/worker/jobs/llm_analysis.py`·`app/api/v1/endpoints/llm_analysis.py` 신설 +
`worker.py`·`router.py`·`schema.py`·`repository.py` additive 수정 + 테스트 신설. 검증 명령 4종
결과와 함께 요약.

## Decisions 요약 (설계 075 참조)

- **QQ. 트리거는 RQ 잡 + 수동 enqueue route**: 동기 실행 금지, `JobRun` 기록, run FAILED는
  `JobRun` FAILED로 승격. 주기 스케줄은 후속.
- **RR. user_id는 인증 사용자에서**: `get_current_user` 필수, 본문 user_id 지정 불허.
- **SS. 조회는 도메인 prefix로 분리**: 트리거는 `/worker/jobs/*`, 조회는 `/llm-analysis/runs`.
- **TT. 목록 projection은 원문 제외**: 입력·출력 원문은 상세 조회에서만, 타 사용자 run은 404.
