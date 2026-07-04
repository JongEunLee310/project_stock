# FAILURE-002: RQ 워커 프로세스에서 FK 대상 모델 미등록

## Status

Accepted

## Background

PR #201 머지 후 `LLM_PROVIDER=mock` 스모크 테스트에서 `POST /api/v1/worker/jobs/llm-analysis`로
enqueue한 잡을 실제 RQ 워커로 실행했다. API·pytest 경로에서는 전부 통과하던 코드였다.

## Failed Approach

워커 잡 모듈(`app/worker/jobs/llm_analysis.py`)이 자신이 직접 사용하는 모듈만 임포트하고,
FK 대상 테이블의 모델 등록은 임포트 그래프에 암묵적으로 의존했다.

## Failure Cause

도메인 모델은 FK 대상을 문자열(`ForeignKey("users.id")`)로만 참조하고 대상 모델을
임포트하지 않는다. 모델이 `Base.metadata`에 등록되는지는 그 프로세스가 어떤 모듈을
임포트했는지에 달려 있다. FastAPI 앱은 라우터 등록 과정에서 전 모델이 로드되고 pytest는
conftest가 전 모델을 임포트하므로 문제가 드러나지 않지만, RQ 워커 프로세스는 잡 모듈이
끌어오는 모듈만 로드한다. `run_llm_analysis_job`의 임포트 그래프에 `users` 모델이 없어
`LLMAnalysisRun` flush 시점에 `NoReferencedTableError`(`llm_analysis_runs.user_id` →
`users`)로 실패했다.

## Impact

llm-analysis 잡이 워커에서 run 레코드를 만들지 못하고 전량 실패했다. 같은 세션이 롤백
상태로 남아 `mark_failed`·`job_run_service.fail`까지 연쇄 실패해 실패 이력도 남지 않았다.
CI·pytest로는 검출되지 않는 유형이라 스모크 테스트 전까지 잠복했다.

## Replacement Decision

전 도메인 모델을 임포트하는 중앙 레지스트리 `app/db/models.py`를 도입하고
`app/worker/jobs/__init__.py`와 `alembic/env.py`가 이를 임포트한다. 워커 임포트
컨텍스트만으로 FK 대상 테이블이 metadata에 존재하는지 서브프로세스 회귀 테스트로
고정한다. 설계 `docs/designs/077-worker-model-registry.md` Decision YY·ZZ 참조.

## Retry Conditions

해당 없음 — 우회가 아니라 구조 마감이므로 재시도 조건이 없다. 다만 다음 신호가 보이면
같은 패턴을 의심한다.

- 워커·스크립트 등 앱 밖 진입점에서만 나는 `NoReferencedTableError`
- pytest는 통과하는데 실제 프로세스에서만 나는 SQLAlchemy metadata 관련 오류

## Related Documents

- `docs/designs/077-worker-model-registry.md`
- 이슈 BE #202, PR #199(잡 배선)·#201(cloud 경로 마감)
