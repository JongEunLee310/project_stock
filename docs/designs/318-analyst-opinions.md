# Design: 기관별 목표주가·투자의견 계약 — analyst-opinions (#318)

- Status: Accepted
- Issue: #318
- 소비처: FE 리서치 헤더 목표주가 출처 표기 고도화 (후속 FE 이슈)

## 1. 배경

리서치 헤더의 목표주가 최저·최고 출처로 기관명(JP모건 등)을 표기하려면
기관별 귀속 데이터가 필요합니다. 현재 컨센서스 집계(#295)는 평균·최고·
최저·애널리스트 수만 제공합니다.

## 2. 데이터 소스 조사 (2026-07-15 실측)

| 소스 | 제공 범위 | 판단 |
| --- | --- | --- |
| yfinance `Ticker.upgrades_downgrades` | 기관명(Firm)·의견(To/FromGrade)·Action·**기관별 목표가(currentPriceTarget·priorPriceTarget)**·priceTargetAction·발표시각. AAPL 969행·NVDA 982행 실측 확인 | **채택** — 무료·기존 의존성·기관별 목표가 포함 |
| yfinance `analyst_price_targets` | 집계값만 (기존 #295와 동일) | 기관 귀속 불가 |
| TipRanks·MarketBeat | 기관별 목표가 제공 | 스크레이핑 약관 리스크 — 배제 |
| 한경컨센서스·네이버 리서치 | 국내 기관 리포트 | 별도 스크레이핑 구현 필요 — 이번 범위 제외, 후속 후보 |
| 유료 API (Refinitiv 등) | 전체 | 현 단계 배제 |

실측 참고: 한국 종목(005930.KS)은 `upgrades_downgrades`가 빈 프레임 —
국내 종목은 빈 목록으로 응답한다. `currentPriceTarget`이 0.0인 행은 목표가
부재를 의미하므로 null로 정규화한다.

## 3. 계약 (신설)

`GET /api/v1/assets/{asset_id}/analyst-opinions`

- Query: `limit: int = 20` (1–50, 최근 발표순)
- 응답 `data`:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `asset_id` | int | 자산 id |
| `opinions` | list | 최근 기관 의견 목록 (발표 시각 내림차순) |
| `opinions[].firm` | str | 기관명 |
| `opinions[].action` | str | 원문 코드 소문자 (`up`/`down`/`main`/`reit`/`init`) |
| `opinions[].to_grade` | str \| null | 변경 후 의견 |
| `opinions[].from_grade` | str \| null | 변경 전 의견 (빈 문자열은 null) |
| `opinions[].price_target` | str \| null | 기관 목표가 (Decimal 문자열, 0은 null) |
| `opinions[].prior_price_target` | str \| null | 직전 목표가 (동일 규칙) |
| `opinions[].price_target_action` | str \| null | 원문 라벨 (Raises/Maintains 등) |
| `opinions[].published_at` | UtcDatetime | 발표 시각 |

- 자산 없음 → 404 `ASSET_NOT_FOUND`. 미제공 종목(국내 등) → `opinions: []`.
- grade·action 문자열은 소스 원문 유지 (FE에서 라벨링) — enum 강제 시
  소스 변형에 취약해 문자열 통과를 선택.

## 4. 구현 스켈레톤

- `app/adapters/market/base.py` — `AnalystOpinionResult` dataclass +
  `MarketDataProvider.get_analyst_opinions(symbol, limit)` (기본 구현 빈
  목록 — 기존 `get_price_targets` 패턴).
- `app/adapters/market/yfinance.py` — `upgrades_downgrades` 수집·정규화
  (0.0→null, NaN 방어, 최근 limit 절단).
- `app/adapters/market/cache.py` — 1시간 TTL 캐시 (price-target 캐시
  패턴 재사용).
- `app/adapters/market/mock.py` — 결정적 mock (AAPL 계열 심볼에 기관명·
  목표가 포함 3건 내외, 그 외 빈 목록 — 컨센서스 mock과 값 정합 유지).
- `app/domains/assets/` 또는 신규 소도메인 — projection·service·endpoint.
  기존 asset 파생 엔드포인트(earnings-summary 등) 등록 관례를 따른다.
- `docs/api/frontend-api-spec.md` — 계약 추가.

## 5. Test / Verification

- 계약 테스트: 응답 형태·limit 검증·404.
- 정규화: 0.0 목표가 → null, 빈 from_grade → null, 발표순 정렬.
- mock 결정성·빈 목록 경로 (국내 종목).
- `uv run ruff check .` / `uv run mypy .` / `uv run pytest`

## 6. Out of Scope

- FE 표시 (후속 FE 이슈 — 목표주가 최저·최고의 기관 귀속 표기)
- 국내 기관 리포트 소스 (한경컨센서스 등) — 후속 후보
- DB 영속화 (on-demand + 캐시로 충분, 필요 시 후속)
