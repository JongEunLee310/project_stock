# BE 설계: 뉴스 인텔리전스 파이프라인 5 — 수급·일정 공급원(investor_flows·market_events) — 이슈 #401

상태: **설계 확정 — 공급원 부재 확인** — 2026-07-24. 트래킹 #391의 5단계, 에픽 #307 후속.
다른 단계와 독립적으로 진행 가능하다.

이 문서는 `investor_flows`·`market_events`의 공급원 현황을 확인하고, 확보 옵션과 계약 요건을
스켈레톤 수준으로 정리한다. 이번 단계는 **설계 문서만** 산출하며 코드 변경이 없다(사용자
결정, 2026-07-24). 실 공급원 어댑터 착수는 후속 #411이다.

## 1. 현황 — 공급원 부재

`investor_flows`·`market_events`를 채울 **실제 공급원이 현재 존재하지 않는다.**

- 기존 시장 어댑터(`app/adapters/market`)는 quote·price target·analyst opinion·index quote·
  exchange rate만 제공한다. 투자자 수급·실적 캘린더 provider가 없다.
- 두 테이블의 유일한 기록 경로는 `seed.py`다(각 1건). 화면은 시드 또는 빈 상태를 보여준다.

이 단계는 앞 네 단계(#397~#400)와 성격이 다르다. 앞은 파이프라인 입력(문서·이벤트·토픽)이
존재해 골격 배관을 돌릴 수 있었으나, 여기서는 **외부 공급원 자체가 없어 골격으로라도 생산할
데이터가 없다.** 값을 지어내는 것은 원칙 위반이므로, 이번 단계는 공급원 옵션을 확정하고
availability 정직성 원칙을 문서화하는 데 그친다.

## 2. `investor_flows` — 투자자 수급

### 모델·계약 현황

- 모델: `market`·`topic_id`(nullable)·`investor_type`·`net_value`(Numeric)·`direction`·
  `window`·`as_of`·`source_kind`.
- 응답 계약 `InvestorFlowsResponse`는 이미 `availability: InvestorFlowAvailability`
  (`available: bool`·`fallback: str | None`)를 담는다. 데이터가 없으면 `available=False`로
  정직하게 표기하는 계약이 2차(#368)에서 완성돼 있다.

### 공급원 옵션

| 후보 | 데이터 | 계약 요건 |
|---|---|---|
| KRX 투자자별 거래실적 | 외국인·기관·개인 순매수 | 인증·이용약관, rate limit, 비용 확인 필요 |
| 증권사 오픈 API | 투자자 유형별 수급 | 계좌·앱키 발급, 호출 한도 |

국내 시장 수급이 주 대상이라 공급원이 국내 거래소·증권사에 한정된다. 무료·무인증 경로가
마땅치 않아 **외부 계약이 실착수의 선행**이다.

## 3. `market_events` — 실적·이벤트 캘린더

### 모델·계약 현황

- 모델: `scheduled_at`·`event_kind`·`title`·`symbol`(nullable)·`market`(nullable)·
  `importance_score`. 토픽 연결은 `market_event_topics`(`market_event_id`·`topic_id`,
  UniqueConstraint).
- 응답 계약 `CalendarItem`은 availability 필드 없이 빈 리스트로 부재를 표기한다.

### 공급원 옵션

| 후보 | 데이터 | 계약 요건 |
|---|---|---|
| DART 공시 일정 | 실적 발표·주요 공시 예정 | OpenDART 인증키, 국내 한정 |
| yfinance earnings 일정 | 실적 발표일(부분) | 무인증이나 커버리지·정확도 확인 필요 |

`market_events`는 `investor_flows`보다 무료 경로(yfinance earnings, OpenDART)가 있어 상대적으로
확보가 쉽다. 다만 커버리지·정확도 검증이 선행이다.

### `market_event_topics` 연결

일정↔토픽 연결은 실 데이터 확보 후 연결 규칙을 정한다. 현재 골격 토픽은 `event_type` 기준
집계라, 일정을 토픽에 잇는 의미 있는 규칙은 실 클러스터링(#407)·실 캘린더(#411) 이후가 적기다.

## 4. availability 정직성 원칙

공급원이 없는 동안 지켜야 할 원칙을 명시한다.

- `investor_flows` — `available=False`, `fallback`에 상태를 담는다. 빈 값을 `0`으로 채우지
  않는다. 이 계약은 이미 완비돼 있으므로, 실 공급원이 붙기 전까지 정직한 빈 상태가 유지되는
  것이 옳은 동작이다.
- `market_events` — 빈 리스트로 표기한다. 없는 일정을 지어내지 않는다.

## 5. 후속 — 실 공급원 어댑터(#411)

실 공급원 어댑터는 후속 **#411**에서 다룬다. 두 소스는 성격이 달라 각각 별도 착수할 수 있다.

- `investor_flows` 어댑터 — KRX·증권사 수급. 외부 계약·인증 선행.
- `market_events` 어댑터 — DART·yfinance 실적 일정. 커버리지 검증 선행.
- `market_event_topics` 연결 규칙 — 실 데이터 확보 후.

## 6. ADR·실패 기록 판단

- ADR: 이번 단계는 문서만이라 **불요**. 다만 #411에서 새 외부 provider(수급·캘린더)를 추가할
  때는 ADR-007(provider abstraction) 계열에 따라 어댑터 인터페이스 설계 시 ADR 필요성을
  검토한다. 기존 `MarketDataProvider` 계열과 나란한 provider 추상화가 될 가능성이 높다.
- 실패 기록: 해당 없음. 공급원 부재는 실패한 접근이 아니라 외부 데이터 확보의 선행 조건이
  아직 충족되지 않은 상태다.
