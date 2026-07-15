# Codex Handoff Task

## Source Issue

이슈 #328 (B2) — `alert_rules` 도메인·규칙 관리 API. 에픽 #327. `gh issue view 328`,
`gh issue view 327`로 맥락을 읽는다. 설계 정본은 `docs/designs/alert-rule-event-unified.md`
(§3 템플릿 카탈로그·§4 조건 스키마·§8 API). 모델·enum은 B1(#255, 머지됨)이 이미 제공한다
(`app/domains/alert_rules/model.py`, `types.py`).

## Task Summary

B1이 만든 `AlertRule` 모델 위에 스키마(projection/request)·리포지토리·서비스·엔드포인트를
얹어 규칙 관리 API와 요약(overview)을 구현한다. 이벤트·채널·엔진은 범위 밖(B3·B4·B5).

## Goal

- 템플릿 카탈로그 `GET /api/v1/alert-rules/templates`가 설계 §3의 6종을 반환한다
  (`TOPIC_IMPACT_SURGE`는 `is_active=false`로 표기).
- 규칙 CRUD·상태 전환이 동작한다: `GET/POST /alert-rules`, `PATCH /alert-rules/{id}`,
  `DELETE /alert-rules/{id}`(SYSTEM 규칙 삭제 불가), `POST .../pause`·`.../resume`.
- 조건 검증기가 설계 §4의 지원 metric·operator·값 도메인만 허용하고, 벗어나면
  `422 VALIDATION_ERROR`.
- `GET /api/v1/alerts/overview`가 요약(active_rule_count·triggered_today_count·
  high_severity_count·paused_rule_count·unread_count·as_of)을 반환한다.
- 모든 엔드포인트 소유권 `user_id` 기준, 타인 접근 시 `*_FORBIDDEN`.

## Background

도메인 파일 구성은 기존 관례를 따른다: 도메인 로직은 `app/domains/alert_rules/`의
`schema.py`·`repository.py`·`service.py`, HTTP 라우터는 `app/api/v1/endpoints/`의 새 모듈
(`alert_rules.py`)에 두고 `app/api/v1/router.py`에 `include_router(prefix="/alert-rules",
tags=["alert-rules"])`로 등록한다(기존 `watchlists`·`decision_logs` 도메인이 정확한 참고
모델). overview 라우트는 경로 `/api/v1/alerts/overview`로 노출한다(기존 `alerts` 엔드포인트
모듈에 추가하거나 신규 모듈에 두되 경로만 맞춘다). 인증·소유권·공통 pagination/sort 의존성은
기존 `app/api/v1/deps.py`를 재사용한다.

overview의 카운트는 `alert_rules`(active/paused)와 `alert_events`(triggered_today·
high_severity·unread) 양쪽을 읽는다. `alert_events` 테이블은 B1이 이미 만들었으므로 count
쿼리는 가능하다(엔진 전이라 값은 0일 수 있음).

## Implementation Scope

- `app/domains/alert_rules/schema.py` — 요청 스키마와 `AlertRuleProjection`·
  `AlertRuleTemplateProjection`·`AlertOverviewProjection`(파생 뷰는 'DTO' 금지, 'projection').
- `app/domains/alert_rules/repository.py` — 규칙 CRUD·상태 전환·소유 조회·overview용 count.
- `app/domains/alert_rules/service.py` — 템플릿 카탈로그(§3, 기본 condition·severity·
  cooldown·delivery_policy·기본 채널), 조건 검증기 `validate_condition`(§4), CRUD·pause/resume·
  overview 오케스트레이션, 소유권 검사.
- `app/api/v1/endpoints/alert_rules.py` — 라우터. `app/api/v1/router.py` 등록.
- overview 라우트(`/api/v1/alerts/overview`).
- `app/core/error_codes.py` — `ALERT_RULE_NOT_FOUND`·`ALERT_RULE_FORBIDDEN` 추가(기존
  `*_NOT_FOUND`/`*_FORBIDDEN` 패턴). `VALIDATION_ERROR`는 기존 것 재사용.

## Out of Scope

- `alert_events` 도메인·목록/상세/읽음 API (B3 #329).
- `notification_channels` 도메인·API (B4 #330).
- 알림 엔진·스케줄러·실제 이벤트 생성 (B5 #331).
- 기존 `alerts`·`alert_candidates`·`WatchlistAlertRuleService` 흡수·deprecate (B3).
- FE.

## Protected Files

없음. `app/api/v1/router.py`·`app/core/error_codes.py`는 추가만 한다(기존 항목 변경 금지).

## Requirements

1. 템플릿 카탈로그가 §3과 일치(라벨·기본 대상·기본 조건·기본 채널·cooldown·delivery_policy).
2. 조건 검증기가 §4의 단일 조건과 `all`(AND) 배열만 허용, 미지원 조합은 `422`.
3. CRUD·pause/resume·삭제 규칙(SYSTEM 불가)·소유권(`*_FORBIDDEN`)이 정확히 동작.
4. overview 카운트가 규칙·이벤트 테이블을 정확히 집계.
5. projection 명명 규칙 준수, `mypy` 타입 게이트 통과.

## Test Requirements

- API 계약 스냅샷 테스트에 신규 응답 구조 추가(기존 스냅샷 테스트 방식 재사용).
- 템플릿 카탈로그·조건 검증(정상/`422`)·CRUD·pause/resume·SYSTEM 삭제 거부·타인 접근
  `403`·overview 집계 단위/통합 테스트.
- 기존 테스트 회귀 없음.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

- 설계 문서는 정본이므로 수정하지 않는다. 설계와 어긋나면 멈추고 가정을 보고한다.

## ADR Need

불필요(ADR-013·설계 문서로 결정 완료, 본 태스크는 구현).

## Failure Record Need

불필요.

## Risk Level

Medium — 공개 API 계약을 신설하므로 FE(F1·F2)와 조건 검증기·overview 형태가 정합해야 한다.

## Expected Output

- `alert_rules` 도메인 schema/repository/service, 엔드포인트, error_codes 추가, 테스트.
- B2 브랜치에 커밋(자체 브랜치 생성 금지, 오케스트레이터가 지정한 현재 브랜치 유지).
- 검증 3종 통과 보고.

## Rules

- Stay within scope. (규칙 도메인·overview까지. 이벤트·채널·엔진 금지.)
- Do not weaken verification.
- 오케스트레이터가 지정한 현재 브랜치를 유지한다. 새 브랜치를 만들지 않는다.
- Do not modify protected files beyond the additive changes listed.
- Report assumptions and verification results.
