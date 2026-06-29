# BE 확장: portfolio summary 일간 변동(day change)

상태: **계약 확정(Frozen)** — 2026-06-29(Opus). FE Portfolio 화면 dayChange mock 제거 페어.
FE Portfolio 화면 상단의 일간 변동 금액/비율이 `mockPortfolio.dayChangeValue/dayChangePercent`로 남아 있다.
summary 계산이 이미 시세(`get_market_provider().get_quote`)를 조회하므로, 시세의 `change_percent`를
활용해 일간 변동을 BE에서 산출한다. **구현은 §3 계약 확정을 정본으로 따른다.**

## 배경

`PortfolioSummaryResponse`는 `total_value`까지만 제공하고 일간 변동(day change)이 없어
FE가 상단 카드 값을 mock으로 유지하고 있다. `_calculate_weights`는 이미 `get_quote`로 현재가를
가져오지만 `change_percent`는 버린다. 동일 quote의 `change_percent`를 함께 사용하면 추가 외부 호출
없이 일간 변동을 계산할 수 있다.

`expand` 패턴(signals/alert_candidates)은 **추가 비용이 드는** asset 정보를 옵션화하기 위한 것이었다.
day change는 summary 계산 경로에 이미 있는 quote만 재사용하므로 추가 호출이 없어 **항상 포함**한다
(expand 불필요). 새 필드 추가일 뿐이라 마이그레이션·인증 변경·신규 결정 없음 → ADR 불요.

## 1. 변경 범위

| Method · Path | 변경 |
| --- | --- |
| `GET /api/v1/portfolios/{id}/summary` | 응답에 `day_change_value`, `day_change_percent` 필드 추가 |
| `GET /api/v1/portfolios/{id}/check` | `summary`가 위 필드를 포함(파생 — 별도 작업 없음) |

엔드포인트 시그니처·쿼리·인증 변경 없음. 신규 엔드포인트 없음.

## 2. FE 매핑

FE는 `day_change_value`/`day_change_percent`를 Portfolio 상단 카드에 바인딩한다(현재 mock).
`aiBriefing`·`riskExposures` mock은 이번 범위 밖으로 그대로 유지한다(후속 AI Briefing 작업).

## 3. 계약 확정 (2026-06-29, Opus — 정본)

와이어 컨벤션은 기존 portfolio summary와 동일: snake_case, 금액·비율=Decimal **문자열**(C5).

### 3.1 응답 스키마

`PortfolioSummaryResponse`에 두 필드 추가:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `day_change_value` | `Decimal` | 포지션 일간 변동 금액의 합(현금 변동 0) |
| `day_change_percent` | `Decimal` | `day_change_value / 전일 평가액 * 100`. 전일 평가액 0이면 `0` |

기존 필드는 변경 없음. 추가 필드뿐이라 FE는 미반영 시 무시 가능(하위호환).

### 3.2 계산 규칙

`_calculate_weights`(또는 인접 헬퍼)에서 quote의 `price`와 `change_percent`를 함께 사용한다.

- 포지션별 현재 평가액 `market_value = quantity * price`(기존과 동일).
- 포지션별 전일 평가액 `prev_value = market_value / (1 + change_percent/100)`.
  - `change_percent`는 퍼센트 단위(예: `1.26` = +1.26%).
  - `1 + change_percent/100 == 0`(이론상 -100%)이거나 `price == 0`(quote 없음)이면 해당 포지션 기여 0.
- `day_change_value = Σ (market_value - prev_value)`.
- 전일 총평가액 `prev_total_value = total_value - day_change_value`(현금은 일간 변동 없음).
- `day_change_percent = day_change_value / prev_total_value * 100`, `prev_total_value == 0`이면 `0`.

quote 누락 포지션은 `price=0`으로 이미 처리되며 day change 기여 0이 된다(기존 `_get_quotes_by_symbol`
fallback과 일관).

### 3.3 데이터 경로

`_get_quotes_by_symbol`이 현재 `{symbol: price}`만 반환한다. `change_percent`도 필요하므로
`{symbol: QuoteResult}`(또는 `{symbol: (price, change_percent)}`)로 확장하고 기존 price 사용처는
그대로 동작하도록 맞춘다. 외부 호출 횟수는 변하지 않는다(동일 `get_quote` 1회).

## 4. 범위 밖

- `riskExposures`(지역/스타일 정성 카드), `aiBriefing` — 후속 AI Briefing 작업.
- 포지션별 일간 변동률(`dailyChangePercent`) 노출 — 이번엔 포트폴리오 합계만. 필요 시 후속.
- 전일 종가 스냅샷 영속화 — 시세 `change_percent` 파생으로 충분, 신규 테이블 없음.
