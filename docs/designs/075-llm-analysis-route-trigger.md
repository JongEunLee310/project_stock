# 075 · LLM 분석 실행 route·워커 잡 배선

Status: Draft
작성: Claude Code (orchestrator)
관련: 구현 이슈 BE #198, Epic BE #174(closed, 후속 과제 1번), Milestone 데이터 수집
파이프라인 — 백엔드(#5). 기준 문서 `docs/knowledge/llm-data-pipeline.md`(§19 route는
마지막·얇게). 선행 설계 `docs/designs/074-llm-analysis-orchestration.md`(7단계 —
오케스트레이션·결과 영속).

## 1. 배경

7단계(PR #192)까지로 `LLMAnalysisService.run_analysis`가 번들 조립→입력 영속→게이트웨이
호출→결과 영속을 완결했지만, 이를 실행할 진입점이 없다. 이 단계는 74 설계의 Decision PP
(route 미노출)가 미뤄 둔 route를 얇게 붙이고, 실행을 워커 잡으로 배선한다.

새 패턴을 만들지 않는다. 실행은 기존 RQ 워커 잡 선례(`analyze_watchlist_job`의
`SessionLocal` + `JobRunService` 기록 구조), 트리거는 기존 enqueue route 선례
(`POST /api/v1/worker/jobs/*`), 게이트웨이 조립은 `get_llm_gateway()` factory,
인증은 `get_current_user`를 그대로 잇는다.

## 2. 범위

포함:

- `app/worker/jobs/llm_analysis.py`(신규): `run_llm_analysis_job` — 잡 래퍼.
- `app/api/v1/endpoints/worker.py`(수정): `POST /jobs/llm-analysis` enqueue route 추가.
- `app/api/v1/endpoints/llm_analysis.py`(신규) + `router.py` 등록: run 목록·상세 조회 route.
- `app/domains/llm_analysis/schema.py`(수정): 조회용 요약·상세 projection 추가.
- `app/domains/llm_analysis/repository.py`(수정): `list_by_user`·`get_by_id_for_user` 조회 추가.
- 단위 테스트(외부 API 없이, `LLM_PROVIDER=mock` 기준).

비포함(후속·변경 없음):

- 주기 스케줄 등록(cron·scheduler registry 실배선) — 트리거는 수동 enqueue route까지.
- LLM 실 어댑터(`LocalLLMProvider` 등) — Epic #141 접점.
- 기존 `analyze_watchlist_job` 분석 플로우 수렴 리팩터 — 3단계 잔여 별도 과제.
- 결과 후처리(decision-log 연결·알림), FE 연동.
- `LLMAnalysisService.run_analysis`·`ContextBuilder`·게이트웨이 코어 변경(재사용).
- 신규 alembic revision — 스키마 변경 없음, 단일 head 유지.

## 3. 구성 요소

### 3.1 워커 잡 (`app/worker/jobs/llm_analysis.py`, 신규)

| 시그니처 | 책임 |
| --- | --- |
| `run_llm_analysis_job(user_id: int, task_type: str, symbols: list[tuple[str, str]]) -> None` | 세션·게이트웨이 조립 후 `LLMAnalysisService.run_analysis` 실행, `JobRun` 기록 |

절차(개념 순서, `analyze_watchlist_job` 선례 계승):

1. `SessionLocal()` 세션 생성, `JobRunService.start("llm_analysis", {...})` 기록.
2. `LLMAnalysisService(db, get_llm_gateway()).run_analysis(task_type, user_id, symbols)` 호출.
3. 반환된 run의 status에 따라 `JobRun`을 매핑한다: SUCCEEDED → `succeed`,
   FAILED → `fail(run.error_message)` (Decision QQ).
4. 잡 래퍼 자체 예외는 `fail` 기록 후 재발생, 세션은 finally에서 close.

### 3.2 enqueue route (`app/api/v1/endpoints/worker.py`, 수정)

| route | 책임 |
| --- | --- |
| `POST /api/v1/worker/jobs/llm-analysis` | 인증 사용자 기준 분석 잡 enqueue, `JobQueuedResponse` 반환 |

- 요청 schema: `LLMAnalysisJobRequest` — `task_type: LLMTaskType`, `symbols: list[SymbolRef]`
  (`SymbolRef`: `symbol: str`, `market: str`, `min_length=1`).
- `user_id`는 요청 본문이 아니라 `get_current_user`에서 얻는다(Decision RR).
- RQ `Queue("default").enqueue(run_llm_analysis_job, ...)` — 기존 잡 enqueue와 동일. 비즈니스
  로직 없음.

### 3.3 조회 route (`app/api/v1/endpoints/llm_analysis.py`, 신규)

| route | 책임 |
| --- | --- |
| `GET /api/v1/llm-analysis/runs` | 본인 run 목록(최신순, 요약 projection) |
| `GET /api/v1/llm-analysis/runs/{run_id}` | 본인 run 상세(입력·출력 포함), 타 사용자·부재 시 404 |

`router.py`에 `prefix="/llm-analysis", tags=["llm-analysis"]`로 등록. 두 route 모두
`get_current_user` 필수, repository 호출만 한다(Decision SS).

### 3.4 조회 projection (`app/domains/llm_analysis/schema.py`, 수정)

| 심볼 | 책임 |
| --- | --- |
| `LLMAnalysisRunSummary` | 목록용 — id, task_type, related_symbols, status, model_name, prompt_version, provider, error_message, created_at. `input_context_json`·`output_json` 제외(Decision TT) |
| `LLMAnalysisRunDetail` | 상세용 — Summary 필드 + `input_context_json`, `output_json` |

### 3.5 repository 조회 (`app/domains/llm_analysis/repository.py`, 수정)

| 시그니처 | 책임 |
| --- | --- |
| `list_by_user(user_id: int, limit: int = 20) -> list[LLMAnalysisRun]` | 본인 run 최신순 목록 |
| `get_by_id_for_user(run_id: int, user_id: int) -> LLMAnalysisRun \| None` | 본인 run 단건(소유권 필터 포함) |

## 4. Decisions

- **QQ. 트리거는 RQ 잡 + 수동 enqueue route**: LLM 호출은 지연이 길어 요청-응답 경로에서
  동기 실행하지 않고, 기존 RQ 워커 잡 선례로 배선한다. `JobRun` 기록도 선례를 따르되, 서비스가
  자체 처리한 실패(run.status=FAILED)는 잡 래퍼가 삼키지 않고 `JobRun` FAILED로 승격해 잡
  이력에서도 보이게 한다. 주기 스케줄 등록은 실행 주기 요구가 구체화된 뒤 별도 단계로 미룬다.
- **RR. user_id는 인증 사용자에서**: 분석 run은 사용자 스코프 데이터(포트폴리오·decision-log)를
  조립하므로, 기존 무인증 worker enqueue route와 달리 `get_current_user`를 필수로 하고 요청
  본문의 user_id 지정을 허용하지 않는다.
- **SS. 조회는 도메인 prefix로 분리**: enqueue(트리거)는 기존 `/worker/jobs/*`에, 조회는
  `/llm-analysis/runs`에 둔다. 트리거와 결과 조회의 책임을 분리하고, 조회 route는 repository
  호출만 하는 얇은 read 경로로 유지한다(§19).
- **TT. 목록 projection은 원문 제외**: `input_context_json`은 번들 전문이라 크다. 목록은 요약
  projection으로 제한하고 입력·출력 원문은 상세 조회에서만 반환한다. 소유권은 repository 조회
  단계에서 필터링하며 타 사용자 run은 존재 여부를 구분하지 않고 404로 답한다.

## 5. 마이그레이션

없음. `llm_analysis_runs`·`job_runs` 테이블을 그대로 사용한다. alembic 단일 head 유지.

## 6. 테스트

- 잡 래퍼: run SUCCEEDED → `JobRun` succeeded, run FAILED → `JobRun` failed +
  `error_message` 전파, 래퍼 예외 → `JobRun` failed 후 재발생.
- enqueue route: 인증 사용자로 202/200 + `JobQueuedResponse`, 미인증 401, `symbols` 빈
  리스트 422. enqueue는 기존 worker route 테스트 선례대로 큐를 대체(mock)해 검증.
- 조회 route: 본인 run 목록 최신순·요약 필드만, 상세는 입력·출력 포함, 타 사용자 run 404,
  미인증 401.
- repository: `list_by_user` 정렬·범위, `get_by_id_for_user` 소유권 필터.
- 외부 API 호출 없이 통과, CI 3종(ruff + mypy + pytest) 통과.

## 7. ADR 판단

불필요. 기존 워커 잡·enqueue route·factory·인증 선례를 그대로 잇는 배선이며 경계·아키텍처
변경이 없다. 주기 스케줄 도입이나 실행 큐 구조 변경이 필요해지는 시점에 별도로 판단한다.
