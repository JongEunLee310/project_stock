# Codex Handoff Task

## Source Issue

GitHub issue #262 — 시그널 집중도 불릿의 수치 포맷 정규화 (PR #261 S1 후속).
설계: `docs/designs/262-concentration-bullet-format.md` (반드시 먼저 읽는다).

## Task Summary

포트폴리오 집중도 시그널의 `key_points` 불릿에 원시 Decimal이 그대로
노출되는 문제를 고친다. 비중·임계치는 백분율(소수 1자리)로, 평가금액은 후행
0을 제거해 조립하고, 수치를 문장 뒤 괄호로 배치해 조사 불일치를 해소한다.

## Goal

- 불릿 1: `현재 비중이 임계치를 초과했습니다 (65.2% > 60.0%)`
- 불릿 2: `평가금액은 586.92입니다.`
- 금액 포맷은 후행 0 제거·지수 표기 금지(정수 배수 입력도 `1000` 형태).
- 3종 검증 통과.

## Background

- 조립 위치는 `app/domains/portfolios/service.py` `check_concentration`의
  `SignalCreate(key_points=[...])` 한 곳뿐이다 (현재 160행 부근).
- `position.weight`는 `_calculate_weight`의 나눗셈 원값(quantize 없음)이라
  28자리 Decimal이 그대로 문자열에 들어간다. `market_value`는
  `586.920000000000`처럼 후행 0이 남는다.
- `evidence`는 동일 수치를 원값 문자열로 보존하므로 불릿만 바꾸면 된다.
- `Decimal.normalize()` 단독 사용은 정수 배수에서 `1E+3` 지수 표기가 나올 수
  있으니 주의한다 (예: `f"{value.normalize():f}"`는 지수 표기를 피한다).

## Implementation Scope

- `app/domains/portfolios/service.py`
  - `_format_percent(value: Decimal) -> str` — 비율(0~1)을 백분율 소수 1자리
    문자열로 (`"65.2%"`).
  - `_format_amount(value: Decimal) -> str` — 후행 0 제거·지수 표기 없는
    문자열로 (`"586.92"`, `"1000"`).
  - `check_concentration`의 불릿 2개를 Goal의 문장으로 교체.
- `tests/test_portfolios.py` — 기존 불릿 단언을 새 포맷 리터럴로 갱신, 포맷
  경계 케이스 추가 (후행 0 제거, 정수 배수 지수 표기 미발생, 소수 1자리
  반올림).

## Out of Scope

- reason·evidence·응답 계약 변경.
- HighImpactNewsRule·ThesisConflictRule 불릿 (수치 삽입 없음).
- 통화 기호·천 단위 구분자.
- migration (스키마 변경 없음).
- FE.

## Protected Files

- `app/domains/signals/types.py` — 변경 금지.

## Rules

- 현재 브랜치 `feat/262-concentration-bullet-format`에서 그대로 작업한다. 새
  브랜치를 만들지 않는다.
- 커밋은 1개로 만든다. push는 하지 않는다.
- 필요하지 않은 추상화를 추가하지 않는다.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `NEWS_PROVIDER=mock uv run pytest`

## Acceptance Criteria

- 집중도 시그널의 불릿이 Goal의 두 문장 형식으로 생성된다.
- 비중 65.21739...% 입력이 `65.2%`로, `0.6000` 임계치가 `60.0%`로 표기된다.
- `586.920000000000` 평가금액이 `586.92`로 표기되고, 정수 배수 입력에서 지수
  표기가 나오지 않는다.
- 기존 테스트 전체와 신규 경계 테스트가 통과한다.
