# Codex Handoff Task

## Source Issue

- #390 — BE: 투자자 동향 window 불일치로 패널이 항상 비어 있음
- 부수 작업 — 로컬 개발용 뉴스 인사이트 시드 스크립트 추가

## Task Summary

`investor_flow_records`의 `window` 조건을 문자열 완전 일치에서 **기간 필터**로 바꾸고, 응답이
실제 집계 기준을 밝히게 만든다. 아울러 로컬 개발 DB에 뉴스 인사이트 데모 데이터를 넣는
스크립트를 추가한다.

## Goal

- 화면이 보내는 `window=7d`로 조회했을 때 시드 데이터(`window="5d"`로 저장됨)가 나온다.
- 응답에 실제 집계 기준이 담겨, 화면이 요청값을 그대로 집계 기준인 양 표시하지 않아도 된다.
- 로컬 DB를 재현 가능한 방식으로 채울 수 있다.

## Background — 조사 완료, 재확인 불필요

### 결함

`app/domains/news_insights/repository.py`의 `investor_flow_records`가 `window`를 저장된
문자열 라벨에 대한 완전 일치 조건으로 쓴다.

```
conditions = [
    InvestorFlow.market == query.market,
    InvestorFlow.window == query.window,
]
```

데이터를 넣는 유일한 경로인 `seed_mock_news_insights`는 `window="5d"`로 쓰고
(`app/domains/news_insights/seed.py`), 화면은 두 곳 모두 `window="7d"`로 조회한다. 값이
어긋나 행이 0건이 되고, 서비스가 이를 `availability.available = false`로 바꿔 빈 상태를
돌려준다. HTTP 200이라 오류로 보이지도 않는다.

이 도메인에서 `window`를 완전 일치로 쓰는 곳은 여기 **한 곳뿐**이다. 다른 조회는 모두
`service.py`의 `_parse_window`로 `timedelta`를 만들어 기간으로 거른다. 즉 설계된 선택이 아니라
어긋난 지점이다.

### 검증이 걸러내지 못한 이유

`tests/test_news_insights.py`의 투자자 동향 테스트 두 건이 모두 `window=5d`로만 조회한다.
시드가 쓰는 값과 테스트가 묻는 값이 같아 항상 통과하고, 화면이 실제로 보내는 값은 한 번도
검증하지 않는다.

### 결정된 방향

`window`를 기간 필터로 바꾼다(사용자 결정). `as_of >= now - window`로 거른다. 저장된 `window`
컬럼은 각 행의 집계 기준을 설명하는 값으로 남는다.

## Implementation Scope

### 1. 기간 필터 전환

- `app/domains/news_insights/repository.py`
  - `investor_flow_records`에서 `InvestorFlow.window == query.window` 조건을 제거하고,
    `InvestorFlow.as_of >= start` 조건을 넣는다. `start`는 기준 시각에서 `window`만큼 뺀 값이다.
  - 기준 시각은 호출자가 넘긴다. 리포지토리가 자체적으로 현재 시각을 만들지 않는다. 이 도메인은
    `clock.utcnow()`를 시계 주입 지점으로 쓰고 있고 테스트가 그것을 고정한다.
  - `sentiment_score` 집계도 같은 `conditions`를 쓰고 있으므로 함께 따라간다.
- `app/domains/news_insights/service.py`
  - `get_investor_flows`가 `as_of or utcnow()`로 기준 시각을 정하고, `_parse_window(query.window)`로
    만든 `timedelta`와 함께 리포지토리에 넘긴다. `_parse_window`는 이미 있다.

### 2. 집계 기준 노출

- 여러 집계 기준이 섞여 들어올 수 있으므로, 응답이 실제로 어떤 기준의 행을 돌려줬는지 밝힌다.
  - `InvestorFlowsResponse`에 집계 기준 필드를 추가한다. 반환된 행들의 `window` 라벨에서 가져온다.
  - 행이 없으면 값을 비운다. 요청값을 그대로 채워 넣지 않는다. 요청한 조회 기간과 데이터의 집계
    기준은 다른 개념이다.
- 필드 이름과 타입은 기존 wire 규약을 따른다(snake_case, `null` 허용).

### 3. 로컬 시드 스크립트

