# Codex Handoff Task

## Source Issue

Issue #59 (제목 Issue 39): `[BE] DB Migration 구조 정리`

## Task Summary

Alembic 구조를 정리한다. 모든 도메인 모델이 autogenerate 대상에 등록되도록 `env.py` import 누락을 보완하고, single head를 유지하며, 마이그레이션 실행 방법을 문서화한다. 기존 마이그레이션 재작성·스키마 변경은 하지 않는다.

## Goal

- 로컬 DB를 migration으로 재현할 수 있다(`upgrade head`).
- 스키마 변경 내역이 코드와 함께 추적된다(전체 모델 autogenerate 인식).
- migration 실행 방법이 문서화된다.

## Background

- **설계문서 우선**: `docs/designs/039-db-migration-structure.md`를 먼저 읽고 따른다.
- 현재 head: `c3d4e5f60055`(single head). Alembic은 `alembic/env.py`에서 `settings.DATABASE_URL` 주입 + `Base.metadata` 사용.
- **확인된 공백**: `env.py`가 `alerts`/`signals`/`reports` 모델을 import하지 않는다 — 해당 테이블은 마이그레이션 파일은 있으나 `--autogenerate` diff 대상에서 누락된다. (`app/domains/{alerts,signals,reports}/model.py` 존재.)
- watchlist/portfolio/research/alert 테이블은 기존 마이그레이션에 반영됨.

## Implementation Scope

- `alembic/env.py` — 누락된 도메인 모델(`alerts`, `signals`, `reports`) import 추가. 전체 도메인 모델 등록 일관성 확보. import 외 로직 변경 없음.
- `alembic heads` single head 확인, `upgrade head` → `downgrade base` → `upgrade head` 왕복 검증.
- `README.md` Alembic 섹션 — 생성(`revision --autogenerate`)/적용(`upgrade head`)/롤백(`downgrade`) 절차 정리.
- `docs/designs/039-db-migration-structure.md` — 달라지면 갱신.

## Out of Scope

- 기존 마이그레이션 파일 squash/재작성.
- 스키마 변경(테이블/컬럼 추가·삭제). 단, 검증 중 모델↔마이그레이션 불일치가 드러나면 보고 후 판단.
- 도메인 모델 자체 수정.

## Protected Files

변경하지 않는다: `AGENTS.md`, `CLAUDE.md`, `.github/workflows/ci.yml`, `docs/harness/`, `docs/decisions/`.

## Requirements

- `env.py`에 전체 도메인 모델이 등록되어 autogenerate가 모든 테이블을 인식.
- single head 유지.
- 깨끗한 DB에서 `upgrade head`로 전체 스키마 재현 가능.
- 실행 절차 문서화.

## Test Requirements

- 모든 도메인 model 모듈이 `Base.metadata`에 테이블을 등록하는지 확인하는 테스트(권고) — `env.py` import 집합과 도메인 model 집합 일치.
- (가능하면) `alembic upgrade head`가 깨끗한 DB에서 오류 없이 적용되는지 확인.
- `uv run pytest` 전체 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
uv run alembic heads
uv run alembic upgrade head   # 로컬 DB 사용 가능 시
```

## Documentation Impact

- `README.md` Alembic 섹션, `docs/designs/039-db-migration-structure.md`.

## ADR Need

불필요 — 기존 마이그레이션 도구 정리. 구조/도구 교체 없음.

## Failure Record Need

검토 — 만약 모델↔마이그레이션 불일치(누락 테이블 등)가 발견되면 원인과 보정 방향을 failure record 또는 PR 설명에 기록.

## Risk Level

Low~Medium — `env.py` import 보완은 안전하나, 보완 후 `--autogenerate`가 예기치 않은 diff를 드러낼 수 있음. diff 발견 시 임의 리비전 생성 말고 보고.

## Expected Output

- `env.py` import 보완 + 문서화 + (가능 시) upgrade 검증 결과.
- lint/typecheck/pytest 통과. PR body에 `Closes #59`.

## Rules

- 기존 마이그레이션 재작성/스키마 변경 금지.
- autogenerate diff 발견 시 임의 리비전 생성 전 보고.
- 보호 파일 변경 금지.
- 가정(모델↔마이그레이션 일치 여부)과 검증 결과 보고.
