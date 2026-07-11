# Codex Handoff Task

## Source

이슈 #270 + #271 잔여(벤치마크 비교 시계열). 설계:
`docs/designs/270-valuation-earnings-benchmark.md` (먼저 전체를 읽는다).

## Task Summary

리서치 상세 2차 계약 세 개를 결정적 mock으로 추가한다. 세 엔드포인트
모두 인증 필수·자산 미존재 404 `ASSET_NOT_FOUND`이며, 구조는
`app/domains/research_coverage/`·`app/domains/catalysts/` 선례를 따른다.

1. `GET /assets/{asset_id}/valuation-metrics` — 신규 도메인
   `app/domains/valuation/`. `ValuationMetricsResponse`(profile ·
   highlighted_metrics · metrics 7개 고정 순서). DEFICIT 템플릿에서
   PER류 `value`가 null이어야 한다.
2. `GET /assets/{asset_id}/earnings-summary` — 신규 도메인
   `app/domains/earnings/`. `EarningsSummaryResponse`(quarters 4개
   오름차순 · guidance · segments). surprise 양·음 혼재, estimate null
   케이스 포함.
3. `GET /assets/{asset_id}/benchmark-comparison?range=` — 신규 도메인
   `app/domains/benchmark/`. range enum `1M/3M/6M/1Y` 기본 `3M`, 허용
   외 422. 시리즈 3개(ASSET·INDEX·SECTOR_ETF) 고정 순서, 세 시리즈
   날짜 축 일치, `return_percent`는 기간 시작 대비 누적 수익률(첫
   포인트 0). 결정적 생성(asset.id·range 시드).

필드 정의·enum 값·mock 규칙은 설계 문서를 따른다. mock은
research_summary 선례의 결정적 템플릿 로테이션(`asset.id % N`)을
사용한다. 경계·파생 뷰 Pydantic 타입 이름에 'DTO'를 쓰지 않는다
(projection 관례).

라우트는 `app/api/v1/endpoints/assets.py`에 기존 research-coverage ·
catalysts 패턴으로 추가한다.

## Test

- 신규: `tests/test_valuation.py` · `tests/test_earnings.py` ·
  `tests/test_benchmark.py`. 케이스는 설계 문서 Test 절을 따른다
  (결정성·404·401·고정 순서·null 계약·range 422·날짜 축 일치).
- `tests/test_api_contract.py` 계약 스냅샷 추가.
- 템플릿 전수 순회는 `len(_TEMPLATES)` 연동. id 리터럴 단언 금지
  (404 테스트는 `existing_asset_id + 1` 패턴).

## Out of Scope

- 실수집·실파생(yfinance 어댑터·수집 유니버스 확장), alembic, 수집
  파이프라인, 다른 도메인.
- `docs/designs/266-research-queue-contract.md`(추적되지 않는 파일)는
  건드리지 않는다.

## Rules

- 현재 브랜치 `feat/270-valuation-earnings-contract`에서 그대로
  작업한다. 새 브랜치를 만들지 않는다.
- 커밋은 1개로 만든다. push는 하지 않는다.
- 커밋 메시지는 한국어 `type: 본문` 형식으로 작성한다.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `NEWS_PROVIDER=mock uv run pytest`
