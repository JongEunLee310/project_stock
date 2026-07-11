# Codex Handoff Task

## Source Issue

#267 — BE: research-summary 구조화 확장 — 스탠스 코멘트·긍정/주의/다음 확인 불릿·신뢰도 근거
`gh issue view 267`

설계 문서: `docs/designs/267-research-summary-structure.md` (반드시 먼저 읽는다)

## Task Summary

`GET /api/v1/assets/{asset_id}/research-summary` 응답을 구조화한다.
`ResearchSummaryResponse`에 `stance_comment`·`positive_factors`·
`caution_factors`·`next_checks`·`confidence_basis`를, `ResearchRisk`에
`evidence`를 추가하고, mock 템플릿 두 벌에 한국어 콘텐츠를 채운다.
기존 필드·엔드포인트·로테이션 방식은 바꾸지 않는다.

## Goal

작업 완료 시 다음 상태여야 한다.

- 신규 필드가 전부 기본값 있는 optional로 추가되어 기존 소비처가 깨지지
  않는다 (기존 테스트 무수정 통과).
- 두 템플릿 모두 신규 필드가 비어 있지 않은 한국어 콘텐츠로 채워진다:
  불릿 각 2~3개, `stance_comment`·`confidence_basis` 각 1문장, key_risks
  항목별 `evidence` 1~2개. 톤은 기존 템플릿과 같은 점검 유도형.
- 같은 asset_id에 대한 응답이 결정적으로 동일하다.
- `uv run ruff check .`, `uv run mypy .`, `uv run pytest`가 전부 통과한다.

## Background

- 스키마: `app/domains/research_summary/schema.py`
  (`ResearchSummaryResponse`, `ResearchRisk`).
- 서비스: `app/domains/research_summary/service.py`
  (`_SummaryTemplate` TypedDict, `_SUMMARY_TEMPLATES`, `get_summary`).
- 필드명 `positive_factors`는 reports 도메인과 동일 리터럴 재사용이고,
  주의 축은 `caution_factors`로 확정됐다 (설계 문서 참조 — reports의
  `negative_factors`와 의미가 달라 일치시키지 않는다).
- DB·마이그레이션 없음.

현재 브랜치 `feat/267-research-summary-structure`에서 그대로 작업한다.
새 브랜치를 만들지 않는다.

## Implementation Scope

**갱신**
- `app/domains/research_summary/schema.py`
- `app/domains/research_summary/service.py`
- 관련 테스트 (`tests/` 아래 research_summary 관련 파일) — 아래 Test
  Requirements 추가.

**변경 불가**
- `app/api/v1/endpoints/assets.py` (엔드포인트 시그니처 변경 없음)
- 다른 도메인 (reports·signals 등)
- alembic (마이그레이션 없음)

## Test Requirements

- 기존 research-summary 테스트가 수정 없이 통과한다.
- 두 템플릿 각각: 신규 필드 5종이 비어 있지 않게 반환되고 key_risks 각
  항목에 `evidence`가 있다.
- 결정성: 같은 asset_id 두 번 호출 시 동일 응답.

## Rules

- 커밋은 1개로 만든다. push는 하지 않는다.
- 커밋 메시지는 한국어 `type: 본문` 형식으로 작성한다.
- 필요하지 않은 추상화를 추가하지 않는다.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`
