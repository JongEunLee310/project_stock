# Codex Handoff Task

## Source Issue

JongEunLee310/project_stock#102 — [계약정렬] decision-log 도메인 신규 (G10/N1)
정본 계약: `docs/designs/decision-log-domain.md` **§6 계약 확정**(2026-06-26, Opus). 결정 근거: `docs/decisions/ADR-006-decision-log-domain.md`.

## Task Summary

의사결정 저널(decision-log) 영속화 도메인을 신설한다. `decision_logs` 테이블 + Alembic 마이그레이션, CRUD 엔드포인트(`GET 목록`/`POST`/`GET {id}`/`PATCH {id}`), 본인 소유권, 신규 에러코드 2종. FE 의사결정 저널 화면의 백엔드 대응(G10/Q7).

## Goal

완료 시 다음이 참이어야 한다:

- `GET·POST /api/v1/decision-logs`, `GET·PATCH /api/v1/decision-logs/{id}` 가 `docs/designs/decision-log-domain.md` §6 계약대로 동작한다.
- `decision_logs` 테이블과 Alembic 마이그레이션이 생성되고 `alembic upgrade head` 가 통과한다.
- 전 엔드포인트 Auth Required, 본인 행만 노출(타인 접근 403, 없음 404).
- `PATCH` 가 `decision_status` 전이 시 `reviewed_at`/`closed_at` 를 규칙대로 스탬프한다(§6.3).
- 신규 에러코드 2종이 명세 HTTP 상태로 매핑된다.
- `frontend-api-spec.md` 와 contract 테스트에 decision-logs 항목이 추가된다.
- 전체 테스트 통과(신규 포함), `TZ=UTC` 에서 시각 단언 통과.

## Background

- 와이어 컨벤션: snake_case, 금액=Decimal **문자열**, 시각=`app/core/schema.py`의 `UtcDatetime`, 공통 엔벨로프 `app/core/response.py`(`success`/`paginated`).
- **참고 구현(이 패턴을 그대로 따른다)**: `app/domains/watchlists/`(user 소유권 CRUD, `_get_owned_*` 403/404 패턴, repository offset/limit/sort, `model_validate`), `app/domains/prices/schema.py`(Decimal→str·`UtcDatetime`), `app/api/v1/endpoints/watchlists.py`(라우터·`get_current_user`·`PaginationParams`·`sort_param`·`paginated`).
- 정렬: `app/core/pagination.py`의 `sort_param(allowed_fields=..., default=...)` 사용.
- 라우터 등록: `app/api/v1/router.py` 에 기존 방식대로 한 줄 추가(prefix `/decision-logs`).
- enum은 문자열 컬럼 + Pydantic `enum`(str, Enum)으로 검증. 정본 값은 §6.4.
- **시각 처리**: `decided_at` 생략 시 서버 `now()`(UTC aware). `reviewed_at`/`closed_at` 는 PATCH 전이 시 스탬프. 모든 datetime 컬럼 `DateTime(timezone=True)`.

## Implementation Scope

- 신규 도메인 `app/domains/decision_logs/`: `model.py`(DecisionLog), `repository.py`(생성·단건·본인목록 offset/limit/sort·count·갱신), `service.py`(소유권 검사·라이프사이클 스탬프·`model_validate`), `schema.py`(`DecisionLogCreate`, `DecisionLogUpdate`, `DecisionLogResponse`), `types.py`(enum 3종: `DecisionType`, `DecisionStatus`, `CreatedBy`).
- 라우터: `app/api/v1/endpoints/decision_logs.py` 신설 + `app/api/v1/router.py` 등록(prefix `/decision-logs`, tags `["decision-logs"]`).
- 에러코드: `app/core/error_codes.py` 에 `DECISION_LOG_NOT_FOUND`, `DECISION_LOG_FORBIDDEN` 추가.
- 마이그레이션: `alembic/versions/` 신규 리비전(`decision_logs`). down_revision 은 현재 head(`c3d4e5f60056`) 확인 후 연결. 컬럼 정의는 §6.2.
- spec: `docs/api/frontend-api-spec.md` 에 decision-logs 섹션 추가(기존 도메인 섹션 포맷 따름).
- 테스트: 전용 신규 파일 + `tests/test_api_contract.py` 에 decision-logs 계약 추가.

