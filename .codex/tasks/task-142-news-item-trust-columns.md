# Codex Handoff Task

## Source Issue

- BE #205 — `NewsItem`에 `trust_level`·`content_hash` nullable 컬럼 추가
- Epic BE #141
- 설계: `docs/designs/078-news-pipeline-completion.md` Part A (§2·§3.1–3.3·§5)

## Task Summary

`NewsItem` 모델에 `trust_level`·`content_hash` 컬럼을 nullable로 추가하고, alembic
migration 1건을 수기 작성한다. `NewsItemCreate`·`NewsItemResponse` 스키마에 optional
필드를 반영하고, `ContextBuilder._recent_news_item_from_model`의 신뢰도 값 취득 방식을
저장값 우선·상수 fallback으로 변경한다.

## Goal

- `NewsItem` 테이블에 `trust_level`(varchar 20)·`content_hash`(varchar 64) 컬럼이 존재하고
  nullable이다.
- `uv run alembic heads` 결과가 단일 head를 유지한다.
- `ContextBuilder`가 `news_item.trust_level`이 존재하면 저장값을, 없으면
  `_DEFAULT_NEWS_TRUST_LEVEL`을 사용한다.
- 검증 4종(ruff·mypy·pytest·alembic heads)이 전부 통과한다.

## Background

- 현재 `_recent_news_item_from_model`은 신뢰도 값으로 `_DEFAULT_NEWS_TRUST_LEVEL` 상수를
  하드코딩한다. 컬럼 추가 후에는 저장값이 있으면 저장값을, 없으면 상수를 사용해야 한다
  (설계 078 Decision BBB).
- 값 채움(backfill)은 이 태스크 범위에 포함되지 않는다. 컬럼 추가 이전 레코드는 null이며
  fallback이 적용된다.
- 현재 단일 alembic head: `c3d4e5f60058`. migration은 이 revision을 `down_revision`으로
  지정해 수기 작성한다. `uv run alembic revision --autogenerate`는 사용하지 않는다.
- `content_hash`의 기준 포맷은 sha256 hex(64자). 이 태스크는 컬럼 정의만 추가하며
  해시 계산·채움 로직은 포함하지 않는다.
- 이 태스크가 완료된 후 같은 브랜치에서 task-143이 이어 실행된다.

## Implementation Scope

1. `app/domains/news/model.py` — `NewsItem`에 `trust_level: Mapped[str | None]`·
   `content_hash: Mapped[str | None]` 추가 (`String(20)`·`String(64)`, `nullable=True`).
2. `alembic/versions/<rev>_add_trust_level_content_hash_to_news_items.py`(신규, 수기 작성):
   - `down_revision = "c3d4e5f60058"`.
   - upgrade: `news_items` 테이블에 `op.add_column` 2건(nullable).
   - downgrade: `op.drop_column` 2건.
3. `app/domains/news/schema.py` — `NewsItemCreate`·`NewsItemResponse`에
   `trust_level: str | None = None`·`content_hash: str | None = None` 추가.
4. `app/domains/llm_context/context_builder.py` — `_recent_news_item_from_model` 수정:
   `news_item.trust_level`이 존재하면 사용하고 없으면 `_DEFAULT_NEWS_TRUST_LEVEL` 사용.
5. 테스트 — `ContextBuilder` fallback 회귀:
   - `trust_level=None`인 `NewsItem` fixture → `_DEFAULT_NEWS_TRUST_LEVEL` 적용 확인.
   - `trust_level="high"` fixture → 저장값이 그대로 사용되는지 확인.

## Out of Scope

- `trust_level`·`content_hash` 값 채움(backfill).
- 뉴스 수집·정규화 로직(`app/domains/news/normalizer.py`·`normalization_service.py` 등) 변경.
- 다른 도메인 모델 변경.
- 게이트웨이·LLM 경로 변경 (task-143 범위).

## Protected Files

- `app/domains/*/model.py` — `app/domains/news/model.py`를 제외한 다른 도메인 모델 변경 금지.
- `alembic/versions/` 기존 파일 — 수정 금지(신규 revision 파일 추가만 허용).
- `app/adapters/llm/gateway.py`·`router.py`·`base.py` — 변경 금지.
- `app/domains/llm_analysis/` — 변경 금지.

## Requirements

- `trust_level`·`content_hash` 컬럼은 nullable이며 기존 레코드에 영향이 없다.
- migration downgrade가 정상 동작해야 한다.
- fallback 로직 변경 후 `_DEFAULT_NEWS_TRUST_LEVEL` 상수는 삭제하지 않는다(fallback에서
  계속 사용).
- 타입 힌트 완전성 (mypy 통과 수준).
- 주석은 WHY가 명확하지 않을 때만 최소한으로.

## Test Requirements

- 신규: `ContextBuilder._recent_news_item_from_model` fallback 회귀 테스트 (위 Implementation
  Scope 5). 기존 테스트 파일 중 적절한 위치에 추가(새 파일 강제 아님).
- 기존 테스트 전부 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
uv run alembic heads
```

`alembic heads` 결과가 신규 revision 1개의 단일 head여야 한다.
`uv run alembic upgrade head --sql` 등으로 migration SQL을 확인하는 것은 개발 DB 없이
가능하며 권장한다.

## Documentation Impact

설계 078이 이 PR에 동봉된다. 지침서·ADR 갱신 불필요.

## ADR Need

없음 — 설계 078 §7 참조.

## Failure Record Need

없음 — 결함 마감이 아니라 계획된 스키마 완성이다.

## Risk Level

낮음. nullable 컬럼 추가와 fallback 로직 변경으로 기존 데이터·동작에 영향이 없다.

## Expected Output

- 수정: `app/domains/news/model.py`, `app/domains/news/schema.py`,
  `app/domains/llm_context/context_builder.py`
- 신규: `alembic/versions/<rev>_add_trust_level_content_hash_to_news_items.py`, fallback 테스트 1건
- 검증 4종 통과

## Decisions 요약 (설계 078 참조)

- AAA: `trust_level`·`content_hash`를 nullable로 추가, 값 채움 정책 보류.
- BBB: `ContextBuilder`는 저장값 우선·`_DEFAULT_NEWS_TRUST_LEVEL` fallback, backfill 없음.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
