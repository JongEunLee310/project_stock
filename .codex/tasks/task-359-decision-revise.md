# Codex Handoff Task

## Source Issue

BE #359 — 판단 버전 관리(revise). 상위 #353(2차). Epic #347.

## Task Summary

`POST /api/v1/decision-logs/{id}/revise`를 구현한다. 원본 판단을 보존한 채 원본을 대체하는 새
DRAFT 판단을 생성해 연결한다. 신규 마이그레이션 없음.

## Goal

- `POST /api/v1/decision-logs/{id}/revise`가 원본을 복제한 새 DRAFT를 만들고 원본의
  `superseded_by_id`를 새 판단 id로 세팅한다.
- 원본 본문·근거·상태는 바뀌지 않는다(`superseded_by_id` 제외).
- `uv run ruff check .` / `uv run mypy .` / `uv run pytest` 모두 통과.

## Background

정본 계약은 `docs/designs/359-decision-revise.md`이며 반드시 먼저 읽고 따른다. 상위 ADR-016
§5(버전 관리)·348 §3.1. 와이어·엔벨로프·소유권은 기존 decision_logs와 동일.

핵심:
- 원본은 변경 금지, `superseded_by_id`만 새 판단 id로.
- 새 판단: `status=DRAFT`, `target`/`decision_type`/`thesis`/`rationale`/`confidence_level`
  복제 + `decision_evidence`·`decision_risks`·`decision_review_triggers` 복제. `decision_snapshots`
  는 복제 안 함.
- 원본이 `DRAFT`/`CANCELLED`이거나 이미 `superseded_by_id`가 있으면 409
  `DECISION_LOG_INVALID_STATE`.

## Implementation Scope

- `app/domains/decision_logs/repository.py` — `revise(source)`: 새 DRAFT 생성·부속 복제·원본
  `superseded_by_id` 세팅(단일 트랜잭션).
- `app/domains/decision_logs/service.py` — `revise(decision_log_id, user_id)`: 소유 확인·상태
  가드·`repo.revise`·상세 반환.
- `app/api/v1/endpoints/decision_logs.py` — `POST /{decision_log_id}/revise` 라우트.
- 테스트.

## Out of Scope

- 이벤트 트리거·Alert(#360), 자동 근거 연결(#361), 복기(#358, 완료), FE(#253).
- 대체 체인 조회 API·버전 이력 표시.

## Protected Files

없음.

## Requirements

- 소유권 404/403. 상태 위반 409 `DECISION_LOG_INVALID_STATE`.
- 근거·위험·트리거 복제는 새 레코드로(원본 레코드 공유 금지).
- 단일 트랜잭션으로 새 판단 + 부속 + 원본 링크를 커밋.

## Test Requirements

- revise가 새 DRAFT를 만들고 원본 `superseded_by_id`가 새 id를 가리키는지.
- 원본 본문·근거·상태가 그대로인지(불변).
- 근거·위험·트리거가 새 판단으로 복제되고 스냅샷은 복제 안 되는지.
- DRAFT/CANCELLED/이미 대체된 원본 revise 시 409.
- 소유권(타인 403).

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

`docs/designs/359-decision-revise.md` 정본, 이미 커밋. ADR·Failure Record 불필요.

## ADR Need

불필요.

## Failure Record Need

불필요.

## Risk Level

Low~Medium — 부속 복제·원본 불변·트랜잭션이 핵심.

## Expected Output

- 변경 파일: repository/service/endpoint + 테스트.
- 검증 3종 통과 로그.
- 현재 브랜치 `feat/358-decision-review` 유지(새 브랜치 금지). 한국어 `feat:` 커밋, `#359`
  참조.
