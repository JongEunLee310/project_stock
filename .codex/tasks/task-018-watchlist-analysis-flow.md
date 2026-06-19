# Codex Handoff Task

## Source Issue

Issue #19: 관심 종목 분석 통합 흐름 구현

## Task Summary

관심 종목 기준으로 뉴스 수집 → 정규화 → AI 요약 → 가설 충돌 판단 → Research Report → Signal → Alert를 하나의 Job으로 연결하는 오케스트레이션을 구현한다.

## Goal

- 하나의 Job 실행으로 관심 종목 분석 흐름이 동작한다.
- 분석 결과가 Research Report, Signal, Alert에 반영된다.
- 실패 지점이 Job Run에 기록된다(종목 단위 부분 실패 격리 포함).

## Background

- **구현 전 `docs/designs/019-watchlist-analysis-flow.md`를 반드시 읽는다.** 관련 설계: `017`, `018`, `020`.
- 선행 머지 필요: Issue #17(Signal, task-015), #18(Alert, task-017), #20(Rule Engine, task-016). 그리고 기존 #12/#15/#16(요약·충돌·리포트) 서비스.
- 신규 DB 테이블 없음. 기존 도메인 서비스를 조합한다.
- 외부 의존(LLM/뉴스)은 Mock 주입으로 테스트 가능해야 한다: `MockLLMClient`, `MockNewsAdapter`.
- **정규화 갭:** `raw_news_events`에는 `asset_id`가 없다. 본 흐름은 종목별로 수집하고 그 결과를 곧바로 해당 asset의 `NewsItem`으로 생성한다. 중복 생성을 막기 위해 `NewsItemRepository`에 `exists_by_url`(또는 `get_by_url`) 보조 메서드를 추가하고 신규 URL만 생성한다.
- 기존 서비스 시그니처:
  - `RawNewsService(db).collect_and_save(adapter, symbols) -> int`
  - `NewsAnalysisService(db, llm).summarize(news_item_id) -> NewsSummaryResult`
  - `ThesisAnalysisService(db, llm).analyze_conflict(news_item_id, thesis_id) -> ThesisConflictResult`
  - `ResearchReportService(db).create_report(ResearchReportCreate) -> ResearchReport`
  - `RuleEngine(rules, SignalRepository(db)).run(RuleContext) -> list[Signal]`
  - `AlertService(db).create_alert(user_id, signal) -> Alert | None`
  - `JobRunService(db).start/succeed/fail`
- 시작 전 최신 main에서 feature 브랜치를 생성한다.

## Implementation Scope

- `app/domains/analysis/__init__.py`
- `app/domains/analysis/schema.py` — `AnalysisFlowResult`
- `app/domains/analysis/service.py` — `WatchlistAnalysisService`
- `app/domains/news/repository.py` — `exists_by_url`(또는 `get_by_url`) 보조 메서드 추가
- `app/worker/jobs/analysis.py` — 기존 `analyze_watchlist_job` 스텁을 실제 구현으로 교체
- `tests/test_analysis_flow.py`

## Out of Scope

- 신규 DB 테이블/마이그레이션
- 신규 API 엔드포인트(통합 흐름은 worker job으로만 트리거)
- 외부 푸시 알림
- 뉴스 어댑터/LLM 어댑터 신규 구현
- 스케줄러/주기 실행 설정

## Protected Files

변경하지 않는 파일:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`, `docs/decisions/`

## Requirements

### AnalysisFlowResult (schema.py)

```python
class AnalysisFlowResult(BaseModel):
    watchlist_id: int
    processed_assets: int
    created_news_items: int
    created_reports: int
    created_signals: int
    created_alerts: int
    failures: list[dict[str, Any]]   # [{"asset_id": int, "error": str}]
```

### WatchlistAnalysisService (service.py)

```python
class WatchlistAnalysisService:
    def __init__(self, db: Session, llm_client: LLMClient, news_adapter: NewsAdapter)
    def run(self, watchlist_id: int) -> AnalysisFlowResult
