# Codex Handoff Task

## Source

PR #283 로컬 리뷰 후속 조치. 리뷰 기록: `docs/reviews/pr-283.md` (B1 절을
먼저 읽는다).

## Task Summary

**B1 — 벤치마크 파생 쿼리에 시간 범위 하한을 도입한다.** 현재
`BenchmarkService.get_comparison`이 세 시리즈 모두
`get_daily_closes(..., start=None)`으로 전체 이력을 적재한다. #281(5년
히스토리) 적재 후 요청당 수천 행이 메모리로 올라가므로 머지 전에
바운드를 건다. `datetime.now()` 의존은 계속 금지한다 (결정성 유지).

수정 방식 (2단계 조회):

1. `app/domains/prices/repository.py`에
   `get_latest_close_date(symbol, market) -> date | None` 추가
   (interval `1d`, `max(timestamp)` — 유니크 인덱스 활용).
2. `app/domains/benchmark/service.py`:
   - 세 시리즈의 latest date를 먼저 조회한다. 하나라도 None이면 기존
     폴백(세 시리즈 `points: []`)으로 즉시 반환.
   - `start = min(세 latest) - range 델타 - 여유폭 14일`로
     `get_daily_closes(..., start=start)` 호출. 여유폭은 기준일(공통
     거래일 최댓값)이 min(latest)보다 다소 이전일 수 있는 경우(휴장일
     어긋남)를 흡수한다 — 이 WHY를 짧은 주석으로 남긴다.
   - 이후 파생 로직(기준일=공통 거래일 최댓값, 교집합, 누적 수익률)은
     불변.

## Test

- `tests/test_benchmark.py`에 추가: start 하한 밖의 오래된 bar가
  파생에 포함되지 않음을 검증하는 케이스 1개 (범위 밖 bar를 픽스처에
  넣고 결과 불변 단언). 기존 테스트는 결과 불변이어야 한다.

## Out of Scope

- S1(QQQ 자산 중복 쿼리)·S2(`_common_dates` 빈 dict)·S3·Q1·Q2 —
  비차단, 손대지 않는다.
- schema·계약·다른 도메인 불변.

## Rules

- 현재 브랜치 `feat/278-benchmark-real-derivation`에서 그대로 작업한다.
- 커밋은 1개로 만든다. push는 하지 않는다.
- 커밋 메시지는 한국어 `type: 본문` 형식으로 작성한다.
- `docs/designs/266-research-queue-contract.md`(추적되지 않는 파일)는
  건드리지 않는다.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `NEWS_PROVIDER=mock uv run pytest`
