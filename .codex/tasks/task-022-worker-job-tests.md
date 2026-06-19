# Codex Handoff Task

## Source Issue

Issue #24: Worker Job 테스트 작성

## Task Summary

Background Job(뉴스 수집/관심종목 분석)의 핵심 흐름은 구현 PR(`0d1b566`)에서 작성한 테스트로 대부분 이미 커버되어 있다. 본 태스크는 갭 분석 결과 미검증으로 남은 두 지점만 메운다: (1) analysis enqueue 엔드포인트 테스트, (2) 뉴스 수집 잡의 RawNews 영속화 검증. 이슈 체크리스트를 통째로 재구현하지 않는다.

## Goal

- `POST /api/v1/worker/jobs/analysis`(`enqueue_analysis_job`)의 큐 등록·응답 스키마를 외부 의존 없이 검증한다.
- `collect_news_job` 성공 시 JobRun 기록뿐 아니라 실제 수집 결과(RawNewsEvent) 영속화를 검증한다.

## Background

- 설계 문서: `docs/designs/024-worker-job-tests.md`
- 워커 잡: `app/worker/jobs/news.py::collect_news_job`, `app/worker/jobs/analysis.py::analyze_watchlist_job`.
- enqueue 엔드포인트: `app/api/v1/endpoints/worker.py` — `POST /jobs/news`(검증됨), `POST /jobs/analysis`(미검증). 둘 다 `rq.Queue`/`get_redis_connection`을 사용.
- `analyze_watchlist_job`는 `AnalysisJobRequest{watchlist_id: int}`를 받아 큐에 등록, 응답은 `JobQueuedResponse{job_id, status}`.
- 뉴스 수집: `collect_news_job(symbols)` → `RawNewsService.collect_and_save(MockNewsAdapter(), symbols)` 호출. `MockNewsAdapter`는 심볼당 2건 반환, 저장 엔티티는 `app/domains/raw_news/model.py::RawNewsEvent`.
- 기존 `tests/test_worker_jobs.py`에 news enqueue용 Fake 패턴(`FakeJob`/`FakeQueue`, `monkeypatch`로 `worker.Queue`/`get_redis_connection` 교체)이 있으니 그대로 재사용한다.
- 워커 잡 테스트는 `news.SessionLocal`을 테스트 세션으로 패치하는 `patch_worker_session` autouse 픽스처에 의존한다(기존 유지).

## Implementation Scope

- `tests/test_worker_jobs.py` (수정)
  - `test_enqueue_analysis_job_api` 신규: `worker.Queue`/`worker.get_redis_connection`을 Fake로 monkeypatch, `POST /api/v1/worker/jobs/analysis`에 `{"watchlist_id": 7}` 전송 → 200, 응답 `{"job_id": ..., "status": "queued"}` 단언. Fake queue의 `enqueue`가 `analyze_watchlist_job`과 `watchlist_id=7`을 전달받았는지 검증.
  - `test_collect_news_job_records_success` 보강: 기존 JobRun 단언 유지 + 잡 실행 후 `RawNewsEvent` 행이 저장되었는지 단언(MockNewsAdapter는 심볼당 2건 → `["AAPL"]`이면 2건). 기존 단언을 약화·삭제하지 않는다.

## Out of Scope

- 프로덕션 코드/스키마/엔드포인트 변경 (테스트가 기존 동작을 드러내야 함. 버그 발견 시 수정하지 말고 보고).
- 이미 커버된 항목 재작성(Mock LLM 요약/충돌 판단/Signal/Alert/실패 JobRun 기록/통합 흐름).
- Redis/실 워커 구동이 필요한 비동기 통합 테스트.
- `worker/entrypoint.py`, `worker/connection.py` 테스트.
- 기존 워커 테스트 픽스처를 conftest로 무리하게 통합(세션 패치 특수성으로 자체 유지).
- README 반영 (Issue #25 범위).

## Protected Files

변경하지 않는다: `AGENTS.md`, `CLAUDE.md`, `.github/workflows/ci.yml`, `docs/harness/`, `docs/decisions/`.

## Test Requirements

- 신규/보강 테스트 포함 `uv run pytest` 전체 통과.
- 기존 테스트 전부 통과 유지(개수 감소·약화 금지).
- 외부 API/Redis 없이 실행 가능.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/designs/024-worker-job-tests.md` 이미 작성됨 (변경 불필요).
- README는 Issue #25.

## ADR Need

없음.

## Failure Record Need

없음.

## Risk Level

Low — 테스트 한정. 스키마·프로덕션 코드·보호 파일 변경 없음. Human Gate 불필요.

## Expected Output

- `tests/test_worker_jobs.py`에 analysis enqueue 테스트 추가 + collect_news 성공 테스트 보강.
- `uv run pytest` 전체 통과, lint/typecheck 통과.
- PR body에 closing keyword 포함 (`Closes #24`).

## Rules

- 스코프 외(프로덕션 코드) 변경 금지. 버그 발견 시 수정 말고 보고.
- 기존 테스트 약화 금지.
- 보호 파일 변경 금지.
- 가정과 검증 결과를 보고.
