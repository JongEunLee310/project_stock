# Codex Handoff Task

## Source Issue

- BE #202 — [Worker] RQ 워커 프로세스에서 FK 대상 모델 미등록 — llm-analysis 잡 flush 실패
- Epic BE #141
- 설계: `docs/designs/077-worker-model-registry.md`
- 실패 기록: `docs/failures/FAILURE-002-worker-fk-target-model-not-registered.md`

## Task Summary

전 도메인 모델을 임포트하는 중앙 레지스트리 `app/db/models.py`를 신설하고,
`app/worker/jobs/__init__.py`·`alembic/env.py`가 이를 임포트하게 해 워커 프로세스에서도
`Base.metadata`에 전 모델이 등록되도록 한다.

## Goal

- RQ 워커에서 `run_llm_analysis_job` 실행 시 `NoReferencedTableError`가 나지 않는다.
- 잡 모듈만 임포트한 프로세스에서 metadata의 모든 FK 대상 테이블이 등록되어 있다.
- alembic autogenerate 대상 모델 목록이 레지스트리 한 곳으로 단일화된다.

## Background

- 도메인 모델은 FK 대상을 문자열(`ForeignKey("users.id")`)로 참조하고 대상 모델을
  임포트하지 않는다. 워커 프로세스는 잡 모듈의 임포트 그래프에 있는 모델만 등록된다.
- `alembic/env.py` 상단에 이미 전 모델 임포트 18줄이 있다(9–26행). 이 목록이 레지스트리로
  옮길 정본이다.
- 모델 모듈은 18개: `app/domains/{alert_candidates,alerts,assets,decision_checklist,
  decision_logs,jobs,llm_analysis,news,portfolios,prices,raw_news,raw_prices,reports,
  signals,users,watchlists}/model.py` + `app/domains/theses/model.py`·
  `app/domains/theses/conflict_model.py`.
- pytest 동일 프로세스에서는 conftest가 전 모델을 임포트해 재현되지 않는다. 회귀 테스트는
  서브프로세스 필수.

## Implementation Scope

1. `app/db/models.py`(신규) — `alembic/env.py`의 모델 임포트 18줄을 그대로 옮긴다
   (`# noqa: F401` 유지, 파일 상단에 WHY 주석 한 줄: 프로세스별 임포트 그래프와 무관하게
   전 모델을 metadata에 등록하는 단일 지점).
2. `alembic/env.py` — 개별 모델 임포트 블록을 `import app.db.models  # noqa: F401`로 대체.
3. `app/worker/jobs/__init__.py` — `import app.db.models  # noqa: F401` 추가
   (RQ가 잡 모듈을 임포트하면 패키지 `__init__`이 먼저 실행된다는 WHY 주석 한 줄).
4. 회귀 테스트 `tests/test_worker_model_registry.py`(신규):
   - `sys.executable -c` 서브프로세스에서 `import app.worker.jobs.llm_analysis`만 수행한 뒤
     `app.db.base.Base.metadata` 순회로 모든 `ForeignKey`의 참조 테이블이
     `Base.metadata.tables`에 존재하는지 검증하고, 위반 목록을 stdout으로 출력해 assert.
   - 서브프로세스 환경변수는 현재 프로세스 것을 상속하되 DB 접속이 필요 없는 검증으로
     구성한다(metadata 검사만 수행, 실제 DB 연결 금지).

## Out of Scope

- 모델·FK 정의 변경, 신규 alembic revision
- 워커 잡 로직·라우트 변경
- `docs/designs/077-*`·`docs/failures/FAILURE-002-*` 수정 (이미 작성됨)

## Protected Files

- `app/domains/*/model.py` — 변경 금지
- `alembic/versions/` — 변경 금지
- `app/worker/jobs/llm_analysis.py`·`analysis.py`·`news.py` — 변경 금지
  (임포트 지점은 `__init__.py`로 일원화)

## Requirements

- sync 유지
- 순환 임포트 금지 — `app/db/models.py`는 어떤 앱 모듈도 이를 임포트하기 전에 로드될
  필요가 없는 leaf 모듈로 유지 (`app/db/session.py`·`base.py`에서 임포트하지 않는다,
  설계 077 Decision ZZ)
- 타입 힌트 완전성 (mypy 통과 수준)
- 주석은 WHY가 필요한 곳에만 최소

## Test Requirements

- 신규: 서브프로세스 기반 FK 대상 등록 검증 (위 Implementation Scope 4)
- 기존 테스트 전부 통과

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
uv run alembic heads
```

## Documentation Impact

설계 077·FAILURE-002가 이 PR에 동봉된다. 지침서·ADR 갱신 불필요.

## ADR Need

없음 — 설계 077 §7 참조.

## Failure Record Need

작성 완료 — `docs/failures/FAILURE-002-worker-fk-target-model-not-registered.md`.

## Risk Level

낮음. 임포트 추가만 있고 스키마·로직 변경이 없다. 유일한 위험은 순환 임포트인데,
레지스트리를 leaf 모듈로 유지하면 발생하지 않는다.

## Expected Output

- 신규: `app/db/models.py`, `tests/test_worker_model_registry.py`
- 수정: `alembic/env.py`, `app/worker/jobs/__init__.py`
- 검증 4종 통과

## Decisions 요약 (설계 077 참조)

- YY: 중앙 모델 레지스트리 모듈 도입 (모델별 FK 대상 개별 임포트 기각)
- ZZ: 워커 임포트 지점은 `app/worker/jobs/__init__.py` (`db/session.py` 역류 기각)