- `scripts/seed_news_insights.py`(신규)
  - `seed_mock_news_insights`를 애플리케이션 세션으로 실행한다. 이 함수는 이미 있고
    docstring이 `for contract demonstrations and tests`라고 밝히고 있다.
  - 기본 동작은 **안전하게**: 뉴스 인사이트 테이블에 이미 행이 있으면 아무것도 하지 않고
    그 사실을 알리고 종료한다.
  - `--reset` 옵션을 줄 때만 기존 뉴스 인사이트 행을 지우고 다시 넣는다. 지우는 대상 테이블을
    실행 전에 이름과 건수로 출력한다.
  - **다른 도메인 테이블은 절대 건드리지 않는다.** `news_items`·`raw_news_events`·
    `earnings_events` 등은 이 스크립트의 대상이 아니다.
  - 애플리케이션 시작 경로에 연결하지 않는다. 수동 실행 전용이다.

## Out of Scope

- 다른 조회(`overview`·`topic map`·`calendar`·`trend`)의 window 처리 변경. 이미 기간 필터다.
- `seed_mock_news_insights`가 넣는 값 변경. `window="5d"`도 그대로 둔다. 이번 수정의 요점은
  조회 측이 저장 라벨을 알아맞히지 않아도 되게 만드는 것이다.
- 프론트엔드 변경. 집계 기준 표시는 별도 PR에서 다룬다.
- `investor_flows`의 실제 공급원 확보(#391).

## Protected Files

없음.

## Requirements

- `window=7d`로 조회하면 `as_of`가 7일 이내인 시드 행이 나온다.
- `window=1d`처럼 범위를 좁히면 그 범위 밖의 행은 빠진다.
- 데이터가 아예 없을 때의 `availability.available = false`와 fallback 문구 동작은 그대로
  유지된다. 파라미터가 어긋나서 비는 경우가 없어졌으므로, 이제 빈 응답은 실제로 데이터가 없다는
  뜻이다.
- 리포지토리는 현재 시각을 스스로 만들지 않는다. 테스트가 시계를 고정할 수 있어야 한다.
- 기존 `InvestorFlowsQuery`의 `window` 패턴(`^[1-9]\d*[hd]$`)은 그대로 둔다.

## Test Requirements

- **화면이 실제로 보내는 파라미터로 조회하는 테스트를 추가한다.** `window=7d`, `market=KR`로
  조회했을 때 `window="5d"`로 저장된 시드 행이 나오는지 검증한다. 이것이 이번 결함의 핵심이다.
- 기간 경계 테스트 — 조회 기간 밖의 행이 제외되는지.
- 집계 기준 필드가 저장된 라벨을 반영하고, 행이 없을 때 비는지.
- 기존 두 테스트(`window=5d` 조회, `market=US` 미제공)는 유지한다. 단언을 약화시키지 않는다.
- 시드 스크립트는 얇은 진입점이므로 별도 테스트를 요구하지 않는다. 다만 import 시 부작용이
  없어야 한다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

`docs/designs/`의 뉴스 인사이트 2차 설계에서 투자자 동향 계약을 기술한 부분이 있으면 `window`의
의미와 새 필드를 반영한다. 없으면 문서 변경은 필요 없다.

## ADR Need

불요. 새 도메인·테이블·외부 의존성이 없고, 이 도메인의 다른 조회가 이미 쓰고 있는 기간 필터
방식으로 맞추는 정합 작업이다.

## Failure Record Need

**필요.** 시드가 쓰는 값과 테스트가 묻는 값이 같아서, 계약이 화면과 어긋난 채로 세 단계(계약·
모델·화면)를 통과한 사례다. `docs/failures/`의 기존 형식(`FAILURE-000-template.md`)을 따라
짧게 남긴다. 증상(패널이 항상 빈 상태·HTTP 200이라 오류로 안 보임), 근본 원인(저장 라벨에 대한
완전 일치 + 시드와 화면의 값 불일치), 조치(기간 필터 전환), 재발 방지(계약 테스트는 화면이
실제로 보내는 파라미터로 조회한다)를 담는다.

## Risk Level

Medium — 조회 조건이 바뀌므로 반환 집합이 달라진다. 다만 이 도메인의 다른 조회와 같은 방식으로
맞추는 것이고, 기존 테스트가 회귀를 잡는다.

## Expected Output

- 위 범위의 커밋(한국어 메시지). push·PR은 하지 않는다.
- 검증 3종 결과 보고.
- 집계 기준 필드의 이름과 타입을 무엇으로 정했는지, 여러 기준이 섞였을 때 어떻게 처리했는지 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치(fix/390-investor-flow-window)를 유지한다(자체 브랜치 생성·push·PR 금지).
