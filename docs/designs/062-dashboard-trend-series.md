# 062 · 대시보드 미니차트 추이 시계열 (Dashboard Trend Series)

Status: Draft
작성: Claude Code (orchestrator)
관련: BE #155, FE #89(위험 스파크라인·시그널 스파크라인·중요뉴스 바), 설계 058(대시보드 브리핑), `DashboardSummaryResponse`

## 1. 배경

대시보드 미니차트(스파크라인)는 위험 알림·검토 시그널·중요 뉴스의 최근 N일 일별 건수 추이를
보여준다(FE 이슈 #89). 개발자 결정: 미니차트 UI는 유지하고 실데이터로 연동한다.

카드 숫자 지표와 현금 도넛은 이미 `GET /dashboard/summary` 실데이터를 사용한다.
미니차트만 BE 출처가 없는 상태다. 세 계열은 모두 기존 테이블의 타임스탬프 컬럼에서
일별 집계로 파생할 수 있으며, 신규 테이블·컬럼 없이 구현 가능하다.

`DashboardSummaryResponse`에 `risk_alert_delta`·`important_news_delta`·`review_signal_delta`
필드가 이미 `= None`으로 예약되어 있다(코드 주석: "히스토리 스냅샷 도입 시 계산(후속)").
트렌드 시리즈 endpoint는 그 delta 계산의 기반 데이터가 되며, delta 채움 자체는 본 설계 범위
밖이다.

## 2. 범위

포함:

- 일별 집계 계열 3종: 위험 알림·검토 시그널·중요 뉴스.
- 응답 스키마 `DashboardTrendSeriesResponse`.
- `DashboardTrendService` 서비스.
- API 엔드포인트 `GET /dashboard/trends`.

비포함(분리):

- 신규 테이블·컬럼 추가 — 기존 타임스탬프에서 집계하므로 DB 스키마 변경 없음.
- `DashboardSummaryResponse`의 `delta` 필드 채움 — 본 설계는 raw 시계열만 반환한다.
- 캐시 전략 — 필요 시 후속.
- 현금 추이 계열 — 포트폴리오 `cash_balance` 이력 테이블이 없어 파생 불가. 후속.

## 3. 집계 소스 — 기존 타임스탬프 활용

신규 테이블 없이 기존 타임스탬프 컬럼에서 UTC 날짜 기준 일별 집계를 수행한다. 세 계열의
집계 기준은 `DashboardService`의 현재 카운트 계산과 동일한 테이블·타입 필터를 따르되,
**mutable-state 필터(`UNREAD` 상태·`active`/만료 판정)는 세 계열 모두 적용하지 않는다**.
현재 카운트는 "지금 미읽음·활성인 건수"라는 시점 상태값이지만, 트렌드는 `created_at` 기준의
발생 건수 추이이므로 이후 상태 변화(읽음 처리·만료)에 흔들리지 않아야 하기 때문이다.
따라서 아래 표의 소스는 type/importance/user 필터만 유지한다.

| 계열 | 집계 기준 컬럼 | 소스 테이블·필터(type/user만) | 요약이 추가로 쓰는 state 필터(트렌드는 제외) |
| --- | --- | --- | --- |
| risk_alerts | `Alert.created_at` | `alerts` JOIN `signals`, `Signal.signal_type IN (RISK_ALERT, THESIS_BROKEN)`, `Alert.user_id = ?` | `Alert.status = UNREAD` |
| review_signals | `Alert.created_at` | `alerts` JOIN `signals`, `Signal.signal_type IN (SELL_REVIEW, OVERHEATED)`, `Alert.user_id = ?` | `active_clause`(만료 미도래) |
| important_news | `AlertCandidate.created_at` | `alert_candidates`, `candidate_type IN (NEWS_SURGE, DISCLOSURE)`, `importance = HIGH`, `user_id = ?` | `AlertCandidate.status = UNREAD` |

**`Alert.created_at` 선택 이유**: `Signal`에는 `user_id`가 없다. 사용자 귀속을 판단하려면
`alerts` 테이블을 거쳐야 하며, `Alert.created_at`이 사용자에게 알림이 생성된 시각이므로
카운트 기준으로 일관성이 있다. `Signal.created_at`(신호 생성 시각)이 아니라 `Alert.created_at`을
사용한다.

**`AlertCandidate.created_at` 선택 이유**: 중요 뉴스 카운트는 `DashboardService._count_important_news`가
`AlertCandidate`를 기준으로 한다. 트렌드도 같은 테이블·같은 필터를 사용해 일관성을 유지한다.
`NewsItem.created_at`(DB 입력 시각, `TimestampMixin` 제공 — non-null 확인됨)이나
`NewsItem.published_at`(외부 발행 시각, nullable)을 직접 사용하지 않는다.

**날짜 집계 단위**: UTC 캘린더 날짜(YYYY-MM-DD). `DashboardService`가 UTC 기준으로 동작하므로
일관성을 유지한다. FE는 날짜 문자열을 타임존 변환 없이 표시한다(price-series-api.md의
일봉 date 처리 선례와 동일).

## 4. 결정 필요 항목

| 항목 | 설명 | 권고 |
| --- | --- | --- |
| 윈도우 길이 N | 몇 일치 데이터를 반환할지 | 기본 14일 권고. 쿼리 파라미터 `?days=N`으로 노출, 상한(예: 90일)을 두어 과부하 방지 |
| 결측 구간 0 채움 | 거래가 없는 날의 처리 | 0으로 채워 반환하는 쪽이 FE 스파크라인 렌더링에 유리. 생략 시 FE가 직접 채워야 함 |
| mutable-state 필터 제외 | 세 계열 모두 `UNREAD`·`active` 등 상태 필터를 제외하고 발생 건수를 집계 | 트렌드는 누적 발생 건수 추이가 자연스러우므로 세 계열 일괄로 상태 필터를 빼는 것을 권고(§3). 요약 카드 숫자와 값이 달라질 수 있음을 FE·핸드오프에 명시. 핸드오프 전 확정 |

## 5. 응답 스키마

`TrendDataPoint(BaseModel)`:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| date | str | UTC 캘린더 날짜 (YYYY-MM-DD) |
| count | int | 해당 날 집계 건수 (결측 → 0) |

`TrendSeries(BaseModel)`:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| key | str | 계열 식별자: `risk_alerts` / `review_signals` / `important_news` |
| data | list[TrendDataPoint] | 날짜 오름차순, 윈도우 전체 (결측일 포함) |

`DashboardTrendSeriesResponse(BaseModel)`:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| days | int | 실제 반환한 윈도우 길이 |
| series | list[TrendSeries] | 계열 목록 (3개 고정) |

API 응답: `ApiResponse[DashboardTrendSeriesResponse]` — 공통 envelope 준수.

## 6. 서비스

신규 `app/domains/dashboard/trend_service.py`:

```
class DashboardTrendService:
    def __init__(self, db: Session) -> None
    def get_trends(self, user_id: int, days: int) -> DashboardTrendSeriesResponse
```

`get_trends` 책임(순서):

1. `days`를 받아 집계 시작일을 계산한다(UTC 기준 `today - days + 1`일).
2. `Alert.created_at`을 UTC 날짜로 잘라 일별 카운트를 계산한다 — `risk_alerts` 계열(Signal
   join, RISK_ALERT·THESIS_BROKEN)·`review_signals` 계열(Signal join, SELL_REVIEW·
   OVERHEATED).
3. `AlertCandidate.created_at`을 UTC 날짜로 잘라 일별 카운트를 계산한다 — `important_news`
   계열(NEWS_SURGE·DISCLOSURE, HIGH).
4. 각 계열의 집계 결과에 0 채움을 적용해 `days`개 날짜 전체를 채운다.
5. `DashboardTrendSeriesResponse`로 조립해 반환한다.

`DashboardService`의 카운트 쿼리를 참고해 동일 필터를 유지한다. 기존 `_active_clause`
(signals의 만료 판정)은 trend 계열에 적용하지 않는다 — 만료와 무관하게 생성된 건수를 세기
때문이다(결정 필요 항목 §4).

## 7. API

기존 `app/api/v1/endpoints/dashboard.py`에 라우트를 추가한다:

| Method | Path | 쿼리 파라미터 | 응답 | 비고 |
| --- | --- | --- | --- | --- |
| GET | `/dashboard/trends` | `days: int` (선택, 기본·상한은 §4 결정) | `DashboardTrendSeriesResponse` | 공통 envelope |

- 인증: `GET /dashboard/summary`와 동일한 사용자 컨텍스트를 따른다.
- `days` 파라미터: 기본값·상한은 §4 결정 필요 항목에서 확정. 상한 초과 시
  `VALIDATION_ERROR`(422).
- 에러: 데이터가 없는 윈도우는 0 채움으로 처리하며 404가 아니다.

## 8. 의존성

- `app/domains/alerts/model.py`(`Alert.created_at`) — 기존 모델 재사용, 변경 없음.
- `app/domains/signals/model.py`(`Signal.signal_type`) — 기존 모델 재사용, 변경 없음.
- `app/domains/alert_candidates/model.py`(`AlertCandidate.created_at`) — 기존 모델 재사용,
  변경 없음.
- `app/domains/dashboard/schema.py`(`DashboardTrendSeriesResponse` 신규 추가) — 기존 파일에
  스키마를 추가하거나 별도 파일로 분리한다.
- `app/core/response.py`(`ApiResponse`·`success`) — 그대로 사용.
- `app/api/v1/endpoints/dashboard.py` — 라우트 추가.

## 9. 테스트

- 서비스 단위: 주어진 `days` 윈도우에 대해 계열 3개가 정확한 길이의 `TrendDataPoint`를
  반환하는지, 데이터가 없는 날에 `count == 0`으로 채워지는지, 사용자 귀속이 올바른지
  (다른 user_id의 데이터가 섞이지 않는지) 단언.
- 각 계열 필터 단위: RISK_ALERT·THESIS_BROKEN이 `risk_alerts`에만 반영되는지,
  NEWS_SURGE·DISCLOSURE + HIGH가 `important_news`에만 반영되는지 단언.
- API: `GET /dashboard/trends` 응답 형태(envelope·series key 집합·days 일치), 인증 컨텍스트,
  `days` 상한 초과 422.
- 계약 스냅샷: `DashboardTrendSeriesResponse` 스키마를 계약 테스트에 반영.

## 10. 비범위 / 후속

- `DashboardSummaryResponse`의 `delta` 필드 채움 — 트렌드 시리즈로 직전 기간 대비 변화를
  계산해 채울 수 있다. 본 설계는 raw 시계열만 반환하며 delta 계산은 별도 후속이다.
- 현금 비중 추이 계열 — 포트폴리오 `cash_balance` 이력 테이블이 없어 파생 불가. 이력 저장
  기능이 생기면 추가할 수 있다.
- 단기 캐시 — 대시보드 화면에서 자주 폴링할 경우 단기 TTL 캐시 도입을 검토한다.
- FE 연동: FE adapter가 `DashboardTrendSeriesResponse`를 소비, 스파크라인 mock 제거
  (FE repo 별도 이슈).
