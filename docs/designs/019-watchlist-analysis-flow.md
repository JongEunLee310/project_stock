# 019: 관심 종목 분석 통합 흐름

## 목적

관심 종목(Watchlist) 기준으로 뉴스 수집 → AI 요약 → 투자 가설 충돌 판단 → Research Report 생성 → Signal 생성 → Alert 생성까지 하나의 Job으로 연결한다.

## 위치

- `app/domains/analysis/service.py` — `WatchlistAnalysisService` (오케스트레이션)
- `app/worker/jobs/analysis.py` — 기존 `analyze_watchlist_job` 스텁을 실제 구현으로 교체(JobRun 수명주기 + 서비스 호출)

신규 DB 테이블 없음. 기존 도메인 서비스를 조합한다.

## 흐름

`WatchlistAnalysisService.run(watchlist_id) -> AnalysisFlowResult`

1. **관심 종목 조회** — `WatchlistRepository` / `WatchlistItemRepository`로 watchlist의 asset 목록 확보.
2. **종목별 반복** (asset 단위):
   1. **뉴스 수집** — `RawNewsService.collect_and_save(adapter, [symbol])`.
   2. **정규화** — 수집된 raw 이벤트를 해당 asset의 `NewsItem`으로 생성. *(현재 raw→item 자동 정규화 경로가 없어 본 흐름에서 신규 구현. 본 설계의 핵심 추가 책임.)*
   3. **AI 요약** — 각 NewsItem에 `NewsAnalysisService.summarize(news_item_id)`.
   4. **가설 충돌 판단** — asset에 연결된 활성 가설이 있으면 `ThesisAnalysisService.analyze_conflict(news_item_id, thesis_id)`.
   5. **Research Report 생성** — 요약·충돌 결과 종합해 `ResearchReportService.create_report(...)`.
   6. **Signal 생성** — `RuleEngine.run(RuleContext(...))`로 Signal 산출.
   7. **Alert 생성** — 생성된 각 Signal에 대해 watchlist 소유자에게 `AlertService.create_alert(user_id, signal)`.
3. **결과 집계** — 처리한 asset/news 수, 생성된 report/signal/alert 수 반환.

## 정규화(2-2) 설계

raw_news_events에는 asset_id가 없으므로, 본 흐름은 **종목별로 수집을 수행**하고 그 종목의 결과를 곧바로 `NewsItem(asset_id=...)`으로 생성한다.
중복 생성을 막기 위해 `url` 기준으로 기존 NewsItem 존재 여부를 확인한 뒤 신규만 생성한다(`NewsItemRepository`에 `get_by_url` 또는 `exists_by_url` 보조 메서드 추가).

## 실패 처리

- 전체 Job은 `JobRunService.start("watchlist_analysis", {...})`로 시작, 성공 시 `succeed`, 예외 시 `fail(error_message)`.
- **종목 단위 부분 실패 격리:** 한 asset 처리 중 예외가 발생해도 흐름을 중단하지 않고 해당 asset의 실패를 결과에 누적한 뒤 다음 asset을 계속 처리한다. 모든 asset 처리 후 실패가 있으면 JobRun `metadata`에 실패 종목·사유를 기록한다.
- LLM/외부 어댑터는 Mock 구현(`MockLLMClient`, `MockNewsAdapter`)을 주입해 테스트 가능하게 한다.

## AnalysisFlowResult (요약 반환)

```
class AnalysisFlowResult(BaseModel):
    watchlist_id: int
    processed_assets: int
    created_news_items: int
    created_reports: int
    created_signals: int
    created_alerts: int
    failures: list[dict]   # [{asset_id, error}]
```

## 완료 조건 매핑

- 하나의 Job 실행으로 흐름 동작 → `analyze_watchlist_job` → `WatchlistAnalysisService.run`
- 결과가 report/signal/alert에 반영 → 단계 6·7
- 실패 지점이 Job Run에 기록 → `JobRun.error_message` / `metadata.failures`

## 의존성

Issue #15, #16, #17(Signal), #18(Alert), #20(Rule Engine) 완료 후 진행.
