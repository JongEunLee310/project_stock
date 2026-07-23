# Codex Handoff Task

## Source Issue

#393 — BE: 자금 흐름 예상 범위를 수치 구간으로 개방 (outlook·scenario)

## Task Summary

자금 흐름 전망의 금액을 라벨 문자열에서 **하한·상한·통화를 갖는 수치 구간**으로 바꾼다.
`fund_flow_outlooks`의 섹터별 예상 흐름과 `fund_flow_scenarios`의 시나리오별 예상 순유입에
같은 형식을 적용한다.

## Goal

- 화면이 문자열 파싱 없이 구간 막대를 그릴 수 있다.
- 값이 없는 항목과 값이 0인 항목이 응답에서 구분된다.
- 단위·통화가 계약에 명시돼 화면이 추측하지 않는다.
- 구간을 대표하는 단일 수치 필드가 생기지 않는다.

## Background

결정 근거는 `docs/decisions/ADR-017-fund-flow-quantitative-range.md`에 있다. 요지만 옮긴다.

3차 설계는 확정 예측을 막기 위해 금액을 라벨 문자열로 저장하기로 했고,
`fund_flow_outlooks.estimated_range`는 `"+0.8~+1.8조원 가능 범위"` 같은 `str`이 됐다.
`fund_flow_scenarios`에는 금액 자리가 아예 없다.

그 결과 설계 이미지가 요구하는 막대 그래프를 그릴 수 없었고, 화면은 남은 정성 필드를 전부
펼치는 긴 텍스트 카드가 됐다. 문자열을 파싱해 막대를 그리는 것은 숫자를 만들어 내는 것과
같으므로 택할 수 없다.

ADR-017은 **금지 대상이 점 예측이지 구간이 아니라는 구분**을 세우고, 하한·상한을 함께 주는
수치 구간으로 표현을 바꾼다. 구간은 불확실성을 폭으로 드러내므로 원래 결정이 막으려던 위험을
만들지 않는다.

설계 문서 `docs/designs/307-news-intelligence-phase3.md`의 §2.1·§2.2·§3.1·§3.2와 서두
와이어 컨벤션 절은 **이미 이 결정에 맞춰 갱신돼 있다.** 구현은 그 문서를 따른다.

## Implementation Scope

### 1. 모델·마이그레이션

- `app/domains/news_insights/model.py`
  - `FundFlowOutlook` — `estimated_range`(str) 컬럼을 제거하고
    `estimated_flow_low`·`estimated_flow_high`(Decimal, nullable)·
    `estimated_flow_currency`(str, nullable)를 추가한다.
  - `FundFlowScenario` — `expected_net_flow_low`·`expected_net_flow_high`(Decimal, nullable)·
    `expected_net_flow_currency`(str, nullable)를 추가한다.
  - Decimal 정밀도는 기존 금액 컬럼(`InvestorFlow.net_value`)과 맞춘다.
- alembic revision 1건을 3차 head(`c3d4e5f6006d`) 위에 스택한다.
  - 컬럼 교체다. 기존 `estimated_range` 문자열을 수치로 백필하지 않는다. 현재 실데이터는
    시드뿐이며, 서술 문자열을 파싱해 수치를 만드는 것은 이 작업이 금지하는 바로 그 행위다.
  - downgrade에서 원래 컬럼 구조로 되돌린다.

### 2. 스키마·서비스

- `app/domains/news_insights/schema.py`
  - 하한·상한·통화를 갖는 구간 projection을 하나 정의하고 두 응답에서 함께 쓴다.
    금액은 `Decimal`을 문자열로 직렬화한다(`InvestorFlowItem.net_value`의
    `field_serializer` 방식을 그대로 따른다).
  - `FundFlowOutlookItem` — `estimated_range: str | None`을 제거하고 구간 필드로 교체한다.
    필드명은 설계 문서 §3.1의 `estimated_flow`를 쓴다.
  - `FundFlowScenarioItem` — 설계 문서 §3.2의 `expected_net_flow`를 추가한다.
  - **하한 > 상한이면 거부한다.** Pydantic validator로 막는다.
  - 하한·상한·통화 중 하나라도 없으면 구간 전체를 `null`로 만든다. 반열린 구간은 만들지
    않는다.
