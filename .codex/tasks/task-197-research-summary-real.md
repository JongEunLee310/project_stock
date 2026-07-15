# Codex Handoff Task

## Source Issue

이슈 #322 — research-summary 실생성 전환. 설계:
`docs/designs/322-research-summary-real.md` (먼저 전체를 읽는다 — 코드 근거 조사
표와 계약·구현 스켈레톤이 확정 스펙이다. "가정"으로 표기된 항목은 아래
Requirements의 검증 지시를 따른다).

## Task Summary

`ResearchSummaryService`의 하드코딩 mock 템플릿(`_SUMMARY_TEMPLATES`)을
`LLMGateway` 경로를 통한 실제 생성·저장으로 전환한다. `research_summaries`
테이블에 자산별 최신 요약 1행을 upsert하고, `POST
/assets/{asset_id}/research-summary/refresh`로 생성을 트리거하며, `GET`은
저장본을 반환하도록 바꾼다.

## Goal

- `POST /assets/{asset_id}/research-summary/refresh` 호출 시 `LLMGateway.complete_json` 경로로 요약이 생성되고 `research_summaries`에 upsert된다.
- `GET /assets/{asset_id}/research-summary`가 저장본을 반환하며, `created_at`이 실제 마지막 생성 시각(저장 행의 `updated_at`)이다.
- 저장본이 없는 자산은 `GET`에서 `404 RESEARCH_SUMMARY_NOT_FOUND`를 반환한다.
- `research_queue` 목록 조회는 저장본이 없는 자산에서도 예외 없이 `stance`/`headline`을 `null`로 응답한다(`ResearchQueueItemProjection`은 이미 nullable).
- `_SUMMARY_TEMPLATES`·`_CREATED_AT` 등 mock 템플릿 코드가 제거된다.
- 기존 계약·수집 경로 회귀 없음.

## Background

