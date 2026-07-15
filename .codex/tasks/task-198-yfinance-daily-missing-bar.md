# Codex Handoff Task

## Source Issue

이슈 #324 — yfinance daily 봉 결측값으로 price series 전체 502. `gh issue view 324`로
원인·범위를 먼저 읽는다.

## Task Summary

`app/adapters/market/yfinance.py`의 `_bars_from_frame`이 daily(`1d`) 프레임의 한 봉에라도
OHLC 결측(NaN/None)이 있으면 `_to_decimal`이 `ValueError`를 던져 `get_daily_bars` 전체가
실패하고 502가 된다. 개별 결측 봉을 건너뛰고 유효한 봉만 반환하도록 바꾼다.

## Goal

- 1M·3M·6M·1Y 차트(daily)가 결측 봉이 섞여 있어도 200으로 응답한다.
- 유효한(OHLC·adjusted_close가 모두 온전한) 봉만 반환하고, 결측 봉은 조용히 skip한다.
- 모든 봉이 결측이면 빈 리스트를 반환해 기존 404 `PRICE_SERIES_NOT_FOUND` 경로를 그대로 탄다.
- intraday(`5m`/`30m`)·weekly(`1wk`) 경로는 동작 변화가 없다.

## Background

`PriceBarResult`(app/adapters/market/base.py:65)의 `open/high/low/close/adjusted_close`는 모두
non-optional `Decimal`이라, 결측이 있는 봉은 온전한 레코드를 만들 수 없다. 따라서 결측 봉은
부분 보정이 아니라 skip이 맞다. 현재 `_bars_from_frame`은 row 루프에서 `_to_decimal`을 직접
호출하므로, 한 봉의 결측이 곧바로 예외로 전파된다. `prices/service.py`의 try/except는 이 예외를
502로 감싼다(수정 대상 아님).

## Implementation Scope

- `app/adapters/market/yfinance.py` — `_bars_from_frame`에서 각 row의 봉 생성을 결측에 안전하게
  처리한다. 한 row라도 필수 가격(OHLC/adjusted_close)이 NaN/None이면 그 봉을 건너뛰고 다음
  row로 진행한다(유효 봉만 append). 나머지 파싱 로직·필드 매핑은 유지한다. `volume` 결측은
  기존처럼 `0` 처리를 유지한다.
- 구현 방식은 row 단위 `try/except ValueError`로 skip하거나, 사전 결측 검사 후 skip하는 방식 중
  코드에 자연스러운 쪽을 택한다. `_to_decimal`의 시그니처·다른 호출부는 바꾸지 않는다.

## Out of Scope

- `_RANGE_COUNTS`·`_RANGE_INTERVALS` 등 range→interval 매핑 변경.
- intraday 경로(`get_intraday_bars`) 변경.
- `prices/service.py`의 예외 처리·상태 코드 변경.
- yfinance 호출 파라미터(auto_adjust 등) 변경.

## Protected Files

없음.

## Requirements

1. daily 프레임에 일부 결측 봉이 섞여 있어도 `get_daily_bars`가 예외 없이 유효 봉만 반환한다.
2. 유효 봉이 하나도 없으면 빈 리스트를 반환한다(service가 404로 처리).
3. intraday·weekly 경로 회귀 없음.

## Test Requirements

- `_bars_from_frame`(또는 `get_daily_bars`) 단위 테스트: 일부 row에 NaN이 포함된 프레임을 넣어
  유효 봉만 반환되고 결측 봉이 제외되는지 확인.
- 전체 봉이 결측인 프레임 → 빈 리스트 반환 확인.
- 결측이 없는 정상 프레임 → 기존과 동일하게 전 봉 반환(회귀 방지) 확인.
- 기존 yfinance·prices 관련 테스트 회귀 없음.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

없음. 내부 provider 파싱 버그픽스로 계약·문서 변경이 없다.

## ADR Need

불필요. 기존 provider 파싱 로직의 방어적 보정이며 아키텍처 결정이 아니다.

## Failure Record Need

불필요.

## Risk Level

Low — 단일 함수의 결측 처리 보정이며, 회귀 테스트로 정상 프레임 동작을 고정한다.

## Expected Output

- 변경: `app/adapters/market/yfinance.py`, 관련 테스트 파일.
- PR 본문에 Verification 결과와, 결측 봉 skip이 정상 프레임 동작을 바꾸지 않음을 확인한 결과를 기록.

## Rules

- 최신 `dev`에서 만든 현재 브랜치(`feat/324-yfinance-daily-missing-bar`)를 유지한다. 다른 브랜치로
  전환하거나 `dev`/`main`에 직접 커밋하지 않는다.
- 커밋 메시지는 한국어 `type: 본문` 형식.
- 이 태스크 문서와 구현이 같은 PR에 함께 실린다.
- 스코프 외 파일을 변경하지 않는다.
- 검증 명령을 생략·완화하지 않는다.
