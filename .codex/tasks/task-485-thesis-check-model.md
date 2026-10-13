# Codex Handoff Task

## Source Issue

#485 — [BE] 에이전트3-1: 가설 점검 저장 모델과 에이전트용 AlertEvent 확장 (트래킹 #465, 에픽 #459)

## Task Summary

가설 점검 결과를 사용자별로 저장하는 `thesis_checks` 테이블을 만들고, 에이전트가 규칙 없이 사용자별 알림을 만들
수 있도록 `alert_events`를 확장한다(`rule_id` nullable, `source` 추가). 판정 로직과 LLM은 #486이다.

## Goal

- `thesis_checks` 모델·마이그레이션·repository가 생긴다.
- `alert_events.rule_id`가 nullable이 되고 `source`(`RULE`/`AGENT`, 기존 행 `RULE`)가 생긴다.
- `create_agent_event`로 규칙 없는 이벤트와 `APP` 전달 기록을 함께 만들 수 있다.
- 규칙 엔진의 이벤트 생성과 `/alert-events` 응답은 `rule_id` 타입과 `source` 추가 외에 바뀌지 않는다.

## Background

- 결정 정본: `docs/decisions/ADR-021-thesis-watch-private-outputs.md`(Proposed). 설계 정본:
  `docs/designs/465-thesis-watch-agent.md` §1·§2. **반드시 먼저 읽는다.**
- AlertEvent: `app/domains/alert_events/model.py`(`AlertEvent`, `AlertDelivery`, unique (`user_id`, `dedup_key`)),
  `schema.py`(`AlertEventProjection`·`AlertEventDetailProjection`), `repository.py`, `service.py`, 엔드포인트
  `app/api/v1/endpoints/alert_events.py`. 생성 선례: `app/domains/alert_engine/service.py:109-140`(중복 처리는
  `begin_nested` + IntegrityError 패턴을 확인해 따른다). 채널·상태 enum은 `app/domains/alert_rules/types.py` 등을
  확인한다(`AlertChannel.APP`, `AlertDeliveryStatus.SUCCESS`).
- 판단 기록: `app/domains/decision_logs/model.py`(`DecisionLog`)
- 새 패키지 `app/domains/agents/thesis_watch/`를 만든다. 모델은 `app/db/models.py`에 등록한다.
- 현재 Alembic head는 `c3d4e5f60073`이다. 마이그레이션 파일 패턴은 최근 파일을 따른다.
- 의존성 추가는 없다. `uv add`, `uv sync`, 네트워크, `git fetch`, docker 명령을 하지 않는다.

## Implementation Scope

1. **`thesis_checks`**(설계 §2.1, §2.3)
   - enum(`app/domains/agents/thesis_watch/types.py`): `ThesisVerdict`, `FindingRelation`, `FindingAspect`
   - 모델 `ThesisCheck`: 설계 표 그대로. unique (`decision_id`, `check_date`), 인덱스 (`user_id`, `check_date`)
   - repository: `get(decision_id, check_date)`, `create(data)`(flush만, commit하지 않음), `list_by_user(user_id, limit)`
     (`check_date` 내림차순, `id` 내림차순)
2. **`alert_events` 확장**(설계 §2.2, ADR-021 §2)
   - `AlertEventSource` enum(`RULE`, `AGENT`)은 `app/domains/alert_events/` 안의 적절한 위치에 둔다.
   - `rule_id` nullable, `source` str(20) not null, server default `RULE`. 마이그레이션은 기존 행을 `RULE`로 채우고,
     downgrade에서 `rule_id`가 null인 행이 있으면 지운 뒤 not null로 되돌린다(주석으로 이유를 남김).
   - 규칙 엔진의 생성 코드는 `source=RULE`을 명시한다.
   - `AlertEventProjection.rule_id: int | None`, `source: str` 추가
   - `AlertEventRepository.create_agent_event(user_id, asset_id, symbol, title, message, severity, evidence, dedup_key,
     triggered_at) -> AlertEvent | None`: `rule_id=None`, `source=AGENT`, `target_type=SYMBOL`, `target_id=symbol`,
     `triggered_value={}`, `APP` 전달 기록 1건(성공 상태, 전달 시각 = 발생 시각). (`user_id`, `dedup_key`)가 이미
     있으면 None을 돌려주고 기존 트랜잭션은 유지한다. commit하지 않는다.
   - 이벤트 목록·상세·읽음 API와 규칙 연결 코드에서 `rule_id`가 null일 때 오류가 나지 않는지 확인하고, 필요하면
     최소한으로 고친다. 규칙 기준 필터·조인이 있으면 에이전트 이벤트가 빠지지 않는지 확인한다.
3. 설계·ADR 문서는 구현과 다르게 정한 것이 있을 때만 고친다(ADR Status는 바꾸지 않는다).

## Out of Scope

- 판정 로직, LLM, 워크플로, job(#486), 노트(#487)
- FE(#309, 별도 repo)
- 기존 `alerts`·`signals`

## Protected Files

- `docs/decisions/`의 기존 ADR은 수정하지 않는다. ADR-021은 위 3번 조건에서만 고친다.

## Test Requirements

- `thesis_checks`: unique 위반, FK, repository 세 함수
- 마이그레이션: 단일 head, SQLite 왕복, 기존 `alert_events` 행이 `source=RULE`로 남음, Postgres 오프라인 SQL
- `create_agent_event`: 필드, `APP` 전달 기록, 같은 dedup 재호출 시 None이고 기존 트랜잭션 유지
- 규칙 엔진 이벤트 생성 테스트가 그대로 통과(`source=RULE`)
- API: 에이전트 이벤트가 목록·상세·읽음에서 정상 응답(`rule_id` null, `source=AGENT`), 다른 사용자에게 보이지 않음

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
uv run alembic heads
```

## ADR Need

ADR-021(Proposed)을 이 PR에 함께 올린다. 승인은 개발자가 리뷰에서 한다.

## Failure Record Need

불필요.

## Risk Level

Medium — 기존 테이블 제약 완화와 응답 계약 변경(FE #309 후속).

## Expected Output

- 현재 브랜치 `feat/485-thesis-check-model`에서 작업한다. 새 브랜치를 만들지 않는다.
- 커밋이 샌드박스에서 막히면 미커밋 상태로 두고 보고한다. push와 PR 생성은 하지 않는다.
- 최종 보고: 변경 파일 목록, 가정, 검증 결과

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
