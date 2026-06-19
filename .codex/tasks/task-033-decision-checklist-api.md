# Codex Handoff Task

## Source Issue

Issue #53 (제목 Issue 33): `[BE] 투자 판단 체크리스트 API 추가`

## Task Summary

충동 매수를 줄이고 투자 판단을 보조하기 위한 매수 전 체크리스트 API를 추가한다. 체크 항목은 규칙 기반으로 산출하고, 사용자 판단 메모를 저장한다. 시스템 방향은 자동매매가 아닌 의사결정 보조다.

## Goal

- 매수 전 체크리스트 조회 API(`GET /api/v1/assets/{asset_id}/buy-checklist`)가 추가된다.
- 체크 항목: 밸류에이션 확인, 최근 뉴스 과열 여부, 포트폴리오 비중 초과 여부, 실적/공시 확인 여부.
- 사용자 판단 메모를 저장하는 구조와 API가 추가된다.
- 체크리스트 완료 여부(`is_complete`)가 응답에 포함된다.

## Background

- 신규 도메인. 기존에 대응 도메인 없음.
- 관련 신호 타입 참고: `app/domains/signals/types.py`의 `OVERHEATED`(뉴스 과열), `RISK_ALERT`(비중 초과) — 체크 항목 산출 시 참고 가능하나 강결합은 피한다.
- 포트폴리오 비중 초과 판단은 기존 `PortfolioService` 집중도 로직(`exceeds_threshold`) 개념을 참조(단, 본 태스크에서 포트폴리오 도메인을 수정하지 않는다).
- 사용자 메모 저장은 영속이 필요 → 신규 테이블 + alembic 마이그레이션.
- 응답 envelope: `app/core/response.py` `success`.
- 글로벌 원칙: 의사결정 보조. 자동 매수/매도 동작을 만들지 않는다.

## Implementation Scope

- `app/domains/decision_checklist/`(신규) — `model.py`(사용자 메모/완료여부 저장), `schema.py`, `repository.py`, `service.py`, `__init__.py`.
  - 모델(권고): `BuyChecklistNote(user_id, asset_id, memo, decided_at?)` + 사용자·종목 단위 유니크 — 또는 항목별 체크 상태 저장이 필요하면 최소 구조로. 과확장 금지.
- `app/api/v1/endpoints/` + `app/api/v1/router.py` — 체크리스트 조회 + 메모 저장(`PUT`/`POST`) 라우트. 인증 Required.
- `app/core/error_codes.py` — 필요 시 `CHECKLIST_NOT_FOUND` 등 신규 코드(최소).
- `alembic/versions/` — 신규 테이블 마이그레이션.
- `docs/designs/033-decision-checklist-api.md` — 스켈레톤 설계문서.

## Out of Scope

- 자동 매매/주문 연동(시스템 방향상 금지).
- 체크 항목의 정교한 산출 로직(밸류에이션 모델 등) — 현재는 규칙 기반 단순 판정 + mock/사용 가능한 기존 데이터.
- 포트폴리오/시그널 도메인 수정.

## Protected Files

변경하지 않는다:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`, `docs/decisions/`

## Requirements

- 체크리스트 응답: 항목별 `{key, label, status, detail?}` 리스트 + 사용자 `memo` + `is_complete`.
  - `is_complete`는 정의를 명확히(권고: 필수 항목이 모두 확인됨 + 메모 존재). PR에 정의 명시.
- 메모 저장은 인증 사용자 본인 종목 단위. 타 사용자 데이터 접근 차단.
- 체크 항목 산출은 외부 키 없이 동작(mock/기존 데이터 활용).
- 신규 테이블 마이그레이션 upgrade/downgrade 작성.
- 시스템은 판단을 "보조"만 — 자동 실행 동작 없음.

## Test Requirements

- 체크리스트 조회가 4개 항목 + 완료여부를 반환하는 테스트.
- 메모 저장 → 재조회 시 반영(왕복) 테스트.
- 타 사용자 메모 접근 차단 테스트.
- `is_complete` 토글 조건 테스트.
- `uv run pytest` 전체 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/designs/033-decision-checklist-api.md` 신규(스켈레톤).
- `docs/api/frontend-api-spec.md`에 매수 전 점검 API 섹션 추가(라우트 체크리스트 포함).

## ADR Need

검토 — 신규 도메인이나 단순 보조 기능. 자동매매 비도입 원칙은 기존 정책과 일치하므로 ADR 불요. 산출 로직이 향후 시그널/엔진과 통합될 경우 후속 ADR 검토.

## Failure Record Need

없음.

## Risk Level

Medium — 신규 도메인 + 테이블 + 마이그레이션. 단 동작은 조회/메모 한정으로 부수효과 작음.

## Expected Output

- 신규 도메인 모듈 + 엔드포인트 + 마이그레이션 + 테스트.
- `uv run pytest`/lint/typecheck 통과.
- PR body에 `Closes #53`.

## Rules

- 자동 매매/주문 동작을 추가하지 않는다.
- 다른 도메인 수정 금지(참조만).
- 보호 파일 변경 금지.
- 가정(특히 `is_complete` 정의)과 검증 결과 보고.
