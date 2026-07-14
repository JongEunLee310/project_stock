# Codex Handoff Task

## Source Issue

이슈 #316 — intraday 가격 간격 15m → 5m 전환. 이슈 본문을 먼저 읽는다.

## Task Summary

1D 차트 해상도 개선을 위해 intraday 봉 간격 표준을 15분에서 5분으로
전환한다. 리서치 가격 차트(`range=1D`)와 워치리스트 스파크라인이 이
간격을 공유한다.

## Goal

- `GET /stocks/{symbol}/prices?range=1D` 응답의 `interval`이 `5m`이고
  봉 수가 5분 기준(정규장 78개 근사)으로 반환된다.
- 워치리스트 스파크라인 경로가 5m 기준으로 동작하며 회귀가 없다.

## Implementation Scope

- `app/domains/prices/service.py` — `_RANGE_INTERVALS["1D"]`를 `"5m"`,
  `_RANGE_COUNTS["1D"]`를 78로 변경.
- `app/adapters/market/yfinance.py` — `get_intraday_bars`의
  `interval="15m"`·`_bars_from_frame(interval=...)`을 `5m`로 변경.
- `app/adapters/market/mock.py` — intraday mock 생성 간격·interval
  문자열 동기화.
- 워치리스트 스파크라인 경로의 15m 참조 동기화 (grep으로 잔존 참조
  전수 확인 — `"15m"` 리터럴이 코드·테스트에 남지 않아야 한다.
  이력 문서 docs/reviews/는 제외).
- `tests/` — 관련 테스트의 interval·봉 수 기대값 갱신.
- 문서 — `docs/designs/price-series-api.md`의 1D→15m 표기,
  `docs/designs/239-watchlist-1d-intraday.md`, `docs/api/frontend-api-spec.md`
  중 15m 언급을 5m로 갱신.

## Out of Scope

- interval 파라미터 계약 구조 변경 (파생 위임 유지)
- 기존 15m 저장 행 마이그레이션·삭제 (interval 필터로 자연 분리)
- FE 수정 (별도 repo)

## Protected Files

없음.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Constraints

- 현재 브랜치(`feat/316-intraday-5m`)에서 그대로 작업한다. 새 브랜치
  생성·checkout 금지.
- 커밋은 한국어 `type: 본문` 형식으로 작성한다.
- 이 태스크 문서와 구현이 같은 PR에 함께 실린다.
