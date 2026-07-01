# Codex Handoff Task

## Source Issue

- BE: JongEunLee310/project_stock#155 (대시보드 미니차트 추이 시계열 endpoint)
- FE 대응: JongEunLee310/project_stock_frontend#89
- 설계: `docs/designs/062-dashboard-trend-series.md`

## Task Summary

대시보드 미니차트(위험 스파크라인·시그널 스파크라인·중요 뉴스 바)에 실데이터를 공급할
`GET /dashboard/trends` endpoint를 추가한다. 최근 N일 일별 발생 건수 계열 3종을 기존
타임스탬프에서 파생하며, 신규 테이블·컬럼은 만들지 않는다.

## Goal

완료 시 다음이 참이어야 한다.

- `GET /dashboard/trends?days=N`이 인증 사용자 기준으로 계열 3종(`risk_alerts`·
  `review_signals`·`important_news`)의 일별 건수를 `ApiResponse[DashboardTrendSeriesResponse]`
  형태로 반환한다.
- 각 계열은 윈도우 전체 날짜를 결측일 0 채움으로 포함하고 날짜 오름차순이다.
- 세 계열은 `created_at` 기준 발생 건수이며 mutable-state 필터(`UNREAD`·active/만료)를
  적용하지 않는다.

## Background

- 설계 062가 계약·집계 소스·결정 사항을 확정한다. 구현은 그 문서를 따른다.
- 카드 숫자 지표·현금 도넛은 이미 `GET /dashboard/summary` 실데이터를 쓴다. 본 작업은
  미니차트용 시계열만 신설한다.
- 집계 소스(설계 §3): `risk_alerts`·`review_signals`는 `Alert.created_at`(alerts JOIN
  signals, signal_type 필터), `important_news`는 `AlertCandidate.created_at`
  (candidate_type NEWS_SURGE·DISCLOSURE, importance HIGH). `DashboardService`의
  카운트 쿼리와 동일한 테이블·타입 필터를 쓰되 state 필터는 제외한다.
- 확정 기본값(설계 §4): 윈도우 기본 14일·상한 90일, 결측 0 채움, state 필터 제외(세 계열
  일괄).

## Implementation Scope

- `app/domains/dashboard/schema.py`: `TrendDataPoint`·`TrendSeries`·
  `DashboardTrendSeriesResponse` 스키마 추가.
- `app/domains/dashboard/trend_service.py`(신규): `DashboardTrendService.get_trends`.
- `app/api/v1/endpoints/dashboard.py`: `GET /dashboard/trends` 라우트 추가(기존 summary·
  briefing과 동일한 인증 컨텍스트).
- 테스트: 서비스 단위·계열 필터 단위·API·계약 스냅샷.

## Out of Scope

- 신규 테이블·컬럼·마이그레이션(기존 타임스탬프에서만 집계).
- `DashboardSummaryResponse`의 `delta` 필드 채움.
- 현금 비중 추이 계열(이력 테이블 부재).
- 캐시 전략.
- FE 연동(별도 repo #89).

## Protected Files

없음.

## Requirements

- 응답은 공통 `ApiResponse` envelope를 따른다(`app/core/response.py`의 `success`).
- `days` 파라미터: 기본 14, 상한 90. 상한 초과 시 `VALIDATION_ERROR`(422).
- UTC 캘린더 날짜(YYYY-MM-DD) 기준 일별 집계. 날짜는 문자열.
- 사용자 귀속: 다른 user_id 데이터가 섞이지 않는다.
- 계열 순서·key 집합(`risk_alerts`·`review_signals`·`important_news`) 고정.

## Test Requirements

- 서비스 단위: 주어진 `days` 윈도우 길이만큼 각 계열이 `TrendDataPoint`를 반환, 결측일
  `count == 0`, 사용자 귀속 정확성.
- 계열 필터 단위: RISK_ALERT·THESIS_BROKEN → `risk_alerts`, SELL_REVIEW·OVERHEATED →
  `review_signals`, NEWS_SURGE·DISCLOSURE+HIGH → `important_news`에만 반영.
- state 필터 회귀: 읽음 처리·만료된 건도 발생일 기준으로 집계됨을 단언.
- API: 응답 형태(envelope·series key·days 일치), 인증 컨텍스트, `days` 상한 초과 422.
- 계약 스냅샷: `DashboardTrendSeriesResponse` 반영.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy app`
- `uv run pytest`

## Documentation Impact

- `docs/designs/062-dashboard-trend-series.md`는 본 브랜치에 포함(설계 확정본).
- 계약 스냅샷 문서·테스트가 있으면 신규 응답 스키마를 반영한다.

## ADR Need

불요. 신규 테이블·도메인 경계·외부 의존성 변경이 없고 기존 집계 패턴을 재사용한다.

## Failure Record Need

불요. 국소 신규 endpoint이며 집계·degradation은 테스트로 커버한다.

## Risk Level

Low. 기존 타임스탬프에서 읽기 전용 집계, 스키마 변경 없음, 인증 컨텍스트 재사용.

## Expected Output

- 스키마·서비스·라우트·테스트 구현이 담긴 PR(base=main).
- 설계 062 포함.
- 검증 3종(ruff·mypy·pytest) 통과 결과 보고.
- PR 메타데이터: labels(api·frontend-integration·signal·priority:medium)·milestone
  `API 계약 정렬 — 백엔드`·assignee.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 최신 main에서 분기했는지 확인하고, state 필터 제외 규칙(설계 §3·§4)을 정확히 지킨다.
