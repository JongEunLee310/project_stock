# 035 Alert Candidate API

## Scope

실제 푸시/메일 발송 전에 시스템이 감지한 "알림 후보"를 조회·관리하는 API를 제공한다. 신규 영속 도메인 `alert_candidates`로 5개 유형, 중요도, 읽음/확인 상태를 저장한다. 실제 발송 연동과 실시간 감지 엔진은 포함하지 않으며, 기존 `alerts` 도메인(signal→alert 발송 흐름)은 변경하지 않는다.

## Data Model

`alert_candidates` (신규 테이블)

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `user_id` | FK users | Yes | 인증 사용자 |
| `candidate_type` | `String` | Yes | 5개 유형 enum |
| `importance` | `String` | Yes | `LOW`/`MEDIUM`/`HIGH` |
| `status` | `String` | Yes | `UNREAD`/`READ`/`CONFIRMED`, 기본값 `UNREAD` |
| `title` | `String` | Yes | 후보 요약 |
| `message` | `Text` | No | 상세 설명 |
| `asset_id` | FK assets | No | 종목 관련 후보 시 |
| `evidence` | `JSON` | No | 산출 근거 |
| `created_at` / `updated_at` | `DateTime` | Yes | server_default |

## Types

- `AlertCandidateType`: `NEWS_SURGE`, `PRICE_MOVEMENT`, `DISCLOSURE`, `PORTFOLIO_CONCENTRATION`, `BUY_CHECKLIST_REQUIRED`
- `AlertImportance`: `LOW` / `MEDIUM` / `HIGH`
- `AlertCandidateStatus`: `UNREAD` / `READ` / `CONFIRMED`

## API

`GET /api/v1/alert-candidates`

- Auth: Required (본인 것만)
- Query: `candidate_type?`, `importance?`, `status?`, 페이지네이션(`page`, `size`)
- Response: 후보 목록 `{id, user_id, candidate_type, importance, status, title, message?, asset_id?, evidence?, created_at}`

`POST /api/v1/alert-candidates/{id}/read`

- Auth: Required, 상태 → `READ`

`POST /api/v1/alert-candidates/{id}/confirm`

- Auth: Required, 상태 → `CONFIRMED`

## Functions

- `AlertCandidateService.list_candidates(user_id, filters, page, size)` — 본인 후보 필터/페이지 조회.
- `AlertCandidateService.mark_read / confirm(candidate_id, user_id)` — 상태 전이, 타 사용자 접근 시 404.

## Decisions

- 기존 `alerts`와 분리한 신규 도메인 — `alerts`는 signal FK 필수의 발송 흐름이라 더 넓은 후보 개념과 강결합을 피한다(사용자 승인된 분기).
- 후보 산출은 외부 키 없이 mock/시드/테스트로 생성 — 실시간 감지 엔진은 후속 범위.
- signal 유형(`OVERHEATED`, `RISK_ALERT` 등)은 매핑 참고용일 뿐 FK로 강제하지 않는다.
- 실제 발송 부수효과 없음 — 의사결정 보조 원칙 유지.
