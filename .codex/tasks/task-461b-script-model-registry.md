# Codex Handoff Task

## Source Issue

#461 보정 — 수동 실행 스크립트의 모델 등록 누락 (에픽 #459)

## Task Summary

`scripts/run_daily_research.py`를 실제 DB로 실행하자 알림 생성 단계에서
`NoReferencedTableError: Foreign key associated with column 'alerts.user_id' could not find table 'users'`가
났다(orchestrator 2026-10-12 실측, 4개 종목 중 2개 실패). 스크립트가 전체 모델 등록 모듈을 import하지 않아
SQLAlchemy 메타데이터에 `users` 등이 등록되지 않았기 때문이다.

## Implementation Scope

1. `scripts/run_daily_research.py`가 실행 시작 전에 `app.db.models`를 import해 모든 모델을 등록하게 한다
   (`app/db/models.py`가 side-effect import로 모델을 등록하는 기존 방식).
2. 같은 문제를 막는 테스트를 추가한다. 기존 `tests/test_worker_model_registry.py`의 방식을 참고해,
   새 Python 프로세스에서 스크립트 모듈만 import했을 때 `alerts.user_id` 등 외래키 대상이 모두 해석되는지
   확인한다.
3. `scripts/backfill_rag_embeddings.py`, `scripts/evaluate_rag_retrieval.py`도 같은 위험이 있는지 확인하고,
   있으면 같은 방식으로 고친다.

## Out of Scope

- 에이전트 로직 변경

## Protected Files

없음.

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

## Risk Level

Low.

## Expected Output

- 현재 브랜치 `feat/461-daily-research-workflow`에서 작업한다. 새 브랜치를 만들지 않는다.
- 커밋이 샌드박스에서 막히면 미커밋으로 두고 보고한다. push와 PR 생성은 하지 않는다.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
