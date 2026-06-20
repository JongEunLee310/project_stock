# 041 API Contract Snapshot Tests

## Scope

프론트엔드와 약속한 응답 구조가 의도치 않게 바뀌지 않도록 contract(스냅샷) 테스트를 추가한다. 주요 API의 응답 schema(필수 필드·타입)를 고정하고, 필수 필드 누락이나 타입 변경을 테스트가 감지하도록 한다. OpenAPI schema를 확인하고, contract 변경 시 검토 기준과 프론트 영향 범위 확인 절차를 문서화한다. #40(API 테스트)이 동작을 보장한 뒤, 본 작업이 응답 구조를 고정한다.

## Current State

- 응답 envelope: `app/core/response.py`의 `ApiResponse{data, message, error, meta}`, `PageMeta{page, size, total}`.
- FastAPI가 `/openapi.json` 자동 제공(앱 기동 시). 별도 contract 고정 장치는 없음.
- `docs/api/frontend-api-spec.md`에 구현 API 카탈로그 존재(응답 구조 서술).

## Approach

| 항목 | 내용 |
| --- | --- |
| Schema 고정 대상 | 프론트 직접 연동 API: watchlist, stock detail, research summary, portfolio summary, alert candidate(목록 포함) |
| 필수 필드 검증 | 응답 data의 필수 키 존재 + 타입 단언. 누락/타입 변경 시 실패 |
| OpenAPI 확인 | `/openapi.json`(또는 `app.openapi()`) 응답에서 주요 경로/스키마 존재 확인 |
| 변경 절차 | contract 변경 시 검토 기준·프론트 영향 범위 확인 절차 문서화 |

## Functions

- `tests/test_api_contract.py`(신규) — 주요 API 응답의 필수 필드·타입을 고정하는 테스트. 직접 키/타입 단언 방식(외부 스냅샷 라이브러리 미도입) 또는 expected schema dict 비교.
- OpenAPI 확인 테스트 — `app.openapi()` 결과에서 핵심 경로와 응답 컴포넌트 존재 검증.
- 문서(`docs/api/frontend-api-spec.md` 또는 신규 절) — "Contract 변경 검토 기준"과 "프론트 영향 범위 확인 절차" 추가.

## Decisions

- 외부 스냅샷 도구(syrupy 등) 도입 여부는 핸드오프에서 결정 — 기본은 명시적 키/타입 단언으로 시작해 의존성 추가를 최소화한다.
- contract 테스트는 응답 **구조**만 고정한다 — 값(데이터 내용)까지 고정하지 않아 시드/시간 의존 깨짐을 피한다.
- 필수 필드 변경은 의도적 contract 변경으로 간주 — 테스트 수정 시 문서의 검토 기준 절차를 따르도록 명문화.
