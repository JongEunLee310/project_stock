# 262 — 시그널 집중도 불릿 수치 포맷 정규화

Status: Approved (PR #261 리뷰 S1 후속, 로드맵 4단계 FE 연결 전 선행)
Designer: Claude Code (Fable 5)
Implementer: Codex (gpt-5.5, reasoning effort medium)

## Problem

포트폴리오 집중도 시그널의 `key_points` 불릿이 원시 Decimal을 그대로 문자열에
삽입합니다.

- `position.weight`는 `_calculate_weight`의 나눗셈 원값(quantize 없음)이라
  "현재 비중 0.6521739130434782608695652174이 임계치 0.6000를 초과했습니다"로
  렌더링됩니다.
- `market_value`는 "586.920000000000"처럼 후행 0이 남습니다.
- f-string 고정 조사("{weight}이", "{threshold}를")가 수치에 따라 어긋납니다.

불릿은 시그널 카드에 그대로 표시되는 사용자 대면 문장이므로, 스캔 가능한
근거라는 기능 목적에 맞게 포맷을 정규화합니다.

## Verified Facts

- 조립 위치는 `app/domains/portfolios/service.py` `check_concentration`의
  `SignalCreate(key_points=[...])` 한 곳입니다 (`service.py:160-166`).
- `evidence`는 동일 수치를 원값 문자열로 별도 보존하므로(`weight`,
  `threshold`, `market_value` 키) 불릿 포맷 변경으로 정밀도 정보가 유실되지
  않습니다.
- 나머지 생성 경로 2곳(HighImpactNewsRule·ThesisConflictRule)의 불릿은 수치
  삽입이 없어 대상이 아닙니다.
- `Decimal.normalize()` 단독 사용은 정수 배수에서 지수 표기(`1E+3`)가 나올 수
  있어 문자열 변환 방식 선택이 필요합니다.

## Decisions

- **백분율 포맷** — 비중·임계치는 백분율 소수 1자리로 표기합니다.
- **괄호 배치** — 수치를 문장 뒤 괄호로 빼서 조사 불일치를 함께 해소합니다.
  - 불릿 1: `현재 비중이 임계치를 초과했습니다 (65.2% > 60.0%)`
  - 불릿 2: `평가금액은 586.92입니다.`
- **금액 정규화** — 후행 0 제거, 지수 표기 금지 (정수 배수 입력에서도
  `1000` 형태 유지).
- **범위 불변** — reason·evidence·응답 계약·다른 생성 경로는 변경하지
  않습니다. 통화 기호·단위 표기는 범위 밖입니다(자산 통화 정보가 이 경로에
  없음).

## Implementation Sketch

- `app/domains/portfolios/service.py`
  - `_format_percent(value: Decimal) -> str` — 비율(0~1)을 백분율 소수 1자리
    문자열로 변환 (`"65.2%"`).
  - `_format_amount(value: Decimal) -> str` — 후행 0 제거·지수 표기 없는
    문자열로 변환 (`"586.92"`, `"1000"`).
  - `check_concentration` 불릿 조립을 위 헬퍼 기반 문장으로 교체.

## Out of Scope

- LLM 기반 불릿 생성, reason/evidence 계약 변경
- HighImpactNewsRule·ThesisConflictRule 불릿 (수치 삽입 없음)
- 통화 기호·천 단위 구분자 표기
- FE 연결 (로드맵 4단계)

## Test Plan

- `tests/test_portfolios.py` 기존 불릿 단언을 새 포맷 리터럴로 갱신
  (백분율·괄호 형식 포함).
- 포맷 헬퍼 경계: 후행 0 입력(`586.920000000000` → `586.92`), 정수 배수
  입력에서 지수 표기 미발생, 비율 반올림(소수 1자리).
- 회귀: ruff / mypy / pytest(NEWS_PROVIDER=mock) 전체 통과.
