# Codex Handoff Task

## Source Issue

이슈 #331 (B5) — 알림 엔진(스케줄러 주기 평가). 에픽 #327. `gh issue view 331`,
`gh issue view 327`로 맥락을 읽는다. 설계 정본은 `docs/designs/alert-rule-event-unified.md`
(§5 엔진·§6 중복 방지). ADR-003(스케줄러)·ADR-013(§15 경계). B1~B4가 모델·규칙·이벤트·채널을
모두 제공한다.

## Task Summary

`enabled` 규칙을 주기적으로 평가해 조건 충족 시 중복 방지를 통과한 건만 `AlertEvent` +
`AlertDelivery`(APP)를 생성하는 엔진을 구현한다. HTTP 요청 경로에서 평가하지 않는다. 엔진은
시그널을 생성하지 않고 기존 지표·시그널의 변화만 감시한다(ADR-013 §15).

## Goal

- `AlertEngineService.run_cycle()`가 활성 규칙을 순회·평가하고, 중복 방지를 통과한 건에 대해
  `AlertEvent`와 규칙 `channels`별 `AlertDelivery`(MVP: `APP` 즉시 `SUCCESS`)를 생성하며
  규칙 `last_triggered_at`을 갱신한다.
- 조건 평가가 설계 §4 조건 스키마(단일 + `all`)를 스냅샷에 적용한다.
- 중복 방지(설계 §6)가 정확히 동작: `dedup_key`(rule_id+target_id+event_fingerprint) +
  cooldown + state-transition(`ONCE_PER_TRANSITION`은 상태 전이 시에만, `ONCE_PER_DAY`는
  대상·규칙당 하루 1회).
- 스케줄러에 알림 평가 잡이 등록된다(기존 registry 패턴).

## Background

기존 패턴을 그대로 따른다.

- **워커 잡**: `app/worker/jobs/`의 잡은 `SessionLocal()` 생성 → `JobRunService.start/succeed/
  fail`로 실행 추적 → 도메인 서비스 호출 → `db.commit()` → `finally: db.close()` 구조다
  (`app/worker/jobs/signal_snapshots.py` 참고). 알림 잡도 동일 구조로 `app/worker/jobs/alerts.py`
  에 `evaluate_alert_rules_job()`을 만든다.
- **스케줄러 등록**: `app/scheduler/registry.py`의 `default_scheduler_registry`에
  `ScheduleDefinition(job=FunctionSchedulerJob(name=..., func=evaluate_alert_rules_job),
  cron=..., enabled=...)`을 추가한다. enabled는 기존 `settings.ANALYSIS_SCHEDULE_ENABLED`처럼
  settings 플래그(예: `settings.ALERT_ENGINE_ENABLED`, 기본값은 기존 관례에 맞춰 추가)로
  게이트한다.
- **상태 전이 소스**: `SignalService.capture_daily_snapshot()`가 시그널 상태 일일 스냅샷을
  캡처한다(`app/domains/signals`). state-transition 판정에 직전 상태가 필요하면 이 스냅샷/이전
  `AlertEvent`의 상태를 근거로 삼는다. 별도 신규 상태 저장소는 최소화한다.

## Implementation Scope

- `app/domains/alert_events/` 또는 신규 `app/domains/alert_engine/`에 엔진 로직을 둔다(도메인
  경계는 기존 관례에 맞게 택일하되, 이벤트·전달 생성은 `alert_events` 리포지토리를 재사용).
  - `AlertEvaluator.evaluate_rule(rule, snapshot) -> 평가 결과`(충족 여부·triggered_value·
    evidence). 순수 로직으로 스냅샷을 입력받아 테스트 가능해야 한다.
  - `AlertDedupService.should_emit(rule, result, ...) -> bool`(dedup_key·cooldown·transition).
  - `AlertEngineService.run_cycle()`(오케스트레이션: 활성 규칙 조회 → 스냅샷 수집 → 평가 →
    dedup → 이벤트/전달 생성 → last_triggered_at 갱신). 요약 결과 반환.
