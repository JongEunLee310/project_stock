# Design: 시그널 근거 불릿 key_points 필드 (#260)

## Status

Approved

## Context

시그널 페이지 재설계 로드맵(전략 A) 3단계입니다. 현재 시그널 카드의 근거는
`reason` 한 문장뿐이라 스캔이 어렵다는 실사용 피드백이 있었습니다(PR #132 화면
확인). 카드에서 빠르게 훑을 수 있는 구조화 불릿 필드를 신설합니다. 로드맵
2단계(#257 스냅샷·변화 추적)와 독립이며, 이 작업이 끝나면 4단계 FE 연결이
가능합니다.

## Verified Facts (2026-07-10, feat/260-signal-key-points 기준)

- `Signal` 모델(`app/domains/signals/model.py`)의 근거 필드는 `reason: Text`
  (필수)와 `evidence: Text nullable`(JSON dict 직렬화) 두 가지다.
- `evidence`는 `SignalRepository._dump_evidence`가 `json.dumps(...,
  ensure_ascii=False)`로 저장하고, `SignalResponse.parse_evidence`
  (`field_validator, mode="before"`)가 역직렬화한다. 동일 패턴을 재사용한다.
- 시그널 생성 경로는 3곳이다:
  - `HighImpactNewsRule`(`app/domains/signals/rules/high_impact_rule.py`) —
    impact_level·sentiment·뉴스 summary/title 보유. reason은 영어 문장.
  - `ThesisConflictRule`(`app/domains/signals/rules/thesis_conflict_rule.py`) —
    `ThesisConflictResult`(status, reason, invalidation_triggered) 보유.
  - 포트폴리오 집중도(`app/domains/portfolios/service.py`) — weight·threshold·
    market_value 보유. reason은 한국어 문장.
- API 계약 스냅샷은 `tests/test_api_contract.py`의 `SIGNAL_CONTRACT`가 단언한다.
- 자연어 출력 언어는 #231 선례에 따라 한국어다(JSON 키·enum 값은 영어 유지).

## Decisions

- **저장 형태**: `Signal.key_points`에 `Text nullable` 컬럼을 추가하고 JSON
  문자열 배열(`["...", "..."]`)로 직렬화한다. `evidence`와 동일한
  dump/validator 패턴을 따른다. 별도 테이블은 만들지 않는다(불릿은 시그널과
  생명주기가 같고 개별 조회가 없다).
- **생성 주체**: 각 생성 경로가 이미 보유한 입력만으로 2~3개의 한국어 불릿을
  조립한다. 새 데이터 조회나 LLM 호출은 없다.
- **불릿 내용** (구현 시 문구는 다듬되 정보 항목은 유지):

  | 경로 | 불릿 정보 항목 |
  | --- | --- |
  | HighImpactNewsRule | 영향도(impact_level), 감성(sentiment, 있을 때만), 대상 뉴스 요지(summary 또는 title) |
  | ThesisConflictRule | 충돌 상태(status)·무효화 발동 여부, 충돌 사유(conflict_result.reason) |
  | 포트폴리오 집중도 | 비중 vs 임계치(weight, threshold), 평가금액(market_value) |

- **응답 계약**: `SignalResponse.key_points: list[str]`로 노출하고 저장값이
  null이면 빈 배열로 내려간다. 하위 응답(`SignalExpandedResponse`,
  `SignalCurrentResponse` 등)은 상속으로 자동 반영된다. FE는 빈 배열일 때
  `reason`으로 폴백한다(4단계에서 처리, 이번 범위 밖).
- **입력 계약**: `SignalCreate.key_points: list[str] | None = None`. POST
  /signals 수동 생성도 동일 필드를 받는다.
- **backfill 없음**: 기존 행은 null 유지. 시그널은 만료로 회전하므로 새 불릿이
  자연히 채워진다.

## Schema

`signals` 테이블 변경 (Alembic migration 1건):

| column | type | nullable | note |
| --- | --- | --- | --- |
| key_points | Text | yes | JSON 문자열 배열, 예: `["영향도 CRITICAL", ...]` |

downgrade는 컬럼 drop.

## Implementation Sketch

- `app/domains/signals/model.py` — `key_points: Mapped[str | None]` 추가.
- `app/domains/signals/schema.py` — `SignalCreate.key_points`,
  `SignalResponse.key_points`(before-validator로 JSON 역직렬화, null → `[]`).
- `app/domains/signals/repository.py` — `create()`에서 배열을 JSON 문자열로
  직렬화(기존 `_dump_evidence` 패턴).
- `app/domains/signals/rules/high_impact_rule.py`,
  `rules/thesis_conflict_rule.py`,
  `app/domains/portfolios/service.py` — 위 표의 불릿 생성.
- `alembic/versions/` — add column migration.
- `tests/test_api_contract.py` — `SIGNAL_CONTRACT`에 `key_points: list` 추가.

## Out of Scope

- LLM이 불릿을 직접 생성하는 경로 (LLM 어댑터 보류 중).
- 기존 `reason`·`evidence` 계약 변경 (HighImpactNewsRule의 영어 reason 정리
  포함 — 불릿이 카드 표시를 대체하므로 별도 후속으로 남긴다).
- 기존 시그널 backfill.
- FE 연결 (로드맵 4단계).

## Test Plan

- migration upgrade/downgrade 왕복.
- 생성 경로 3곳 각각: 불릿이 2~3개 생성되고 해당 정보 항목(리터럴 근거:
  impact_level·sentiment / status·invalidation / weight·threshold)을 포함한다.
- `key_points=None`인 기존 행이 응답에서 빈 배열로 내려간다.
- POST /signals에 `key_points`를 넘기면 응답에 그대로 반영된다.
- `SIGNAL_CONTRACT` 계약 스냅샷 갱신, `view=all`·`view=current` 응답 회귀 유지.
