# Codex Handoff Task

## Source Issue

이슈 #255 (B1) — 알림 통합 모델 4테이블 + 마이그레이션. 에픽 #327. `gh issue view 255`,
`gh issue view 327`로 맥락을 먼저 읽는다. 상세 설계 정본은
`docs/designs/alert-rule-event-unified.md`(§1·§2·§7)이며, 상위 결정은
`docs/decisions/ADR-013-signal-alert-decision-log-screen-boundaries.md`이다. 구현 전에 설계
문서 §1(모델)·§2(enum)·§7(전환)을 반드시 읽는다.

## Task Summary

알림을 시그널 1:1 래퍼에서 벗어나 규칙/이벤트/전달/채널로 재편하기 위한 통합 도메인 모델
4테이블과 Alembic 마이그레이션을 신설한다. 본 태스크는 **모델·enum·마이그레이션까지**이며,
서비스·라우터·엔진(B2~B5)은 범위 밖이다.

## Goal

- `alert_rules`·`alert_events`·`alert_deliveries`·`notification_channels` SQLAlchemy 모델이
  설계 §1대로 정의된다.
- 설계 §2의 enum이 신규 도메인 `types.py`에 정의된다.
- 신규 4테이블을 생성하는 Alembic 마이그레이션이 추가되고 `alembic upgrade head`가 성공한다.
- `alert_events`에 `UniqueConstraint(user_id, dedup_key)`가 적용된다.
- 기존 `alerts`·`alert_candidates`·`watchlists` 테이블·모델은 변경하지 않는다(흡수는 후속 B3).

## Background

repo는 int PK + `ForeignKey` 관례를 쓴다(설계가 스펙의 UUID 대신 int PK를 채택). 시각 컬럼은
기존 도메인과 동일하게 `DateTime(timezone=True)` + `server_default=func.now()`,
`updated_at`은 `onupdate=func.now()`. 기존 `app/domains/alerts/model.py`(`Alert`)와
`app/domains/alert_candidates/model.py`(`AlertCandidate`)의 스타일을 참고한다. 신규 도메인은
`app/domains/alert_rules`, `app/domains/alert_events`(하위에 `AlertDelivery` 포함),
`app/domains/notification_channels`로 만든다.

## Implementation Scope

- `app/domains/alert_rules/` — `model.py`(`AlertRule`), `types.py`(enum: `AlertRuleSource`,
  `AlertTargetType`, `AlertMetric`, `AlertOperator`, `AlertSeverity`, `AlertChannel`,
  `AlertDeliveryPolicy`, `AlertTemplateType`), `__init__.py`.
- `app/domains/alert_events/` — `model.py`(`AlertEvent`, `AlertDelivery`),
  `types.py`(enum: `AlertDeliveryStatus`, `AlertEventStatus`), `__init__.py`.
- `app/domains/notification_channels/` — `model.py`(`NotificationChannel`), `__init__.py`.
- 컬럼·타입·제약은 설계 §1.1~§1.4 표를 정본으로 따른다. `condition`·`channels`·
  `triggered_value`·`evidence`·`configuration`은 `JSON` 컬럼.
- Alembic 마이그레이션 1건(신규 4테이블 create). `alembic/versions`의 기존 마이그레이션 형식·
  `down_revision` 연결 관례를 따른다. FK·index·unique 제약을 마이그레이션에 반영한다.
- 신규 모델을 `app/db/models.py`(중앙 모델 등록 지점, `alembic/env.py`가 import)에서 import해
  `Base.metadata`에 등록한다. 이 등록이 있어야 alembic autogenerate와 테스트 `create_all`이
  신규 테이블을 인식한다.

## Out of Scope

- 서비스·리포지토리·스키마(projection)·라우터 (B2~B5).
- 알림 엔진·스케줄러 (B5).
- 기존 `alerts`·`alert_candidates`·`WatchlistAlertRuleService` 흡수·deprecate·데이터 백필 (B3).
- 기존 테이블 삭제 마이그레이션 (후속).
- FE.

## Protected Files

없음. (기존 `alembic.ini`·`app/db/base.py` 등록 경로는 필요한 최소 연결만 수정 가능. 그 외
기존 도메인 모델은 수정 금지.)

## Requirements

1. 4개 모델이 설계 §1 컬럼·타입·제약을 정확히 반영한다.
2. enum 값이 설계 §2와 일치한다(`AlertMetric.TOPIC_IMPACT_SCORE` 포함, 비활성 여부는 값
   정의와 무관하게 enum에는 존재).
3. `alembic upgrade head`가 깨끗한 DB에서 성공하고, `alembic downgrade`도 대칭으로 동작한다.
4. `mypy` no-untyped-def 등 타입 게이트를 통과한다(기존 도메인과 동일한 `Mapped[...]` 스타일).

## Test Requirements

- 테스트는 SQLite 인메모리 + `Base.metadata.create_all` 방식이다(`tests/conftest.py`). 신규
  모델이 `app/db/models.py` 등록으로 metadata에 들어와야 테스트에서 테이블이 생성된다.
- 신규 모델 생성·기본값·`UniqueConstraint(user_id, dedup_key)` 위반 시 무결성 오류를 확인하는
  단위 테스트(기존 테스트가 쓰는 DB 픽스처 방식 재사용).
- enum 값 스냅샷/구성 테스트가 있다면 신규 enum 반영.
- 기존 테스트 회귀 없음.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`
- `uv run alembic upgrade head` — postgres 연결이 필요하다. 샌드박스에 DB가 없으면 실행 불가일
  수 있으므로, 그 경우 마이그레이션은 기존 `alembic/versions` 형식·`down_revision` 연결을
  따라 작성만 하고 실행 불가를 보고한다. 1차 게이트는 ruff·mypy·pytest다.

## Documentation Impact

- `docs/designs/alert-rule-event-unified.md`는 정본이므로 수정하지 않는다(구현이 설계를 따른다).
  설계와 불가피하게 어긋나는 부분이 생기면 구현을 멈추고 가정을 보고한다.

## ADR Need

불필요. 방향은 ADR-013에서 이미 결정됐고 본 태스크는 그 구현이다.

## Failure Record Need

불필요(신규 기능 추가, 실패 복기 대상 아님).

## Risk Level

Medium — 신규 스키마·마이그레이션이라 후속 도메인의 계약 기반이 된다. 설계 §1 표를 정확히
따르는 것이 중요하다.

## Expected Output

- 신규 3개 도메인 디렉터리의 모델·enum, Alembic 마이그레이션 1건, 관련 단위 테스트.
- 현재 브랜치 `feat/be-alerts-unified-model`에 커밋(자체 브랜치 생성 금지).
- 검증 4종 통과 결과 보고.

## Rules

- Stay within scope. (모델·enum·마이그레이션까지. 서비스·라우터·엔진 금지.)
- Do not weaken verification.
- 현재 브랜치 `feat/be-alerts-unified-model`을 유지한다. 새 브랜치를 만들지 않는다.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
