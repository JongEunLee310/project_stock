# Design — Issue 271: 데이터 신선도·분석 커버리지·반대 관점 계약

리서치 상세 2차에 필요한 계약 중 이슈 #271의 세 항목(데이터 신선도, 분석
커버리지, 반대 관점)을 다룹니다. 신선도와 커버리지는 같은 축 단위 정보라서
단일 엔드포인트로 합치고, 반대 관점은 기존 research-summary 응답을
확장합니다.

## Scope Decision

이슈 #271의 네 항목 중 **벤치마크 비교 시계열은 이 PR에서 제외**합니다.
지수·섹터 ETF 가격의 실수집(수집 유니버스 확장)이 필요해 규모가 다르고,
밸류에이션·실적 계약(#270)과 함께 데이터 소스 검토가 묶이는 것이
자연스럽기 때문입니다. 후속 라운드로 분리합니다.

이번 PR의 원칙: 신선도·커버리지는 **기존 수집 데이터에서 실제로
파생**합니다 (mock 아님). 반대 관점은 #267 선례를 따라 결정적 mock
템플릿으로 시작합니다.

## Endpoint 1 — `GET /assets/{asset_id}/research-coverage`

데이터 축별 확보 상태와 마지막 수집 시각을 반환합니다. 핵심 원칙(AI 판단 ≠
리서치 상태) 중 "분석 완성도 = 데이터 확보율"의 근거 데이터입니다.

응답: `ResearchCoverageResponse`

- `asset_id: int`
- `axes: list[CoverageAxis]` — 항상 5개, 고정 순서 (NEWS, PRICE,
  EARNINGS, VALUATION, DISCLOSURE)

`CoverageAxis`:

- `axis: str` — enum 5값: `NEWS` / `PRICE` / `EARNINGS` / `VALUATION` /
  `DISCLOSURE`
- `status: str` — `COLLECTED` / `NOT_COLLECTED`
- `last_updated_at: UtcDatetime | None` — 해당 축 데이터가 마지막으로
  확보·갱신된 시각 (`updated_at` 최댓값). 미확보면 null.
- `item_count: int` — 확보된 데이터 건수. 미확보면 0.

시맨틱 (PR #275 리뷰 Q1로 확정): `created_at`은 행의 최초 삽입 시각이라
"마지막 수집 시각"과 어긋납니다 — 뉴스는 URL 중복 스킵으로 새 기사가
없으면 갱신되지 않고, 가격은 upsert가 기존 bar를 in-place 갱신해
`created_at`이 변하지 않습니다. 따라서 이 필드는 "마지막으로 데이터가
갱신된 시각"으로 정의하고 `updated_at`(onupdate 반영)에서 파생합니다.
"수집 실행 시각"(파이프라인 상태)은 `job_runs` 기반의 별도 관심사로,
실수집 라운드에서 필요 시 다룹니다.

축별 파생 방법:

- `NEWS` — `news_items`에서 `asset_id` 일치 행. `max(updated_at)`, count.
- `PRICE` — `stock_price_bars`에서 asset의 `symbol`+`market` 일치 행.
  `max(updated_at)`, count.
- `EARNINGS` / `VALUATION` / `DISCLOSURE` — 수집 파이프라인이 아직 없어
  항상 `NOT_COLLECTED`·null·0. (#270 밸류에이션·실적 계약, 공시 실수집이
  도입되면 그때 파생 로직을 추가합니다.)

동작:

- 인증 필수. 자산 미존재 404 `ASSET_NOT_FOUND` (기존 라우트와 동일).
- 커버리지 비율(예: 2/5)은 FE에서 파생하므로 BE는 축 목록만 반환합니다.
- BE #266(리서치 큐)의 분석 완성도와 정합: 큐 계약이 재개되면 같은 파생
  로직을 공유합니다.

## Endpoint 2 — 반대 관점: research-summary 확장

`ResearchSummaryResponse`에 필드 1개를 추가합니다 (additive, 기존 필드
불변).

- `counter_view: list[str] = Field(default_factory=list)` — 현재 stance에
  반대되는 근거 불릿 2~3개. AI 확증 편향 방지 목적.

서비스는 #267과 같은 결정적 mock 템플릿 로테이션(`asset.id % N`)으로
생성합니다. 내용은 점검 유도형 한국어 문장이며, 템플릿의 stance 방향과
반대되는 논거여야 합니다 (예: 긍정 스탠스 템플릿에는 밸류에이션 부담·경쟁
심화 같은 반대 논거).

## Files

**신규**

- `app/domains/research_coverage/__init__.py`
- `app/domains/research_coverage/schema.py` — `CoverageAxis`,
  `ResearchCoverageResponse`
- `app/domains/research_coverage/service.py` — `ResearchCoverageService`
  - `get_coverage(asset_id: int) -> ResearchCoverageResponse` — 자산 존재
    검증 후 축별 파생 쿼리 실행
- `tests/test_research_coverage.py`

**갱신**

- `app/api/v1/endpoints/assets.py` — `GET /{asset_id}/research-coverage`
  라우트 1개 추가
- `app/domains/research_summary/schema.py` — `counter_view` 필드 추가
- `app/domains/research_summary/service.py` — 템플릿에 counter_view 불릿
  추가
- `tests/test_assets.py` (research-summary 기존 테스트 위치) —
  counter_view 검증 추가. 계약 스냅샷이 있으면 `tests/test_api_contract.py`
  도 갱신.

**변경 불가**

- alembic (신규 테이블·컬럼 없음), 다른 도메인, 수집 파이프라인.

## Test

- research-coverage: 뉴스·가격 픽스처가 있는 자산은 NEWS·PRICE가
  `COLLECTED` + last_collected_at·item_count 채워짐, 픽스처 없는 자산은
  5축 전부 `NOT_COLLECTED`. 축 5개·순서 고정. 404·401.
- counter_view: 응답에 불릿 존재(비어 있지 않음), 같은 asset_id 반복 호출
  결정성, 기존 필드 회귀 없음.
- id 리터럴 단언 금지 (PR #273 B1 선례 — StaticPool autoincrement 순서
  의존).

## Out of Scope

- 벤치마크 비교 시계열 (후속 분리 — #270과 함께 데이터 소스 검토).
- 공시·실적·밸류에이션 실수집 및 해당 축의 파생 로직.
- FE 표시 (#148/#150).

## Open Questions

- 없음.
