# Codex Handoff Task

## Source Issue

Issue #52 (제목 Issue 32): `[BE] 종목 리서치 요약 API 추가`

## Task Summary

종목별 뉴스/공시/실적/리스크를 요약해 제공하는 리서치 요약 API의 기본 구조를 만든다. LLM 연동 전에도 동작하도록 Mock 요약 데이터를 제공한다.

## Goal

- 종목별 리서치 요약 조회 API(`GET /api/v1/assets/{asset_id}/research-summary`)가 추가된다.
- 응답에 주요 긍정 요인, 주요 부정 요인, 확인 필요 항목, 데이터 출처 목록, 마지막 갱신 시각이 포함된다.
- LLM 없이 Mock 요약 데이터로 동작한다.
- 존재하지 않는 종목은 `404 ASSET_NOT_FOUND`.

## Background

- 기존 `reports` 도메인(`app/domains/reports/`)은 **개별 리서치 리포트**(positive/negative_factors, risk_level, thesis_conflict)를 다룬다. 본 이슈는 종목 단위 **요약 카드**로 성격이 다르다 — 별도 경량 구조로 추가한다.
- 요약 출처는 향후 news/disclosure/report 집계로 대체될 자리. 현재는 Mock 상수 데이터로 채운다(LLM·집계 로직 미구현).
- 어댑터 패턴 참고: mock 데이터는 결정적(deterministic)으로 반환(`MockMarketDataProvider`/`MockNewsAdapter` 스타일).
- 응답 envelope: `app/core/response.py` `success`(단건).
- 권고 위치: 신규 도메인 `app/domains/research_summary/` 또는 기존 `app/domains/analysis/`에 schema+service 추가(모델/DB 불필요 — mock 반환). 과확장 금지, DB 테이블 만들지 않는다.

## Implementation Scope

- `app/domains/research_summary/`(또는 `analysis/`) — `schema.py`(요약 응답), `service.py`(asset 존재 검증 + mock 요약 반환). 신규 디렉토리면 `__init__.py` 포함.
- Mock 요약 데이터(상수 또는 `sample_data.py`) — 결정적. asset_id/symbol에 따라 안정적으로 매핑.
- `app/api/v1/endpoints/` — `GET /assets/{asset_id}/research-summary` 라우트(assets 엔드포인트에 추가하거나 신규 라우터 등록). 인증 정책은 기존 reports와 동일(Required) 권고.
- `app/api/v1/router.py` — 신규 라우터 추가 시 등록.
- `docs/designs/032-research-summary-api.md` — 스켈레톤 설계문서.

## Out of Scope

- 실제 LLM 요약 생성·뉴스/공시 집계 로직.
- 요약 영속화(DB 테이블/마이그레이션) — mock 반환만.
- reports/theses 도메인 변경.

## Protected Files

변경하지 않는다:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`, `docs/decisions/`

## Requirements

- 응답 필드: `asset_id`, `positive_factors: list[str]`, `negative_factors: list[str]`, `items_to_verify: list[str]`(확인 필요 항목), `sources: list[...]`(출처: 최소 라벨/URL 또는 type), `updated_at`(마지막 갱신 시각).
- Mock 데이터는 결정적 — 동일 입력에 동일 출력.
- 존재하지 않는 `asset_id` → `404 ASSET_NOT_FOUND`(asset 존재를 먼저 검증).
- LLM/외부 호출 없음 — 외부 키 없이 기동·동작.

## Test Requirements

- 등록 종목에 대해 요약 응답의 모든 필드가 채워져 반환되는 테스트.
- 동일 입력 반복 시 동일 결과(결정성) 테스트.
- 존재하지 않는 asset_id → `404 ASSET_NOT_FOUND`.
- `uv run pytest` 전체 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/designs/032-research-summary-api.md` 신규(스켈레톤).
- `docs/api/frontend-api-spec.md` 리서치요약 섹션에 신규 API 반영(라우트 체크리스트 포함).

## ADR Need

없음 — mock 기반 신규 조회 API. 단, 향후 LLM/집계 연동 시 데이터 소스 설계는 후속 이슈에서 ADR 검토.

## Failure Record Need

없음.

## Risk Level

Low — DB 변경 없음, mock 반환 신규 엔드포인트.

## Expected Output

- 스키마/서비스/엔드포인트 + mock 데이터 + 테스트.
- `uv run pytest`/lint/typecheck 통과.
- PR body에 `Closes #52`.

## Rules

- DB 테이블/마이그레이션 만들지 않는다.
- LLM/외부 호출 추가 금지.
- 보호 파일 변경 금지.
- 가정과 검증 결과 보고.