- **MetricSnapshotProvider 경계**: 대상(target_type·target_id)별 현재 지표 스냅샷을 반환하는
  얇은 provider를 두고, 아래 지표를 기존 서비스에서 읽어 채운다. 신규 수집 파이프라인은 만들지
  않는다.
  - `NEWS_RISK`·`THEME_HEAT`·`AI_JUDGMENT_CHANGED` — `app/domains/watchlists`
    (`trend_service`/관련 서비스).
  - `PRICE_CHANGE_1D` — `app/domains/prices`.
  - `SIGNAL_CHANGED` — `app/domains/signals`(스냅샷/현재 상태).
  - `POSITION_WEIGHT` — `app/domains/portfolios`.
  - `EARNINGS_DATE` — `app/domains/earnings`.
  - 특정 지표를 기존 서비스에서 깨끗하게 소싱할 수 없으면 **임의로 stub하지 말고** provider에서
    해당 지표를 "미지원"으로 남기고 그 사실을 보고한다(후속 이슈로 채운다). `TOPIC_IMPACT_SCORE`는
    토픽 인프라 부재로 비활성이므로 대상에서 제외한다.
- `app/worker/jobs/alerts.py` — `evaluate_alert_rules_job()`.
- `app/scheduler/registry.py` — 스케줄 등록. 필요 시 `app/core/config.py`에 enable 플래그 추가.

## Out of Scope

- Redis 큐 기반 Evaluator/Delivery 워커 분리·SSE — 2차.
- 외부 채널(EMAIL/DISCORD/SLACK) 실제 발송 — 2차(MVP는 `APP` delivery만).
- 시그널 생성(엔진은 감시만, ADR-013 §15).
- 신규 지표 수집 파이프라인.
- FE.

## Protected Files

없음. `app/scheduler/registry.py`·`app/core/config.py`는 추가만.

## Requirements

1. `run_cycle()`이 활성 규칙만 평가하고, 조건 미충족·중복·cooldown·비전이 건은 이벤트를 만들지
   않는다.
2. 충족·발송 가능 건은 `AlertEvent`(triggered_value·evidence 포함) + `AlertDelivery`(APP,
   SUCCESS)를 생성하고 `last_triggered_at`을 갱신한다.
3. `dedup_key` 중복은 `UniqueConstraint(user_id, dedup_key)`로도 방지되어 중복 이벤트가 생기지
   않는다.
4. `ONCE_PER_TRANSITION`은 상태 전이 시에만, `ONCE_PER_DAY`는 하루 1회로 제한한다.
5. 엔진은 어떤 경우에도 `Signal`을 생성하지 않는다.
6. 스케줄러 잡이 registry에 등록되고 `mypy` 게이트를 통과한다.

## Test Requirements

- `AlertEvaluator`·`AlertDedupService`를 합성 스냅샷/규칙으로 검증하는 단위 테스트(조건 충족/
  미충족, dedup_key 동일 시 미발송, cooldown 내 미발송, 전이 시 발송·유지 시 미발송,
  `ONCE_PER_DAY` 하루 1회).
- `run_cycle()` 통합 테스트: seed한 규칙·지표 상황에서 이벤트/전달 생성·`last_triggered_at`
  갱신·시그널 미생성 확인. 지표 소스는 기존 테스트 픽스처/모의 provider로 구성.
- 기존 테스트 회귀 없음.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

- 설계 정본은 임의 변경 금지. 어긋나면 멈추고 가정을 보고한다. 미지원으로 남긴 지표가 있으면
  보고에 명시한다.

## ADR Need

불필요. ADR-003(스케줄러)·ADR-013으로 결정 완료, 본 태스크는 구현이다. 스케줄러 잡 추가는
기존 registry 패턴을 따르는 애플리케이션 기능이다.

## Failure Record Need

불필요.

## Risk Level

High — BE 에픽의 마지막·통합 지점이 가장 많다. 중복 방지 로직(§6)의 정확성이 핵심이며, 지표
소싱은 깨끗한 것만 연결하고 나머지는 보고한다.

## Expected Output

- 엔진(evaluator·dedup·engine service·snapshot provider), 워커 잡, 스케줄러 등록, 테스트.
- 미지원으로 남긴 지표 목록 보고.
- 지정된 현재 브랜치에 커밋(자체 브랜치 생성 금지).
- 검증 3종 통과 보고.

## Rules

- Stay within scope. 엔진은 감시만 하고 시그널을 만들지 않는다.
- 지표를 소싱 못 하면 stub하지 말고 미지원으로 보고한다.
- Do not weaken verification.
- 지정된 현재 브랜치를 유지한다. 새 브랜치 금지.
- Report assumptions, unsupported metrics, and verification results.
