# Codex Handoff Task

## Source Issue

Issue #55 (제목 Issue 35): `[BE] 알림 후보 API 추가`

## Task Summary

실제 푸시/메일 발송 전에 시스템이 감지한 "알림 후보"를 조회·확인할 수 있는 API를 추가한다. 알림 후보는 유형과 중요도를 가지며 읽음/확인 처리가 가능하다.

## Goal

- 알림 후보 목록 조회 API(`GET /api/v1/alert-candidates`)가 추가된다.
- 알림 유형: 뉴스 급증, 가격 변동, 공시 발생, 포트폴리오 비중 초과, 매수 전 점검 필요.
- 각 후보에 중요도(severity) 필드가 포함된다.
- 읽음/확인 처리 API가 추가된다.
- 실제 발송 없이 알림 흐름을 검증할 수 있다.

## Background

- 기존 `alerts` 도메인(`app/domains/alerts/`)은 **확정 알림**(signal 기반, status UNREAD/READ/DISMISSED, read/dismiss 동작)을 다룬다. `Alert(user_id, signal_id, status, dedup_key)`.
- frontend-api-spec의 미구현 후보 항목: "시그널에서 알림 후보를 생성/승인하는 전용 API". 본 이슈가 이를 구체화한다.
- 설계 선택(PR에 명시):
  - (A) 신규 도메인 `alert_candidates`(자체 테이블) — 유형/중요도/확인여부 보관.
  - (B) 기존 `alerts` 확장 — 유형/중요도 컬럼 추가.
  - 권고: **(A) 신규 도메인** — 확정 알림과 후보의 라이프사이클이 다르고, 기존 alerts 동작 보존이 안전.
- 유형 매핑 참고: `app/domains/signals/types.py`(`OVERHEATED`=뉴스 과열, `RISK_ALERT`=비중 초과 등) — 후보 유형 enum 설계 시 참고.
- 응답 envelope: `success`/`paginated`. 목록은 `meta{page,size,total}`. 신규 에러는 `ErrorCode`에 추가.
- DB는 alembic.

## Implementation Scope

- `app/domains/alert_candidates/`(권고 신규) — `model.py`, `types.py`(유형 enum, severity enum), `schema.py`, `repository.py`, `service.py`, `__init__.py`.
  - 모델(권고): `AlertCandidate(user_id, candidate_type, severity, status[UNREAD/READ], asset_id?, signal_id?, payload?, created_at)`.
- `app/api/v1/endpoints/` + `app/api/v1/router.py` — 목록 조회(유형/중요도/상태 필터 + 페이지네이션), 읽음/확인 처리(`POST /alert-candidates/{id}/read`). 인증 Required.
- `app/core/error_codes.py` — `ALERT_CANDIDATE_NOT_FOUND` 등 신규 코드.
- `alembic/versions/` — 신규 테이블 마이그레이션.
- (선택) mock 후보 시드 데이터 — 흐름 검증용 결정적 샘플(상수/시드 서비스). 발송은 하지 않는다.
- `docs/designs/035-alert-candidate-api.md` — 스켈레톤 설계문서.

## Out of Scope

- 실제 푸시/이메일 발송.
- 후보→확정 알림 자동 승인 파이프라인(별도 후속).
- 기존 `alerts` 도메인 동작 변경(참조만, 컬럼/경로 불변).

## Protected Files

변경하지 않는다:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`, `docs/decisions/`

## Requirements

- `candidate_type` enum: 뉴스 급증 / 가격 변동 / 공시 발생 / 포트폴리오 비중 초과 / 매수 전 점검 필요(5종).
- `severity` enum: 최소 LOW/MEDIUM/HIGH.
- 목록은 인증 사용자 본인 후보만. 필터(type/severity/status) + 페이지네이션.
- 읽음/확인 처리는 본인 후보만(타 사용자 → 404 또는 forbidden, 일관 정책 명시).
- 발송 부수효과 없음 — 상태 전이만.
- 신규 테이블 마이그레이션 upgrade/downgrade 작성.

## Test Requirements

- 후보 목록 조회 + 유형/중요도/상태 필터 + 페이지네이션 테스트.
- 읽음 처리 → 상태 전이/재조회 반영 테스트.
- 타 사용자 후보 접근 차단 테스트.
- 존재하지 않는 후보 → `ALERT_CANDIDATE_NOT_FOUND`.
- `uv run pytest` 전체 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/designs/035-alert-candidate-api.md` 신규(스켈레톤).
- `docs/api/frontend-api-spec.md` 알림후보 섹션에 신규 API 반영 + 미구현 후보 표에서 제거(라우트 체크리스트 포함).

## ADR Need

검토 — 신규 도메인. 단 alerts와 분리하는 설계 선택은 경량이라 ADR 없이 PR에 근거 기록으로 충분. 후보→확정 파이프라인 도입 시 후속 ADR.

## Failure Record Need

없음.

## Risk Level

Medium — 신규 도메인 + 테이블 + 마이그레이션. 발송 부수효과 없어 영향 제한적.

## Expected Output

- 신규 도메인 모듈 + 엔드포인트 + 마이그레이션 + (선택) 시드 + 테스트.
- `uv run pytest`/lint/typecheck 통과.
- PR body에 `Closes #55`.

## Rules

- 실제 발송 동작을 추가하지 않는다.
- 기존 alerts 도메인 변경 금지(참조만).
- 설계 선택(A/B)과 근거를 PR에 명시.
- 보호 파일 변경 금지. 가정과 검증 결과 보고.
