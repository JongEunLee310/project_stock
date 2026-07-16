# Codex Handoff Task

## Source Issue

이슈 #330 (B4) — `notification_channels` 도메인·채널 관리 API. 에픽 #327.
`gh issue view 330`, `gh issue view 327`로 맥락을 읽는다. 설계 정본은
`docs/designs/alert-rule-event-unified.md`(§1.4·§8). 모델·enum은 B1이 제공한다
(`app/domains/notification_channels/model.py`, `AlertChannel` in `alert_rules/types.py`).

## Task Summary

B1의 `NotificationChannel` 모델 위에 스키마·리포지토리·서비스·엔드포인트를 얹어 채널 목록·추가
API를 구현한다. MVP는 `APP` 채널을 사용자별 기본 1건으로 보장하고, `EMAIL`은 미검증
placeholder까지만 허용한다. 외부 발송 어댑터·테스트 발송은 범위 밖(2차).

## Goal

- `GET /api/v1/notification-channels` — 사용자 채널 목록. `APP` 기본 채널이 없으면 보장(자동
  생성 또는 조회 시 기본 포함)하여 항상 최소 `APP` 1건이 나온다.
- `POST /api/v1/notification-channels` — 채널 추가. MVP 허용: `APP`(중복 불가)·`EMAIL`
  (configuration에 이메일 주소, `verified_at=None` placeholder). `DISCORD`·`SLACK`은 `422`로
  거부(2차).
- 소유권 `user_id` 기준, 타인 접근 `NOTIFICATION_CHANNEL_FORBIDDEN`(403), 없음
  `NOTIFICATION_CHANNEL_NOT_FOUND`(404).

## Background

도메인 구성은 B2·B3와 동일 관례: `app/domains/notification_channels/`의 `schema.py`·
`repository.py`·`service.py`(model.py는 B1 제공), 엔드포인트는
`app/api/v1/endpoints/notification_channels.py`에 두고 `app/api/v1/router.py`에
`include_router(prefix="/notification-channels", tags=["notification-channels"])` 등록. 인증·
소유권 의존성은 기존 `app/api/v1/deps.py` 재사용.

`APP` 기본 채널 보장 방식은 조회 시점 lazy 생성(없으면 만들어 반환)이나 사용자 생성 훅 중
코드에 자연스러운 쪽을 택하되, MVP에서는 `GET`에서 없으면 생성해 반환하는 것으로 충분하다.

## Implementation Scope

- `app/domains/notification_channels/schema.py` — `NotificationChannelProjection`·추가 요청
  스키마(파생 뷰는 'projection' 명명).
- `app/domains/notification_channels/repository.py` — 소유 목록·조회·생성·`APP` 존재 확인.
- `app/domains/notification_channels/service.py` — 목록(APP 기본 보장)·추가(채널별 검증)·
  소유권 검사.
- `app/api/v1/endpoints/notification_channels.py` — 라우터. `router.py` 등록.
- `app/core/error_codes.py` — `NOTIFICATION_CHANNEL_NOT_FOUND`·`NOTIFICATION_CHANNEL_FORBIDDEN`
  추가.

## Out of Scope

- 외부 발송 어댑터(EMAIL/DISCORD/SLACK 실제 전송)·`POST .../{id}/test`(테스트 발송) — 2차.
- `DISCORD`·`SLACK` 채널 추가 허용 — 2차(현재는 `422`).
- `AlertDelivery` 생성(엔진 B5). 채널은 규칙·엔진과 독립.
- FE.

## Protected Files

없음. `app/api/v1/router.py`·`app/core/error_codes.py`는 추가만.

## Requirements

1. `GET`이 항상 최소 `APP` 1건을 포함해 반환.
2. `POST`가 `APP`(중복 불가)·`EMAIL`(placeholder) 허용, `DISCORD`·`SLACK`은 `422`.
3. 소유권 403/404 처리.
4. projection 명명·`mypy` 게이트 통과.

## Test Requirements

- `GET` 기본 `APP` 보장·목록, `POST` 채널별 허용/거부(`APP` 중복·`EMAIL` placeholder·
  `DISCORD`/`SLACK` 422), 소유권 단위/통합 테스트.
- API 계약 스냅샷 테스트에 신규 응답 구조 추가.
- 기존 테스트 회귀 없음.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

- 설계 정본은 임의 변경 금지. 어긋나면 멈추고 가정을 보고한다.

## ADR Need

불필요.

## Failure Record Need

불필요.

## Risk Level

Low — 독립적 소규모 도메인. 규칙·이벤트·엔진과 결합 없음.

## Expected Output

- `notification_channels` 도메인 schema/repository/service, 엔드포인트, error_codes, 테스트.
- 지정된 현재 브랜치에 커밋(자체 브랜치 생성 금지).
- 검증 3종 통과 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- 지정된 현재 브랜치를 유지한다. 새 브랜치 금지.
- Report assumptions and verification results.
