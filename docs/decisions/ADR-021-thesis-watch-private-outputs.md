# ADR-021: Thesis Watch Agent Private Outputs — 사용자별 결과 저장과 규칙 없는 AlertEvent

## Status

Proposed — 2026-10-13. 에이전트 3(투자 가설 감시, #465) 착수 결정. ADR-013(알림 모델 방향)과
ADR-020(작업형 에이전트 공통 경계)을 보완한다.

## Context

에이전트 3은 사용자의 판단 기록(`decision_logs`)에 적힌 가설과 근거를 매일 새 근거(일일 브리프, 공시
분석)와 대조해, 가설을 흔드는 근거가 있으면 알려 준다. 사용자는 2026-10-13 다음과 같이 정했다.

- 감시 대상은 판단 기록만 한다. 기존 `investment_theses`는 다루지 않는다.
- 실행 시점은 일일 브리프 직후다.
- 에이전트는 알림과 노트만 남긴다. 가설과 판단 기록(상태, 근거, 리스크)은 바꾸지 않는다.
- 알림은 사용자별 `AlertEvent`로 보낸다.

에이전트 1·2의 산출물은 모두 종목 단위로 공유되는 데이터다. 리포트(`research_reports`)와
신호(`signals`)에는 `user_id`가 없고, 기존 알림(`alerts`)은 신호에 1:1로 묶인다. 판단 기록은 사용자
개인 데이터이므로, 같은 경로를 쓰면 두 가지 문제가 생긴다.

1. 가설 점검 결과를 리포트나 신호에 저장하면 다른 사용자에게도 보인다. 가설 문구를 빼더라도 "누군가의
   가설이 흔들렸다"는 사실이 그 종목 신호 목록에 드러난다.
2. 기존 `Alert`로 알리려면 공유 신호를 먼저 만들어야 한다.

ADR-013은 알림의 목표 모델을 `AlertRule`과 `AlertEvent`로 정했다. `AlertEvent`는 사용자별이고 제목,
메시지, 심각도, 근거를 직접 가진다. 하지만 지금은 `rule_id`가 필수라서 규칙 없이 발생하는 알림을
담을 수 없다.

## Decision

### 1. 사용자 데이터에서 나온 에이전트 산출물은 사용자별로 저장한다

가설 점검 결과는 새 테이블 `thesis_checks`(사용자, 판단 기록, 종목, 점검일, 판정, 내용)에 저장한다.
공유 테이블(`research_reports`, `signals`)에는 쓰지 않는다. 앞으로 사용자 데이터를 입력으로 쓰는
에이전트도 같은 원칙을 따른다.

### 2. 에이전트 알림은 규칙 없는 `AlertEvent`로 보낸다

`alert_events.rule_id`를 nullable로 바꾸고, 발생 출처를 나타내는 `source`(`RULE`, `AGENT`)를 추가한다.
에이전트는 `source=AGENT`, `rule_id=null`로 이벤트를 만든다. 전달은 `APP` 채널 기록 하나로 한다. 외부
채널(이메일 등) 전달은 이번 범위가 아니다. 이 변경은 ADR-013의 목표 모델 안에서 "규칙 없이 발생하는
이벤트"를 허용하는 확장이다. 기존 `Alert`와 신호는 건드리지 않는다.

`AlertEvent` 조회 응답의 `rule_id`는 nullable이 되고 `source`가 추가된다. 대상은 `target_type=SYMBOL`,
`target_id`는 종목 심볼로 둔다(FE `AlertTargetType`에 이미 있는 값).

### 3. 에이전트는 판단 기록을 바꾸지 않는다

에이전트 3은 판단 기록의 상태 전이, 근거·리스크 추가, 재검토 트리거 변경을 하지 않는다(ADR-020 §3
"산출물만 쓴다"). 사용자가 직접 설정한 재검토 트리거의 기존 동작은 그대로 둔다.

### 4. 사용자 자유 텍스트는 마스킹을 거쳐 클라우드로 보낸다

가설·이유·리스크 설명은 사용자 자유 텍스트이므로, LLM 입력 projection의 `free_text_fields`로 선언해
게이트웨이의 `PrivacyGate.mask`를 거친다(ADR-019). 입력에는 사용자 식별자, 보유 수량, 금액을 싣지 않는다.

## Alternatives

- **공유 신호(`THESIS_BROKEN`)와 기존 `Alert` 재사용.** 기각. FE 알림 화면에 바로 나오지만, 신호가
  종목 단위라 다른 사용자의 신호 목록에 드러난다.
- **`signals`에 `user_id` 추가.** 기각. 신호를 읽는 모든 조회(목록, 확장, 현재 상태, 변화, 요약, 대시보드,
  관심종목 상태)에 사용자 필터를 넣어야 하고, 하나만 빠져도 노출된다.
- **사용자별 시스템 `AlertRule`을 만들어 연결.** 기각. 에이전트가 사용자 설정(규칙)을 만들게 된다.
- **1차는 노트만 남기고 알림은 후속.** 보류. 사용자가 알림을 1차 범위로 정했다.

## Consequences

- 쉬워지는 것: 사용자 데이터를 다루는 에이전트의 결과가 다른 사용자에게 새지 않는 경로가 생긴다.
  `AlertEvent`가 규칙 엔진과 에이전트 알림을 함께 담는 통지 기록이 된다.
- 어려워지는 것과 위험
  - `AlertEvent` 응답 계약이 바뀐다(`rule_id` nullable, `source` 추가). FE 알림 화면은 이미
    `/alert-events`를 표시하지만 `ruleId`를 "규칙 #N"으로 그린다(`AlertDetail`, `AlertHistoryPanel`).
    FE가 `rule_id` null을 "에이전트"로 표시하도록 맞추기 전까지는 "규칙 #null"처럼 보일 수 있다.
  - 실 DB에 판단 기록이 아직 없어 실측 검증은 예시 데이터로 한다.

## Follow-up

- 설계 `docs/designs/465-thesis-watch-agent.md`와 구현(#465 하위 이슈)
- FE: `AlertEventDto.rule_id` nullable과 `source` 반영, 에이전트 출처 표시(`AlertDetail`, `AlertHistoryPanel`)

## Related Documents

- ADR-013(알림 모델 방향), ADR-016(판단 기록 재설계), ADR-019(자유 텍스트 마스킹), ADR-020(작업형
  에이전트), ADR-009(CloudSafe)
- 에픽 #459, 트래킹 #465