- `app/domains/news_insights/service.py` — 위 규칙에 따라 레코드를 projection으로 변환한다.

### 3. 시드

- `app/domains/news_insights/seed.py` — 기존 `estimated_range` 문자열 대신 수치 구간을 넣는다.
  현재 문자열이 담고 있던 의미를 그대로 옮긴다.
  - 반도체 `"+0.8~+1.8조원 가능 범위"` → 하한 8000억, 상한 1조 8000억, 통화 KRW.
  - 2차전지 `"-0.3~+0.3조원 가능 범위"` → 하한 -3000억, 상한 +3000억, 통화 KRW.
  - 값은 **통화 기본 단위(원)** 로 넣는다. 억·조 단위로 넣지 않는다.
  - 시나리오 3종에도 예상 순유입 구간을 넣는다. 낙관·기준·보수의 방향과 어긋나지 않게 한다.
    단, 한 시나리오는 구간을 `null`로 두어 값이 없는 경우가 계약에서 표현되는지 드러낸다.

## Out of Scope

- 구간을 산출하는 정량 로직. 이 작업은 표현 형식만 정한다.
- 프론트엔드 변경. 구간 막대 렌더는 FE #294에서 다룬다.
- `weight`·`likelihood`·`confidence` 등 다른 필드의 의미 변경.
- 구간을 대표하는 단일 수치(중앙값·기대값) 추가. ADR-017이 명시적으로 금지한다.
- 다른 도메인의 금액 표현.

## Protected Files

없음.

## Requirements

- 통화 코드는 응답에 함께 실린다. 화면이 단위를 추측하지 않아야 한다.
- 값이 없는 구간(`null`)과 하한·상한이 모두 0인 구간이 구분된다.
- 하한은 상한보다 클 수 없다. 위반은 스키마에서 거부한다.
- 금액은 문자열로 직렬화된다. float으로 나가지 않는다.
- 마이그레이션 적용 후 `uv run alembic heads`가 단일 head를 보여야 한다.

## Test Requirements

- `/fund-flow-outlook` 응답에 구간이 실리고, 금액이 문자열이며, 통화가 함께 오는지.
- `/topics/{id}/scenarios` 응답에 시나리오별 구간이 실리는지. 구간이 `null`인 시나리오가
  그대로 `null`로 오는지.
- 하한 > 상한인 입력이 거부되는지.
- 기존 테스트에서 `estimated_range`를 단언하던 부분을 새 형식으로 옮긴다. 단언을 삭제하지
  말고 다시 쓴다.
- 기존 테스트를 약화시키지 않는다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`
- `uv run alembic heads`

## Documentation Impact

`docs/designs/307-news-intelligence-phase3.md`와
`docs/decisions/ADR-017-fund-flow-quantitative-range.md`는 **이미 갱신돼 있다.** 구현이 문서와
어긋나면 문서가 아니라 구현을 맞춘다. 문서와 다르게 가야 할 이유를 발견하면 구현을 멈추고
그 이유를 보고한다.

## ADR Need

이미 작성됨(ADR-017). 추가 ADR은 불요하다.

## Failure Record Need

불요. 실패한 접근을 사후에 대체한 것이 아니라, 설계 이미지와 계약의 어긋남을 확인하고 결정을
갱신한 계획된 변경이다. 판단 근거는 ADR-017에 남았다.

## Risk Level

Medium — 스키마 변경과 마이그레이션이 있고 응답 계약이 바뀐다. 다만 실데이터가 시드뿐이라
데이터 손실 위험은 낮고, 프론트엔드 어댑터가 선택적 접근을 쓰고 있어 런타임 오류는 나지 않는다.

## Expected Output

- 위 범위의 커밋(한국어 메시지). push·PR은 하지 않는다.
- 검증 4종 결과 보고.
- 구간 projection의 이름과 필드 구성, 값이 없는 경우를 어떻게 표현했는지 보고.
- 시드에서 문자열을 수치로 옮길 때 쓴 환산 값을 보고한다.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치(feat/393-fund-flow-range)를 유지한다(자체 브랜치 생성·push·PR 금지).
