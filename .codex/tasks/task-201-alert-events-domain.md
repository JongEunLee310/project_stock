# Codex Handoff Task

## Source Issue

이슈 #329 (B3) — `alert_events` 도메인·최근 알림 목록/상세/읽음. 에픽 #327.
`gh issue view 329`, `gh issue view 327`로 맥락을 읽는다. 설계 정본은
`docs/designs/alert-rule-event-unified.md`(§1.2·§7·§8). 모델·enum은 B1이, 규칙·overview는
B2(#328, 머지됨)가 제공한다.

## Task Summary

B1의 `AlertEvent`/`AlertDelivery` 모델 위에 스키마·리포지토리·서비스·엔드포인트를 얹어 최근
알림 목록/상세(근거)/읽음 API를 구현한다. **구 엔드포인트 병존 유지 결정**에 따라 기존
`/alerts`(시그널 래퍼)·`/alert-candidates`는 건드리지 않고, 신규 이벤트 API는 별도 경로
`/alert-events`로 추가한다.

## Goal

- `GET /api/v1/alert-events` — 목록(필터: severity·read·target_type, 공통 pagination/sort).
- `GET /api/v1/alert-events/{alert_event_id}` — 상세(발생 조건·현재값·임계값·이전값·근거).
- `POST /api/v1/alert-events/{alert_event_id}/read` — 단건 읽음.
- `POST /api/v1/alert-events/read` — 다건 읽음(`alert_ids`).
- 소유권 `user_id` 기준, 타인 접근 `ALERT_EVENT_FORBIDDEN`(403), 없음 `ALERT_EVENT_NOT_FOUND`(404).
- 구 `/alerts`·`/alert-candidates`·그 소비처(FE 현행 알림함)는 무변경으로 계속 동작.

## Background

전환 정책은 "계약 병존"이다(설계 §7). 구 시그널 래퍼 `/alerts`와 `/alert-candidates`는 FE F
시리즈가 신규로 이관을 마칠 때까지 그대로 두고, 신규 이벤트 API는 `/alert-events`로 나란히
추가한다. 설계 §8은 이벤트 목록을 `/alerts`로 적었으나, 병존 유지 결정에 따라 신규 경로를
`/alert-events`로 조정한다 — 본 태스크에서 설계 §7·§8의 해당 문구도 이 결정에 맞게 갱신한다
(구 `/alerts`=deprecated 유지, 신규=`/alert-events`). overview는 B2가 이미 `/alerts/overview`에
두었고 그대로 둔다.

도메인 구성은 B2(`alert_rules`)와 동일한 관례를 따른다: `app/domains/alert_events/`의
`schema.py`·`repository.py`·`service.py`(model.py·types.py는 B1 제공), 엔드포인트는
`app/api/v1/endpoints/alert_events.py`에 두고 `app/api/v1/router.py`에
`include_router(prefix="/alert-events", tags=["alert-events"])` 등록. 인증·소유권·pagination
의존성은 기존 `app/api/v1/deps.py` 재사용.

## Implementation Scope

- `app/domains/alert_events/schema.py` — `AlertEventProjection`(목록용)·
  `AlertEventDetailProjection`(상세: triggered_value·evidence 포함)·읽음 요청 스키마
  (파생 뷰는 'projection' 명명).
- `app/domains/alert_events/repository.py` — 소유 조회·필터 목록·count·단건/다건 읽음 처리
  (`read_at` 세팅).
- `app/domains/alert_events/service.py` — 목록/상세/읽음 오케스트레이션, 소유권 검사.
- `app/api/v1/endpoints/alert_events.py` — 라우터. `app/api/v1/router.py` 등록.
- `app/core/error_codes.py` — `ALERT_EVENT_NOT_FOUND`·`ALERT_EVENT_FORBIDDEN` 추가.
- `docs/designs/alert-rule-event-unified.md` — §7·§8의 신규 이벤트 경로를 `/alert-events`로,
  구 `/alerts`를 deprecated-유지로 문구 갱신(정본 동기화).

## Out of Scope

- 구 `alerts`·`alert_candidates` 도메인·엔드포인트 수정·삭제(병존 유지). deprecate 제거는 후속.
- `AlertEvent` 실제 생성(엔진 B5 #331). 본 태스크는 조회·읽음까지이며, 테스트는 직접 seed한
  이벤트로 검증한다.
- `notification_channels`(B4), 알림 엔진(B5).
- FE.

## Protected Files

없음. `app/api/v1/router.py`·`app/core/error_codes.py`는 추가만. 구 `alerts.py`·
`alert_candidates.py`는 수정 금지.

## Requirements

1. 목록 필터(severity·read·target_type)·pagination·정렬(`-triggered_at` 기본)이 동작.
2. 상세가 triggered_value·evidence를 포함해 반환.
3. 단건/다건 읽음이 `read_at`을 세팅하고, 타인 이벤트는 403.
4. 구 `/alerts`·`/alert-candidates` 응답·동작 회귀 없음.
5. projection 명명·`mypy` 타입 게이트 통과.

## Test Requirements

- 직접 seed한 `AlertEvent`로 목록 필터·상세·단건/다건 읽음·소유권(403/404) 단위/통합 테스트.
- API 계약 스냅샷 테스트에 신규 `/alert-events` 응답 구조 추가.
- 기존 `/alerts`·`/alert-candidates` 계약 테스트 회귀 없음.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

- 설계 §7·§8 문구를 병존 결정에 맞게 갱신(위 Scope 참조). 그 외 설계는 정본이므로 임의 변경
  금지.

## ADR Need

불필요(ADR-013·설계로 결정 완료).

## Failure Record Need

불필요.

## Risk Level

Medium — 신규 조회 API 계약(FE F3와 정합) + 구 계약 병존 유지가 핵심.

## Expected Output

- `alert_events` 도메인 schema/repository/service, `/alert-events` 엔드포인트, error_codes,
  설계 문구 갱신, 테스트.
- 오케스트레이터가 지정한 현재 브랜치에 커밋(자체 브랜치 생성 금지).
- 검증 3종 통과 보고.

## Rules

- Stay within scope. 구 `/alerts`·`/alert-candidates`는 건드리지 않는다.
- Do not weaken verification.
- 지정된 현재 브랜치를 유지한다. 새 브랜치 금지.
- Report assumptions and verification results.
