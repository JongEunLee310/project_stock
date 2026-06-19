# Codex Handoff Task

## Source Issue

Issue #55 (제목 Issue 35): `[BE] 알림 후보 API 추가`

## Task Summary

실제 푸시/메일 발송 전에 시스템이 감지한 "알림 후보"를 조회·관리하는 API를 추가한다. 신규 영속 도메인 `alert_candidates`를 만들어 5개 알림 유형과 중요도, 읽음/확인 상태를 저장한다. 기존 `alerts` 도메인(signal→alert 발송 흐름)은 변경하지 않는다.

## Goal

- 알림 후보 목록 조회 API(`GET /api/v1/alert-candidates`)가 추가된다(인증 사용자 본인 것만, 페이지네이션, 유형/중요도/상태 필터).
- 알림 유형 5종 지원: 뉴스 급증, 가격 변동, 공시 발생, 포트폴리오 비중 초과, 매수 전 점검 필요.
- 중요도 필드(예: LOW/MEDIUM/HIGH)가 응답에 포함된다.
- 읽음/확인 처리 API가 추가된다(상태: UNREAD → READ → CONFIRMED).
- 실제 푸시/메일 발송 없이 알림 흐름을 검증할 수 있다.

## Background

- **설계문서 우선 확인**: `docs/designs/035-alert-candidate-api.md`(Claude Code 작성, 스켈레톤)를 먼저 읽고 그 Data Model/Types/API/Decisions를 따른다. 구현 중 설계와 달라지면 설계문서를 함께 갱신한다.
- 사용자 결정: **신규 영속 도메인**. 기존 `alerts` 확장이 아님.
- 기존 `alerts` 도메인(`app/domains/alerts/`)은 `signal_id` FK 필수 + dedup + UNREAD/READ/DISMISSED + read/dismiss API를 가진다. 본 태스크는 이를 **수정하지 않고**, 더 넓은 "후보" 개념을 별도 도메인으로 구현한다.
- 도메인 모듈 구조는 기존 패턴(`model.py`/`schema.py`/`repository.py`/`service.py`/`types.py`/`__init__.py`)을 따른다. 참고: `app/domains/alerts/`.
- 알림 유형/중요도/상태는 `types.py`에 Enum으로 정의(`app/domains/alerts/types.py`의 `AlertStatus` 패턴 참조).
- 후보 데이터 산출은 외부 키 없이 동작해야 한다 — mock/기존 데이터 기반 시드 또는 테스트 fixture로 후보를 생성. 실시간 감지 파이프라인 연결은 범위 외.
- 신호 유형 참고(강결합 금지): `app/domains/signals/types.py`의 `OVERHEATED`(뉴스 과열), `RISK_ALERT`(비중 초과) 등 — 매핑 참고용일 뿐 signal FK로 강제하지 않는다.
- 응답 envelope: `app/core/response.py` `success`/`paginated`. 목록 페이지네이션은 `app/api/v1/endpoints/alerts.py` 패턴 참조.
- 글로벌 원칙: 의사결정 보조. 실제 발송 동작은 만들지 않는다.

## Implementation Scope

- `app/domains/alert_candidates/`(신규) — `model.py`, `schema.py`, `repository.py`, `service.py`, `types.py`, `__init__.py`.
  - 모델(권고): `AlertCandidate(user_id, candidate_type, importance, status, title/message, asset_id?(nullable), evidence?(JSON), created_at, updated_at)`. 과확장 금지 — 위 필드 범위 내 최소 구성.
  - `types.py`: `AlertCandidateType`(5종), `AlertImportance`(LOW/MEDIUM/HIGH), `AlertCandidateStatus`(UNREAD/READ/CONFIRMED).
- `app/api/v1/endpoints/alert_candidates.py`(신규) + `app/api/v1/router.py` 등록(prefix `/alert-candidates`, tags `alert-candidates`).
  - `GET /alert-candidates` — 목록(유형/중요도/상태 필터 + 페이지네이션), 인증 Required.
  - 읽음 처리: `POST /alert-candidates/{id}/read`.
  - 확인 처리: `POST /alert-candidates/{id}/confirm`.
- `app/core/error_codes.py` — `ALERT_CANDIDATE_NOT_FOUND`(최소) 추가.
- `alembic/versions/` — `alert_candidates` 테이블 마이그레이션(upgrade/downgrade). 참고: `9c0d1e23f405_create_alerts.py`.
- `docs/designs/035-alert-candidate-api.md` — 기존 스켈레톤 설계문서. 설계와 구현이 달라지면 갱신.
- `docs/api/frontend-api-spec.md` — 알림 후보 API 섹션 추가.

## Out of Scope

- 실제 푸시/이메일 발송 연동(시스템 방향상 금지).
- 기존 `alerts` 도메인 및 analysis 파이프라인 수정.
- 실시간 후보 감지 엔진/스케줄러 구현(후보는 mock/시드/테스트로 생성).
- signals 도메인 수정.

## Protected Files

변경하지 않는다:

- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`, `docs/decisions/`

## Requirements

- 알림 후보 응답: `{id, candidate_type, importance, status, title/message, asset_id?, created_at}` + 필요한 메타.
- 5개 유형 enum이 모두 표현 가능.
- 목록은 본인 데이터만, 유형/중요도/상태 필터 + 페이지네이션 지원.
- 상태 전이: UNREAD → READ(read API), → CONFIRMED(confirm API). 타 사용자 데이터 접근 차단(404).
- 후보 산출/시드는 외부 키 없이 동작.
- 신규 테이블 마이그레이션 upgrade/downgrade 작성.
- 실제 발송 부수효과 없음.

## Test Requirements

- 목록 조회 + 유형/중요도/상태 필터 + 페이지네이션 테스트.
- 5개 유형 표현 가능 확인 테스트.
- read/confirm 상태 전이 왕복 테스트.
- 타 사용자 후보 접근 차단(404) 테스트.
- `tests/test_alert_candidates.py`(신규) 추가, `uv run pytest` 전체 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/designs/035-alert-candidate-api.md` 참고 및 필요 시 갱신(Claude Code가 스켈레톤 작성 완료).
- `docs/api/frontend-api-spec.md`에 알림 후보 API 섹션 추가(라우트/필터/상태 전이 포함).

## ADR Need

검토 — 기존 `alerts`와 별도로 `alert_candidates` 도메인을 신설하는 결정. 사용자 승인된 분기이며 기존 흐름과 충돌 없음. 향후 두 도메인 통합/실시간 감지 연동 시 후속 ADR 검토 권장(설계문서에 분리 사유 명시).

## Failure Record Need

없음.

## Risk Level

Medium — 신규 도메인 + 테이블 + 마이그레이션. 동작은 조회/상태변경 한정, 기존 alerts 미변경으로 부수효과 작음.

## Expected Output

- 신규 `alert_candidates` 도메인 모듈 + 엔드포인트 + 마이그레이션 + 테스트.
- `uv run pytest`/lint/typecheck 통과.
- PR body에 `Closes #55`.

## Rules

- 실제 알림 발송 동작을 추가하지 않는다.
- 기존 `alerts`/signals/analysis 파이프라인 수정 금지(참조만).
- 보호 파일 변경 금지.
- 가정(유형↔신호 매핑, 중요도 산출 방식, 시드 출처)과 검증 결과 보고.
