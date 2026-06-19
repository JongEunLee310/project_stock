# Design: 공통 API 응답 포맷 (Issue #46 / 제목 Issue 26)

프론트엔드가 모든 API 응답을 단일 fetch wrapper로 처리할 수 있도록, 성공·실패·목록 응답을 하나의 envelope 구조로 통일한다. v0.1에서 구현된 기존 엔드포인트 전체를 이 포맷으로 소급 적용한다.

## 응답 Envelope

모든 응답(성공/실패 공통)은 다음 4개 최상위 필드를 가진다.

| 필드 | 타입 | 성공 | 실패 |
|------|------|------|------|
| data | T \| null | 페이로드 | null |
| message | str \| null | 선택(예: 생성 완료) | 사용자 표시용 메시지 |
| error | object \| null | null | `{code, fields?}` (코드 체계는 #47) |
| meta | object \| null | 목록일 때 PageMeta | null |

- 성공 단건: `{data: {...}, message: null, error: null, meta: null}`
- 성공 목록: `{data: [...], message: null, error: null, meta: PageMeta}`
- 실패: `{data: null, message: "...", error: {code, ...}, meta: null}` — error 본문 형식은 Issue #47에서 확정

### PageMeta

| 필드 | 타입 | 설명 |
|------|------|------|
| page | int | 1-base 현재 페이지 |
| size | int | 페이지 크기 |
| total | int | 전체 항목 수 |

## 신규 모듈: app/core/response.py

- `ApiResponse[T]` (Generic, Pydantic v2 `BaseModel`) — 위 4필드. `data` 제네릭.
- `PageMeta` — page, size, total.
- `success(data: T, message: str | None = None) -> ApiResponse[T]` — 단건 성공 래핑.
- `paginated(items: list[T], page: int, size: int, total: int) -> ApiResponse[list[T]]` — 목록 성공 + meta 구성.

에러 envelope 생성은 예외 핸들러(Issue #47)에서 담당하므로 본 모듈은 성공 경로만 책임진다.

## 목록 페이지네이션 규약

- 목록 엔드포인트는 쿼리 파라미터 `page`(기본 1, ≥1), `size`(기본 20, 1~100)를 받는다.
- 응답 `data`는 해당 페이지 항목 배열, `meta`는 PageMeta.
- 정렬/필터 공통 규약은 Issue #36 범위이며 본 이슈에서는 page/size만 도입한다.

## 적용 대상 (전 엔드포인트 ~30개)

| 라우터 | 엔드포인트 | 비고 |
|--------|-----------|------|
| auth | register, login, me | 단건 |
| assets | POST, GET(목록), GET/{id} | 목록 page/size |
| watchlists | POST, GET(목록), POST items, DELETE item | 목록 page/size, 204→envelope 정책 확인 |
| portfolios | POST, GET(목록), summary, check, positions CRUD | 목록 page/size |
| theses | POST, PUT, GET latest, PATCH deactivate | 단건 |
| reports | POST, GET(목록), GET/{id} | 목록 page/size |
| signals | POST, GET(목록), GET/{id} | 목록 page/size |
| alerts | GET(목록), read, dismiss | 목록 page/size |
| job_runs | GET(목록) | 목록 page/size |
| worker | jobs/news, jobs/analysis | 단건 |
| health | GET | envelope 적용 여부 결정 — `/health`와 `/api/v1/health` 모니터링 호환 위해 **제외** |

- `response_model`을 `ApiResponse[기존모델]` 또는 `ApiResponse[list[기존모델]]`로 교체.
- 204 No Content(예: 포지션/관심항목 삭제)는 본문이 없으므로 envelope 미적용 유지하거나 200 + `success(None)`로 통일 — 핸드오프에서 200 통일 방향 검토.
- 루트 `/health`, `/api/v1/health`는 외부 헬스체크 호환을 위해 envelope 미적용(예외).

## 의존성

- 없음(기반 작업). Issue #47(에러 envelope), #48(명세 문서)이 본 설계에 의존.

## 마이그레이션/스키마

- DB 스키마 변경 없음. 순수 응답 직렬화 계층 변경.

## 리스크

- 전 엔드포인트의 응답 계약이 바뀌는 광범위 변경(High 표면적). 다만 프론트엔드 미착수 상태이므로 호환성 파기 허용.
- 기존 API 테스트의 응답 단언이 envelope 기준으로 전면 갱신 필요.