```

`run` 책임 (설계 문서 흐름 준수):

1. watchlist 조회(없으면 `AppException(404)`), 소유자 `user_id`와 asset 목록 확보.
2. asset마다:
   1. `RawNewsService.collect_and_save(news_adapter, [symbol])`
   2. 수집 결과 중 신규 URL을 해당 asset의 `NewsItem`으로 생성(`exists_by_url`로 중복 제외)
   3. 각 신규 NewsItem `summarize`
   4. asset 활성 가설 존재 시 `analyze_conflict`
   5. `create_report`로 요약·충돌 종합 저장
   6. `RuleEngine(default_rules(), SignalRepository(db)).run(RuleContext(...))`
   7. 생성된 각 Signal에 `AlertService.create_alert(user_id, signal)` (중복은 None → 카운트 제외)
3. **부분 실패 격리:** asset 처리 중 예외는 `failures`에 `{asset_id, error}`로 누적하고 다음 asset 계속.
4. 집계된 `AnalysisFlowResult` 반환.

### analyze_watchlist_job (worker/jobs/analysis.py)

기존 스텁 교체:

```python
def analyze_watchlist_job(watchlist_id: int) -> None:
    db = SessionLocal()
    job_run_service = JobRunService(db)
    job_run_id = None
    try:
        job_run = job_run_service.start("watchlist_analysis", {"watchlist_id": watchlist_id})
        job_run_id = job_run.id
        result = WatchlistAnalysisService(db, <llm>, <adapter>).run(watchlist_id)
        # 부분 실패가 있으면 JobRun metadata/error에 기록
        job_run_service.succeed(job_run.id)
    except Exception as exc:
        if job_run_id is not None:
            job_run_service.fail(job_run_id, str(exc))
        raise
    finally:
        db.close()
```

- worker 기본 구성에서는 `MockLLMClient`, `MockNewsAdapter`를 주입한다(향후 이슈에서 실제 어댑터 교체).
- `result.failures`가 비어있지 않으면 JobRun을 실패로 기록하지 않되, 실패 종목·사유를 남긴다. JobRun 모델에 부분 실패를 기록할 방법(`metadata` 갱신 또는 `error_message`)을 사용한다. 전체 흐름 자체 예외만 `fail` 처리.

## Test Requirements

`tests/test_analysis_flow.py` (in-memory SQLite + Mock 주입):

- 정상 흐름 — watchlist의 asset에 대해 NewsItem/Report/Signal/Alert가 생성되고 `AnalysisFlowResult` 카운트가 반영됨
- 중복 수집 — 동일 URL 재수집 시 NewsItem이 중복 생성되지 않음(`exists_by_url`)
- 가설 충돌 흐름 — CONFLICTS 결과가 Rule Engine을 거쳐 Signal·Alert로 이어짐
- 부분 실패 격리 — 한 asset 처리 실패가 다른 asset 처리를 막지 않고 `failures`에 기록됨
- `analyze_watchlist_job` — JobRun이 start→succeed로 기록됨(존재하지 않는 watchlist는 JobRun fail)

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest tests/test_analysis_flow.py -v
```

## Documentation Impact

`docs/designs/019-watchlist-analysis-flow.md` 외 없음. 정규화 보조 메서드 추가로 `009-news-item-domain.md`에 한 줄 보강 가능(선택).

## ADR Need

없음. 단, raw→item 정규화 방식(종목별 수집 후 직접 생성)은 설계 문서에 근거가 기록되어 있어야 한다. 구조적 변경이 아니므로 ADR 불필요.

## Failure Record Need

없음.

## Risk Level

Medium — 여러 도메인 서비스를 조합하는 오케스트레이션. 다수 선행 이슈에 의존. 신규 테이블은 없음.

## Expected Output

- `app/domains/analysis/` 신규 파일 + `analysis.py` job 구현
- `NewsItemRepository.exists_by_url` 추가
- `tests/test_analysis_flow.py` 통과
- lint/typecheck 통과

## Rules

- 구현 전 `docs/designs/019-watchlist-analysis-flow.md`를 읽는다.
- 선행 이슈(#17, #18, #20) 머지 후 최신 main에서 시작한다.
- 기존 서비스 시그니처를 변경하지 않고 조합한다(필요한 보조 메서드만 추가).
- Mock 어댑터로 테스트 가능하게 의존성을 주입한다.
- 스코프 외 파일 변경 금지. 테스트 약화 금지. 보호 파일 변경 금지.