## Out of Scope

- forward-only 전이 강제, 스냅샷 typed 스키마/검증, 검색·필터(ticker/status/기간), 정렬 필드 확장, AI 자동생성 연동(모두 §6.6 후속).
- FE 코드, FE 어댑터 매핑.
- 기존 도메인 스키마/엔드포인트 변경.
- `docs/designs/decision-log-domain.md`·`docs/decisions/*` 수정(확정본, 정본 문서).

## Protected Files

없음. `.codex/*`, `.claude/*`, `docs/harness/*`, `docs/decisions/*`, `docs/designs/decision-log-domain.md` 수정 금지(읽기 전용 정본).

## Requirements

- 엔드포인트·소유권·meta: §6.1. 소유권 위반 403(`DECISION_LOG_FORBIDDEN`), 미존재 404(`DECISION_LOG_NOT_FOUND`) — watchlists `_get_owned_watchlist` 패턴 차용.
- 컬럼·타입·제약: §6.2. `Numeric(20,4)`, JSON 컬럼, `cognitive_risks` server_default `[]`, `decision_status` default `OPEN`, `created_by` default `USER`.
- POST/PATCH/응답 스키마: §6.3. `confidence_score` 0~100 범위 밖 422. `target_price`/`stop_loss_price` 입력·출력 모두 Decimal 문자열(prices 패턴).
- enum: §6.4 정본 값. 잘못된 값 422. `cognitive_risks` 자유 string 배열.
- 에러 매핑: §6.5.
- PATCH 라이프사이클 스탬프: §6.3(→REVIEWED & reviewed_at null ⇒ now, →CLOSED & closed_at null ⇒ now, 명시값 우선).

## Test Requirements

- 라우터 통합 테스트(전용 신규 파일 `tests/test_decision_logs.py`): 생성·단건·목록(본인만, 페이지네이션·sort)·PATCH(상태 전이 + 타임스탬프 스탬프)·소유권 403·미존재 404·enum/confidence 검증 422·Decimal 문자열·snake_case 필드 표기.
- `tests/test_api_contract.py`: decision-logs 응답 엔벨로프/필드 타입 계약 추가.
- 시각 단언은 `TZ=UTC` 로 수행(스탬프 타임스탬프 회귀 방지).
- 기존 테스트 무손상.

## Verification Commands

```
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run alembic upgrade head
TZ=UTC uv run pytest
```

## Documentation Impact

- `docs/api/frontend-api-spec.md` 에 decision-logs 섹션 추가(스코프 내).
- `docs/designs/decision-log-domain.md`·`docs/api/contract-alignment.md`·ADR-006 은 수정 불필요(정본/후속 Opus 처리).

## ADR Need

ADR-006(Opus 작성, Proposed) 이미 동반됨. Codex 추가 ADR 불필요. 스냅샷 자유 JSON·라이프사이클·정본 enum 결정은 ADR-006 에 기록됨.

## Failure Record Need

불필요(예상 실패 없음). 마이그레이션/sandbox 충돌 시 보고만.

## Risk Level

Medium — 신규 테이블/마이그레이션(DB 스키마) 포함. **DB 스키마는 human-gate 대상**(human-gate-policy.md, ADR-005 #6)으로 본 task 는 사람 승인 후에만 실행한다.

## Expected Output

- 신규 도메인·라우터·에러코드·마이그레이션·spec·테스트 포함 브랜치(`feat/be-102-decision-log`) 커밋.
- 모든 검증 명령 통과(특히 `alembic upgrade head`, `TZ=UTC pytest`).
- PR 본문에 BE#102 라벨 승계(api, DB, decision-support, frontend-integration, priority:medium).

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- `--dangerously-bypass-approvals-and-sandbox` / `-s danger-full-access` 사용 금지(ADR-005).
