# Codex Handoff Task

## Source Issue

이슈 #266 — BE: 리서치 목록(큐) 계약. 설계:
`docs/designs/266-research-queue-contract.md` (먼저 전체를 읽는다 —
2026-07-13 개정판 기준).

## Task Summary

자산별 리서치 메타(리서치 상태·완성도·핵심 이슈·stance·마지막 갱신
시각)와 상단 요약 카운트를 한 번에 반환하는
`GET /api/v1/research-queue`를 신설한다. 신규 테이블·마이그레이션은
없고, 기존 테이블 배치 집계로 모든 필드를 파생한다.

## Goal

- FE가 리서치 목록을 N+1 호출 없이 한 번의 요청으로 구성할 수 있다.
- 설계 문서의 판정 규칙(§4.1–§4.5)이 코드와 테스트로 구현되어 있다.
- 계약 문서와 계약 테스트가 신규 엔드포인트를 반영한다.

## Background

- FE 리서치 재설계 2단계(FE 에픽 project_stock_frontend#152, FE 소비
  이슈 #143)의 선행 BE 계약이다.
- AI 판단(stance)과 리서치 상태(데이터 준비도)는 별개 개념이다.
  완성도는 AI 확신도가 아니라 데이터 확보율이다.
- 완성도 4축(NEWS·PRICE·EARNINGS·VALUATION)은 `research_coverage`
  도메인의 축 정의와 동일하되, 목록용 배치 집계로 별도 구현한다
  (설계 §1.3).
- `earnings_upcoming` 필터는 `earnings_events.event_date` DB 조회로
  판정한다 (설계 §1.4·§4.5).

## Implementation Scope

- `app/domains/research_queue/` 신규 도메인 — `schema.py`(projection),
  `service.py`, `repository.py`, `__init__.py`. 설계 §3.3(projection
  필드), §4.6(service 시그니처), §4.7(repository 시그니처)을 따른다.
- `app/api/v1/endpoints/research_queue.py` 신규 + `app/api/v1/router.py`
  등록 (prefix `/research-queue`, 기존 등록 패턴과 동일).
- `docs/api/frontend-api-spec.md` — 신규 엔드포인트 계약 추가 (기존
  문서 형식을 따른다).
- `tests/test_api_contract.py` — 신규 엔드포인트 계약 테스트 추가
  (기존 스타일을 따른다).
- `tests/test_research_queue.py` 신규 — 판정 규칙·필터·요약 카운트·
  페이지네이션 테스트.

## Out of Scope

- 실 LLM stance 전환, `ResearchSummaryService` 구현 변경 (소스로
  재사용만 한다)
- 공시(disclosure) 축, 사용자별 watchlist 필터링
- 마이그레이션·신규 테이블 (없어야 정상)
- `research_coverage`·`watchlists`·`signals` 등 기존 도메인의 동작 변경
  (조회 재사용만 허용)
- FE 화면 구현

## Protected Files

없음.

## Requirements

- 응답 엔벨로프: `ApiResponse[ResearchQueueData]` + `meta: PageMeta`
  (설계 §3.3). `summary`는 필터 무관 전체 기준, `total`은 필터 적용 후
  건수.
- `ResearchStatus` 판정 우선순위(§4.1), 완성도 4축 25점 배점(§4.2),
  `key_issue`(§4.3)·`last_updated_at`(§4.4) 파생 규칙, 필터 매핑(§4.5)을
  정확히 따른다.
- N+1 금지 — 설계 §5의 배치 쿼리 실행 순서를 따른다. 자산 수에
  비례하는 per-asset 쿼리·라이브 어댑터 호출이 없어야 한다.
- 인증 필수(`get_current_user`), snake_case, 시각은 `UtcDatetime`.
- 알 수 없는 `filter` 값은 기존 컨벤션에 따라 422 또는
  VALIDATION_ERROR로 거부한다 (기존 엔드포인트의 enum/Query 검증
  패턴을 따른다).

## Test Requirements

- 상태 판정 5종(ANALYZED / NEEDS_ATTENTION / COLLECTING / INSUFFICIENT
  / STALE) 각각을 만드는 데이터 픽스처로 판정 규칙 검증.
- 완성도 배점: 0·1·2·3·4축 확보 시 0/25/50/75/100.
- 필터 4종 각각의 포함·제외 경계 (특히 `earnings_upcoming` 30일 경계,
  `recently_updated` 오늘 UTC 경계).
- 요약 카운트가 필터와 무관하게 전체 기준인지 검증.
- 페이지네이션 meta(total·page·size) 검증.
- 계약 테스트(`tests/test_api_contract.py`)에 응답 형태 추가.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

- `docs/api/frontend-api-spec.md`에 신규 계약 추가 (Implementation
  Scope 포함).
- 설계 문서 `docs/designs/266-research-queue-contract.md`는 이미
  작성되어 있으며 이 브랜치에서 함께 커밋된다 — 내용을 수정하지 않는다.

## ADR Need

불필요 — 신규 테이블·외부 의존성 없음. 도메인 추가는 기존 구조의 반복
패턴이며 설계 문서가 결정을 기록한다.

## Failure Record Need

불필요 — 신규 기능 구현.

## Risk Level

Medium — 신규 엔드포인트라 기존 경로 회귀 위험은 낮지만, 파생 규칙이
여러 도메인 집계에 걸쳐 있어 테스트 커버리지가 중요하다.

## Expected Output

- 위 Implementation Scope의 신규 도메인·엔드포인트·문서·테스트.
- 커밋 1개 (push 금지).

## Rules

- 현재 브랜치 `feat/266-research-queue`에서 그대로 작업한다. 새
  브랜치를 만들지 않는다.
- 커밋은 1개로 만든다. push는 하지 않는다.
- 커밋 메시지는 한국어 `type: 본문` 형식으로 작성한다.
- Stay within scope. Do not weaken verification.
- Report assumptions and verification results.
