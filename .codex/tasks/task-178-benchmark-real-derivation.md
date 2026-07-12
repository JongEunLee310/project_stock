# Codex Handoff Task

## Source

이슈 #278 — 벤치마크 실수집·실파생. 설계:
`docs/designs/278-benchmark-real-derivation.md` (먼저 전체를 읽는다).

## Task Summary

`benchmark-comparison`을 mock에서 `stock_price_bars` 실파생으로
전환한다. **API 계약(schema.py·응답 구조·enum·시리즈 고정 순서)은
변경하지 않는다.**

1. `app/domains/prices/universe.py` — `_benchmark_targets()` 추가:
   QQQ(NASDAQ) + 유니버스 자산 섹터에 매핑되는 섹터 ETF + 매핑 불가
   섹터 존재 시 SPY(NYSE). 중복 제거는 기존 dict 방식 재사용.
2. `app/domains/benchmark/sector_map.py` 신규 — 섹터→ETF 상수 매핑
   11종(설계 문서 표 그대로)과 `resolve_sector_etf` (매핑 불가·null →
   SPY / `S&P 500`).
3. `app/domains/prices/repository.py` — `get_daily_closes(symbol,
   market, start)` 조회 헬퍼 추가 (interval `1d`, 오름차순).
4. `app/domains/benchmark/service.py` — mock 템플릿 제거, 실파생 교체:
   기준일 = 세 시리즈 공통 거래일 최댓값(`datetime.now()` 사용 금지),
   시작일 = 기준일 - range 델타(1M 31 / 3M 92 / 6M 183 / 1Y 366일,
   `dict[BenchmarkRange, timedelta]`), 날짜 축 = 공통 거래일 교집합
   오름차순, `return_percent` = 첫 공통일 대비 누적 수익률 %
   quantize 0.01(첫 포인트 0). 데이터 부족 시 세 시리즈 모두
   `points: []` (구조·순서·label 유지). label: ASSET=asset.symbol,
   INDEX=`NASDAQ 100`, SECTOR_ETF=ETF 심볼(폴백 `S&P 500`).

## Test

- `tests/test_benchmark.py` 재작성 — 픽스처 bars 기반. 설계 문서 Test
  절을 그대로 따른다: 누적 수익률 손계산 기대값(주석으로 출처 명시),
  공통 날짜 교집합, range 필터, 폴백(빈 points·SPY), 기존 계약
  검증(3시리즈 순서·422·404·401·기본 3M) 유지, id 리터럴 단언 금지.
- `tests/test_price_ingestion.py` — 벤치마크 타깃 포함·중복 제거 검증
  추가.
- `tests/test_api_contract.py` — 스냅샷 형태 유지, 픽스처 필요 시 갱신.

## Out of Scope

- `app/domains/benchmark/schema.py`·alembic·yfinance 어댑터·다른 도메인
  불변. #279·#280·#281 범위 침범 금지.
- `docs/designs/266-research-queue-contract.md`(추적되지 않는 파일)는
  건드리지 않는다.

## Rules

- 현재 브랜치 `feat/278-benchmark-real-derivation`에서 그대로 작업한다.
  새 브랜치를 만들지 않는다.
- 커밋은 1개로 만든다. push는 하지 않는다.
- 커밋 메시지는 한국어 `type: 본문` 형식으로 작성한다.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `NEWS_PROVIDER=mock uv run pytest`
