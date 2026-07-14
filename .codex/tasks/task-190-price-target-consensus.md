# Codex Handoff Task

## Source Issue

이슈 #295 — 목표 주가 컨센서스 계약. 설계:
`docs/designs/295-price-target-consensus.md` (먼저 전체를 읽는다).

## Task Summary

asset detail 계약에 목표 주가 컨센서스(평균·최고·최저·애널리스트 수)를
additive로 추가하고, yfinance 실수집으로 채운다. 현재 `target_price`는
yfinance 경로에서 항상 null이다.

## Goal

- `GET /assets/{id}/detail`이 `target_price_high`·`target_price_low`·
  `target_analyst_count`를 반환한다 (컨센서스 미제공 종목은 null).
- 실 프로바이더 경로에서 `target_price`가 `targetMeanPrice`로 채워진다.
- `target_upside_percent` 파생(평균 기준)과 기존 필드는 회귀 없음.

## Implementation Scope

- `app/adapters/market/base.py` — 컨센서스 결과 타입·provider 계약
  (설계 §4 — QuoteResult 확장 또는 분리 메서드 중 기존 fast_info/info
  접근 비용을 보고 결정).
- `app/adapters/market/yfinance.py` — `Ticker.info`의
  `targetMeanPrice`/`targetHighPrice`/`targetLowPrice`/
  `numberOfAnalystOpinions` 수집 + 1시간 TTL 캐시 (기존 quote 캐시
  구조 재사용).
- `app/adapters/market/mock.py` — 결정적 mock 값
  (high ≥ mean ≥ low 불변식).
- `app/domains/assets/service.py`·`schema.py` — additive 필드 전달.
- `docs/api/frontend-api-spec.md` — asset detail 계약 갱신.
- 테스트 — 계약 필드 타입·null 허용, mock 불변식, 미제공 종목 null
  경로, 기존 필드 회귀 없음.

## Out of Scope

- FE 표시 (FE #206에서 별도 처리)
- research-summary 등 다른 계약 변경
- 증권사별 개별 목표가 상세 (집계 값만)
- 마이그레이션·신규 테이블 (없어야 정상)

## Protected Files

없음.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Constraints

- 현재 브랜치(`feat/295-price-target-consensus`)에서 그대로 작업한다.
  새 브랜치 생성·checkout 금지.
- 커밋은 한국어 `type: 본문` 형식으로 작성한다.
- 설계 문서·이 태스크 문서·구현이 같은 PR에 함께 실린다.
