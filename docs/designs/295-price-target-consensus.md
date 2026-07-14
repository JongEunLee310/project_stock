# Design: 목표 주가 컨센서스 계약 — 평균·최고·최저 (#295)

- Status: Accepted
- Issue: #295
- 소비처: FE 리서치 헤더 (FE #206 — 평균 옆 최고·최저 병기)

## 1. 배경

현재 asset detail 계약에는 평균 목표가(`target_price`)와 상승 여력
(`target_upside_percent`)만 있습니다. yfinance quote provider는 이 필드를
채우지 않아 실 프로바이더 경로에서는 항상 null입니다 (mock만 값 제공).
이번 라운드에서 컨센서스(평균·최고·최저)를 실수집으로 채웁니다.

## 2. 데이터 소스

yfinance `Ticker.info`의 `targetMeanPrice` / `targetHighPrice` /
`targetLowPrice` / `numberOfAnalystOpinions`를 사용합니다.
(`analyst_price_targets` 속성은 내부적으로 같은 소스를 노출하므로,
기존 어댑터의 info 접근 관례에 맞는 쪽을 구현에서 선택합니다.)

- 미제공 종목(대다수 KOSDAQ 소형주 등)은 모든 필드 null.
- 조회 빈도가 낮고 갱신 주기도 느린 데이터이므로 기존 quote 캐시(TTL 60s)와
  분리된 더 긴 TTL 캐시(1시간)를 둡니다. 캐시 구조는 기존 quote 캐시 구현을
  재사용합니다.

## 3. 계약 (additive)

`GET /assets/{id}/detail` 응답에 추가:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `target_price_high` | `str \| null` | 최고 목표가 |
| `target_price_low` | `str \| null` | 최저 목표가 |
| `target_analyst_count` | `int \| null` | 집계 애널리스트 수 |

- 기존 `target_price`는 평균 목표가로 유지하되, 실 프로바이더에서
  `targetMeanPrice`로 채워지도록 전환한다.
- `target_upside_percent` 파생(평균 기준)은 유지.

## 4. 구현 스켈레톤

- `app/adapters/market/base.py` — `QuoteResult`에 컨센서스 필드 추가
  또는 별도 `PriceTargetResult` + provider 메서드 신설 (구현에서 기존
  fast_info/info 접근 비용을 보고 결정; info 호출이 quote 경로 성능에
  영향을 주면 분리한다).
- `app/adapters/market/yfinance.py` — 수집 구현 + 캐시.
- `app/adapters/market/mock.py` — 결정적 mock 값 (high ≥ mean ≥ low 불변식).
- `app/domains/assets/service.py`·`schema.py` — additive 필드 전달.
- `docs/api/frontend-api-spec.md` — 계약 갱신.

## 5. Test / Verification

- 계약 테스트: 신규 필드 타입·null 허용.
- mock 불변식: high ≥ mean ≥ low.
- 컨센서스 미제공 종목 → 세 필드 모두 null, 기존 필드 회귀 없음.
- `uv run ruff check .` / `uv run mypy .` / `uv run pytest`
