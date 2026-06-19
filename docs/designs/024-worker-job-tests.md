# 024. Worker Job 테스트 보강 (Issue #24)

## 배경

Issue #24의 작업 항목(Mock News Adapter 수집, Mock LLM 요약, 가설 충돌 판단, Signal/Alert 생성, Job 실패 시 JobRun 기록)과 완료 조건(외부 API 없이 테스트 가능, 실패 시 JobRun 기록, 관심 종목 분석 통합 흐름 통과)은 뉴스 어댑터/워커 구현 PR(commit `0d1b566`)에서 작성된 테스트로 대부분 이미 충족된 상태다. 따라서 이슈 텍스트를 통째로 재구현하지 않고 실제 갭만 메운다.

## 현행 커버리지 (재구현 불필요)

| 이슈 항목 | 기존 테스트 |
|---|---|
| Mock News Adapter 수집 | `test_news_adapter.py`, `test_worker_jobs.py::test_collect_news_job_records_success` |
| Mock LLM 요약 | `test_llm_adapter.py`, `test_news_analysis.py` |
| 투자 가설 충돌 판단 | `test_thesis_conflict.py`, `test_rule_engine.py` |
| Signal 생성 | `test_rule_engine.py`, `test_analysis_flow.py`, `test_signals.py` |
| Alert 생성 | `test_analysis_flow.py` |
| Job 실패 시 JobRun 기록 | `test_worker_jobs.py::test_collect_news_job_records_failure`, `test_analysis_flow.py::test_analyze_watchlist_job_records_failure_for_missing_watchlist` |
| 관심 종목 분석 통합 흐름 | `test_analysis_flow.py::test_watchlist_analysis_flow_*`, `test_analyze_watchlist_job_*` |

## 갭

1. **`POST /api/v1/worker/jobs/analysis`(`enqueue_analysis_job`) 무테스트** — `test_worker_jobs.py`는 news enqueue(`test_enqueue_news_job_api`)만 검증한다. analysis enqueue 엔드포인트의 큐 등록·응답 스키마가 미검증.
2. **`collect_news_job` 성공 테스트가 JobRun만 검증** — 잡의 본 작업인 RawNews 저장 결과를 확인하지 않는다. JobRun 성공과 별개로 수집 결과 영속화가 미검증.

## 변경 사항

### tests/test_worker_jobs.py (수정)
- `test_enqueue_analysis_job_api` 신규 — `rq.Queue`/`get_redis_connection`을 monkeypatch한 Fake로 대체, `POST /api/v1/worker/jobs/analysis`에 `{"watchlist_id": N}` 전송 → 200 + `{"job_id", "status": "queued"}` 검증, `analyze_watchlist_job`과 watchlist_id가 큐로 전달됨을 확인. 기존 news enqueue 테스트의 Fake 패턴 재사용.
- `test_collect_news_job_records_success` 보강 — JobRun 성공 단언에 더해, 잡 실행 후 RawNews(또는 수집 결과 엔티티)가 심볼 기준으로 저장되었는지 단언 추가.

## 범위 밖

- 프로덕션 코드/스키마/엔드포인트 변경 (테스트가 기존 동작을 드러내야 함, 버그 발견 시 수정 말고 보고).
- 이미 커버된 항목 재작성.
- Redis/실 워커 구동이 필요한 비동기 통합 테스트.
- `worker/entrypoint.py`, `worker/connection.py` 인프라 글루 테스트.
- README 반영 (Issue #25).

## 보호 파일

`AGENTS.md`, `CLAUDE.md`, `.github/workflows/ci.yml`, `docs/harness/`, `docs/decisions/`.

## 검증

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Risk Level

Low — 테스트 한정. 스키마·프로덕션 코드·보호 파일 변경 없음. Human Gate 불필요.

## ADR / Failure Record

불필요.
