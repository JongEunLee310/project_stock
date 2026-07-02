# Codex Handoff Task

## Source Issue

BE #163 — BE↔FE 응답 계약 불일치 정리(response_model 필드 정렬). 설계: `docs/designs/064-be-fe-contract-alignment.md`. 점검 기록: `docs/reviews/contract-audit-be-fe-2026-07-02.md`.

## Task Summary

BE 응답 스키마 8종을 FE가 기대하는 형태로 정렬한다. 계약 기준은 BE이며, DB 마이그레이션 없이
기존 컬럼·파생값·mock으로 해결한다.

## Goal

완료 시 다음이 참이어야 한다.

- FE `dto.ts`가 기대하는 필드가 각 BE 응답에 존재한다(설계 064 §3~§4의 델타 전부 반영).
- `GET /auth/me`가 `username`·`created_at`을 반환한다.
- `GET /assets/{id}/research-summary`가 `stance`·`stance_confidence`·`headline`·`body`·`key_risks`·`created_at`을 반환한다(factor-list 필드 제거).
- `GET /assets/{id}/buy-checklist` item이 `{id,label,description,checked}` 형태다.
- `GET /assets/{id}/detail`이 `market_cap`·`next_earnings_date`·`updated_at`을 반환한다(`as_of` 제거).
- `GET /reports`·`GET /theses/latest`가 `title`을, `GET /alerts`가 `title`을, `GET /assets`·`GET /assets/{id}`가 `sector`를 반환한다.
- `tests/test_api_contract.py`가 갱신된 계약을 검증하고 전체 테스트가 통과한다.
- ruff·mypy·pytest 3종 모두 통과한다.

## Goal (branch)

최신 `main`에서 feature 브랜치(`feat/be-163-contract-alignment` 권장)를 생성해 작업한다.
브랜치가 `main`보다 뒤처져 있으면 먼저 rebase한다.

## Background

FastAPI `response_model`이 스키마 밖 필드를 제거해 FE가 `undefined`를 받고 화면에 빈 값·기본값이
조용히 표시되는 불일치 8건이 확인되었다. FE DTO·adapter는 이미 목표 형태를 기대하며 fallback으로
방어하고 있어, BE가 목표 형태로 응답하면 FE 변경은 최소화된다. 상세 델타·데이터 출처는 설계
064에 표로 정리되어 있다.

## Implementation Scope

설계 064 §7의 파일 목록을 따른다.

- 스키마: `app/domains/{users,research_summary,decision_checklist,assets,reports,theses,alerts}/schema.py`
- 서비스: 위 도메인의 응답 조립부(`service.py`), `app/api/v1/endpoints/auth.py`의 `/me` 매핑
- provider: `app/adapters/market/base.py`(`QuoteResult`), `app/adapters/market/mock.py`
- 테스트: `tests/test_api_contract.py`(+ 필드 변경으로 깨지는 도메인 테스트 정렬)
- 문서: `docs/api/frontend-api-spec.md`, `docs/api/contract-alignment.md`

## Out of Scope

- FE 저장소 변경(FE #101에서 별도 진행).
- DB 스키마 변경·Alembic 마이그레이션·신규 컬럼 도입.
- research-summary·buy-checklist의 실제 AI/데이터 파이프라인(형태 정렬만, 값은 mock 유지).
- 도메인 규칙·비즈니스 로직 변경(응답 조립부만 조정).
- envelope·pagination 규약 변경.

## Protected Files

없음. `AGENTS.md`, `.codex/config.toml`, `.codex/agents/` 등 보호 파일은 변경하지 않는다.

## Requirements

- 설계 064 §4 표의 필드·타입을 정확히 반영한다.
- 파생값 원칙: `username`=email local-part, report/thesis `title`=`summary` 파생(비어있지 않게),
  alert `title`=기존 파생값(`symbol`/`alert_type`) 조합, `AssetDetail.updated_at`=quote as_of,
  `market_cap`·`next_earnings_date`=quote mock.
- research-summary mock은 `asset.id` 기반 결정적 선택을 유지해 테스트를 안정화한다.
- buy-checklist 쓰기 경로(`BuyChecklistNoteUpdate.checked_item_keys`)는 기존 key 문자열을 유지하고,
  응답 item에서만 `id`/`description`/`checked`로 매핑한다.
- 제거 대상(`ResearchSummarySource`, research-summary factor-list 필드, `as_of`)의 잔여 참조를
  코드·테스트·문서에서 모두 정리한다.
- UtcDatetime 직렬화 규약(Z suffix)을 따른다.

## Test Requirements

- `tests/test_api_contract.py`: `RESEARCH_SUMMARY_CONTRACT`·`ASSET_DETAIL_CONTRACT` 갱신,
  `RESEARCH_SUMMARY_SOURCE_CONTRACT` 제거, openapi 컴포넌트 단언 정리, `/auth/me`·`/reports`·
  `/theses/latest`·`/alerts`·`/assets`·buy-checklist item 계약 단언 추가/보강.
- 필드 변경으로 깨지는 기존 테스트를 갱신하되 검증을 약화하지 않는다.

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/api/frontend-api-spec.md` — 변경된 응답 스키마 반영.
- `docs/api/contract-alignment.md` — BE 측 정렬 결과 반영.
- 설계 064 Status를 구현 완료 시 갱신할지 여부는 리뷰에서 판단.

## ADR Need

불필요. 기존 계약 스냅샷 테스트(설계 041)·envelope 규약을 따르는 필드 정렬로 아키텍처 결정
변경이 없다. 주요 결정(정성 스키마 FE 형태 채택·파생값 정렬)은 설계 064에 기록되어 있다.

## Failure Record Need

불필요.

## Risk Level

Medium. 다수 도메인 응답 스키마를 동시에 변경하고 일부는 필드를 제거(as_of·factor-list)하므로
잔여 참조·계약 테스트 회귀 범위가 넓다. DB 변경이 없어 데이터 위험은 낮다.

## Expected Output

- feature 브랜치 커밋 + PR(base=main). 설계 064·점검 기록 링크 포함.
- ruff·mypy·pytest 통과 로그.
- 가정·파생 규칙 선택(예: title 파생 방식)을 PR 본문에 명시.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