`ResearchSummaryService`는 현재 `asset.id % 2`로 템플릿 2종을 순환하는 mock이며
`created_at`도 고정 상수입니다. LLM 인프라(`LLMGateway`·`ContextBuilder`·일일
호출 상한 가드)와 응답 계약 구조화(#267, #298)는 이미 갖춰져 있어 생성·저장
경로를 연결하는 작업만 남아 있습니다. 설계 문서 §2에 실측 근거를 파일:행으로
정리했습니다 — 특히 일일 호출 상한 가드는 `LLMGateway.complete_json`이
`LLM_TASK_ROUTES`에서 cloud로 해석될 때 내부에서 자동으로 적용하므로, 서비스
코드에서 별도 가드 API를 직접 호출할 필요가 없습니다.

## Implementation Scope

설계 §4 스켈레톤 그대로:

- `app/domains/research_summary/model.py` (신설) — `research_summaries` 테이블 모델.
- `app/domains/research_summary/repository.py` (신설) — 저장본 조회·upsert.
- `app/domains/research_summary/service.py` — `get_summary`(strict, 404)·`get_summary_or_none`(fallback)·`generate` 구현, mock 템플릿 제거.
- `app/adapters/llm/types.py` — `LLMTaskType.RESEARCH_SUMMARY` 추가.
- `app/adapters/llm/router.py` — `LLM_TASK_ROUTES`에 항목 추가.
- `app/adapters/llm/schema.py` — `ResearchSummaryResult` 추가.
- `app/adapters/llm/prompts/research_summary.py` (신설) — 한국어 출력 시스템 프롬프트.
- `app/adapters/llm/privacy.py` — `ResearchSummarySnapshot`(CloudSafePayload) + `to_research_summary_snapshot` 추가, 포트폴리오 컨텍스트 필드 배제.
- `app/adapters/llm/mock.py` — `DEFAULT_MOCK_RESPONSES["ResearchSummaryResult"]` 추가.
- `app/core/error_codes.py` — `RESEARCH_SUMMARY_NOT_FOUND` 추가.
- `app/api/v1/endpoints/assets.py` — 기존 GET을 저장본 조회로 전환, `POST .../refresh` 신설.
- `app/domains/research_queue/service.py` — `get_summary` 호출을 `get_summary_or_none`으로 교체하고 fallback 처리.
- Alembic migration — `research_summaries` 테이블 생성.
- `docs/api/frontend-api-spec.md` — GET 갱신, POST refresh 계약 추가, mock 관련 서술 제거.
- `tests/test_api_contract.py` — 저장본 기반 GET 테스트로 갱신, 저장본 없음 404, refresh 계약 테스트 추가.
- 설계 §5의 서비스·회귀 테스트.

## Out of Scope

- FE 수정 (별도 repo, JongEunLee310/project_stock_frontend#219).
- 요약 이력 보관 — 최신 1행만 유지.
- 주기 잡에 의한 자동 재생성 (#209 정책 유지).
- 예산 초과 시 전용 4xx 응답 매핑 — 기존 관례(비구분 500)를 유지한다. 이 범위에서 새로운 예외 핸들러를 추가하지 않는다.

## Protected Files

없음.

## Requirements

이슈 요구 불릿을 수용 기준으로 번역했습니다. 설계 문서에서 "가정"으로 표기된
항목은 구현 전에 실제 코드를 다시 확인하고, 코드와 다르면 이 문서 대신 실제
코드를 따르며 구현 노트에 이탈 사유를 남깁니다(quality-process-policy Deviations
Log).

1. `research_summaries` 테이블이 존재하고 `asset_id`에 unique 제약이 있으며, 자산별 최신 1행만 upsert된다. (alembic migration 포함)
2. `LLMTaskType.RESEARCH_SUMMARY`가 추가되고, 한국어 출력 프롬프트를 사용하며, 결과가 기존 `ResearchSummaryResponse` 구조에 대응하는 projection으로 변환된다. `DEFAULT_MOCK_RESPONSES`에 결정적 기본 응답이 등록된다.
3. 생성 서비스가 `ContextBuilder.build_symbol_context` 기반 스냅샷에서 포트폴리오 컨텍스트를 제외하고 `LLMGateway.complete_json`을 호출한 뒤 저장한다. **가정 검증**: `build_symbol_context(user_id, symbol, market)`는 코드상 `user_id`가 필수이며 "제외 전용" 오버로드가 없다(context_builder.py:76-101 실측) — 스냅샷 매핑 단계에서 `portfolio_context` 필드를 옮기지 않는 방식으로 배제되는지 구현 전 재확인한다.
4. `POST /assets/{asset_id}/research-summary/refresh`가 생성을 트리거하고, 일일 호출 상한 가드가 적용된다. **가정 검증**: 가드는 `LLMGateway.complete_json`이 cloud 라우트에서 내부적으로 `DailyCallBudget.consume()`을 호출하는 경로(gateway.py:123-124)이며, `LLM_TASK_ROUTES`에 `RESEARCH_SUMMARY`를 cloud로 등록하는 것만으로 충족된다. 구현 전 라우팅 등록이 실제로 이 경로를 타는지 재확인한다.
5. `GET`이 저장본을 반환으로 전환되고, 저장본이 없으면 `404`와 신규 `RESEARCH_SUMMARY_NOT_FOUND`를 반환한다.
6. `research_queue`가 저장본 부재 자산에서 `stance`/`headline`을 `null`로 fallback 처리하며 큐 조회가 예외 없이 동작한다. `ResearchQueueItemProjection`은 이미 nullable(research_queue/schema.py:33-34)이므로 스키마 변경은 필요 없다.
7. `_SUMMARY_TEMPLATES`가 제거되고, `frontend-api-spec.md`와 `test_api_contract.py`가 실제 동작에 맞게 갱신된다.
8. 완료 조건(이슈 원문): refresh 호출 시 게이트웨이 경로로 요약이 생성·저장되고 GET이 저장본과 실제 생성 시각을 반환한다. 저장본이 없는 자산에서 GET 404와 리서치 큐 fallback이 계약대로 동작한다.

## Test Requirements

- `test_research_summary_response_contract`를 저장본 기반으로 갱신(사전에 refresh 또는 저장소 직접 upsert로 저장본을 만든 뒤 조회).
- GET 저장본 없음 → 404 `RESEARCH_SUMMARY_NOT_FOUND` 케이스 추가.
- `POST .../refresh` 계약 테스트 추가(응답 형태, 저장 후 재조회 시 동일 값 반환).
- `research_queue` 목록 조회에서 저장본 없는 자산이 예외 없이 `stance=None`/`headline=None`으로 응답하는 회귀 테스트.
- `generate`가 CloudSafe 스냅샷에 `portfolio_context`를 포함하지 않는지 확인하는 서비스 단위 테스트.
- upsert가 동일 `asset_id`에서 행을 늘리지 않고 갱신만 하는지 확인하는 리포지토리 테스트.
- `DEFAULT_MOCK_RESPONSES["ResearchSummaryResult"]` 결정성 테스트.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`
- `uv run alembic heads` (마이그레이션 체인이 단일 head로 정리되는지 확인)

## Documentation Impact

- `docs/api/frontend-api-spec.md` — GET 섹션(계약 예시가 "Mock 응답" 서술을 포함하고 있으면 제거) 갱신, `POST .../refresh` 신규 섹션 추가.
- `tests/test_api_contract.py` — 저장본 기반 계약으로 갱신, refresh 엔드포인트 계약 추가.
- 이 핸드오프와 설계 문서는 이미 작성되어 있으므로 구현 중 추가 문서 변경은 위 두 파일 범위로 한정한다.

## ADR Need

불필요합니다. 신규 `LLMTaskType`은 `STOCK_RECOMMENDATION` 전례와 동일하게
기존 `LLMGateway`/`LLMRouter`/CloudSafe 경계 아키텍처(ADR-007~012) 안에서의
확장이며, 별도 ADR 없이 추가된 전례가 있습니다(`grep` 확인 — 관련 ADR
문서에서 `STOCK_RECOMMENDATION` 참조 없음). 신규 테이블 `research_summaries`
역시 `valuation_snapshots`(자산 단위 unique 행 + `TimestampMixin`) 패턴을
그대로 따르는 확장이며, `valuation_snapshots` 도입 시에도 ADR이 작성되지
않았습니다.

## Failure Record Need

불필요합니다. 이 작업은 기존에 실패했던 시도의 재작업이 아니라 처음
계획하는 mock→실생성 전환입니다.

## Risk Level

Medium — 이유: 신규 테이블·신규 LLM 태스크 타입 추가 자체는 기존 패턴 반복이라
낮은 리스크이지만, `research_queue`가 모든 활성 자산에 대해 `get_summary`를
무조건 호출하는 기존 경로(research_queue/service.py:70)를 건드리므로 fallback
누락 시 큐 목록 조회 전체가 깨질 수 있습니다. 회귀 테스트로 좁혀야 합니다.

## Expected Output

- 새 파일: `app/domains/research_summary/model.py`, `app/domains/research_summary/repository.py`, `app/adapters/llm/prompts/research_summary.py`, alembic migration 파일.
- 변경 파일: `app/domains/research_summary/service.py`, `app/adapters/llm/types.py`, `app/adapters/llm/router.py`, `app/adapters/llm/schema.py`, `app/adapters/llm/privacy.py`, `app/adapters/llm/mock.py`, `app/core/error_codes.py`, `app/api/v1/endpoints/assets.py`, `app/domains/research_queue/service.py`, `docs/api/frontend-api-spec.md`, `tests/test_api_contract.py`, 관련 단위 테스트 파일.
- PR 본문에 Verification Commands 실행 결과와, Requirements의 "가정 검증" 항목에 대한 실제 확인 결과(코드와 설계가 일치했는지, 이탈이 있었다면 무엇인지)를 기록합니다.

## Rules

- 최신 `dev`에서 새 브랜치(`feat/322-research-summary-real`)를 생성해 작업한다. 다른 브랜치로 전환하거나 `dev`/`main`에 직접 커밋하지 않는다.
- 커밋 메시지는 한국어 `type: 본문` 형식으로 작성한다.
- 설계 문서·이 태스크 문서·구현이 같은 PR에 함께 실린다(별도 문서 전용 PR 금지).
- 스코프 외 파일을 변경하지 않는다. 특히 이 작업과 무관한 다른 도메인 로직은 건드리지 않는다.
- 검증 명령을 임의로 생략하거나 완화하지 않는다.
- 가정으로 표기된 항목은 실제 생산자 코드에 대해 검증한 뒤 구현하고, 설계와 다르면 실제 코드를 따르며 이탈 사유를 PR 본문에 기록한다.
