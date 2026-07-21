# Codex Handoff Task

## Source Issue

BE #365 — 유사 과거 판단 검색. 상위 #354(3차). Epic #347.

## Task Summary

`GET /api/v1/decision-logs/{id}/similar`를 구현한다. 기준 판단과 정량 유사도(대상·유형·위험
태그 겹침)로 상위 N개 과거 판단을 반환한다. 신규 마이그레이션 없음.

## Goal

- `GET /api/v1/decision-logs/{id}/similar?limit=`가 유사 과거 판단을 경량
  `DecisionLogListItem[]`로 반환한다.
- `uv run ruff check .` / `uv run mypy .` / `uv run pytest` 모두 통과.

## Background

정본 계약은 `docs/designs/365-similar-decisions.md`이며 반드시 먼저 읽고 따른다. 응답 항목은
기존 `DecisionLogListItem`을 재사용하고, `_to_list_items`(risks·review_at 배치 로딩)를 그대로
쓴다.

유사도(설계 §2): 같은 대상(symbol 또는 target_type+target_id) 강, 같은 decision_type 중,
겹치는 risk_type 수 가점. 점수 내림차순·동점 최신순. 기준 판단 자신과 버전 체인
(superseded_by_id 연결)은 제외. limit 기본 5, 상한 20.

## Implementation Scope

- `app/domains/decision_logs/repository.py` — `list_similar(base, user_id, limit)`: 후보
  조회·점수·정렬(SQL + 소규모 파이썬 보정 허용).
- `app/domains/decision_logs/service.py` — `list_similar(decision_log_id, user_id, limit)`:
  소유 확인(404/403) 후 후보를 `_to_list_items`로 매핑.
- `app/api/v1/endpoints/decision_logs.py` — `GET /{decision_log_id}/similar` 라우트, limit
  쿼리(기본 5, 1~20).
- 테스트.

## Out of Scope

- 임베딩·텍스트 의미 유사도, 교차 사용자 벤치마크, analytics(#364), FE(#261).
- 스키마 변경.

## Protected Files

없음.

## Requirements

- 소유권: 기준 판단이 호출자 소유. 없음 404, 타인 403.
- 기준 판단 자신·버전 체인 제외.
- 사용자 소유 판단만 후보.
- limit 범위 밖은 422 또는 클램프(기존 쿼리 규약 따름).
- 후보 없으면 빈 목록.

## Test Requirements

- 같은 대상·같은 유형·겹치는 위험 태그가 점수·정렬에 반영.
- 기준 판단 자신·버전 체인 제외.
- 타 사용자 판단 격리, 소유권 404/403.
- 후보 없음 빈 목록, limit 동작.

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

`docs/designs/365-similar-decisions.md` 정본, 이미 커밋. ADR·Failure Record 불필요.

## ADR Need

불필요.

## Failure Record Need

불필요.

## Risk Level

Low — 읽기 조회, 유사도 규칙 정확성이 핵심.

## Expected Output

- 변경 파일: repository/service/endpoint + 테스트.
- 검증 3종 통과 로그.
- 현재 브랜치 `feat/365-similar-decisions` 유지(새 브랜치 금지). 한국어 `feat:` 커밋, `#365`
  참조.
