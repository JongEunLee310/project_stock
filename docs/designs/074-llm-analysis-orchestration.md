# 074 · LLM 데이터 파이프라인 7단계 — LLM Gateway 분석 오케스트레이션·결과 영속

Status: Draft
작성: Claude Code (orchestrator)
관련: Epic BE #174(LLM 사전 데이터 수집·가공 파이프라인 v0.1), 구현 이슈 BE #191,
Milestone 데이터 수집 파이프라인 — 백엔드(#5). 기준 문서 `docs/knowledge/llm-data-pipeline.md`
(§3.5·§6.8·§7·§7단계·§17·§18). 선행 설계 `docs/designs/073-context-builder-news-signals.md`
(6.5단계 — 뉴스·시그널 배선), `docs/designs/072-context-builder.md`(6단계 — 번들 조립).

## 1. 배경

6·6.5단계(#187·#189)에서 `ContextBuilder`가 `LLMContextBundle`을 완성했다. 7단계는 이 번들을
LLM에 태워 분석을 실행하고 입력·출력을 재현 가능하게 영속하는 오케스트레이션을 신설한다.

이번 단계의 핵심은 새 실체가 많지 않다는 점이다. LLM 어댑터 스택
(`app/adapters/llm/`: `LLMGateway`·`LLMRouter`·`PrivacyGate`·`CloudSafePayload`·`MockLLMClient`·
`prompts/`)은 밀스톤 #4에서, `llm_analysis` 데이터 계약(`LLMAnalysisRun` 모델·`LLMAnalysisResult`·
`RunStatus` 스키마·마이그레이션 `c3d4e5f60057`)은 1단계(#175)에서 이미 완성돼 있다. 따라서
7단계가 새로 만드는 것은 이 조각들을 잇는 **repository·service(오케스트레이션)·번들→CloudSafe
projection**뿐이다.

경계 상 유의점이 하나 있다. 지침 §18은 "LLMGateway는 ContextBundle만 입력받는다"고 하지만, 실제
구현된 `LLMGateway.complete_json`은 `CloudSafePayload`(PrivacyGate가 cloud엔 `AGGREGATED`·`PUBLIC`
만 허용)를 받는다. `LLMContextBundle`에는 개인 원가(`avg_buy_price`) 등 SEMI 민감정보가 있어 그대로
cloud에 태울 수 없다. 이 단계는 번들에서 민감 필드를 제거·집계한 CloudSafe projection을 새로 도입해
경계를 지키면서 게이트웨이에 전달한다(Decision LL). 전체 번들은 `input_context_json`으로 로컬 DB에
영속되어 재현성을 확보한다.

## 2. 범위

포함:

- `app/domains/llm_analysis/repository.py`: `LLMAnalysisRunRepository` — run 생성·조회·결과 갱신.
- `app/domains/llm_analysis/service.py`: `LLMAnalysisService` — 번들 조립 → `input_context_json`
  영속(PENDING) → projection 변환 → `LLMGateway` 호출 → `output_json`·status 갱신·파싱.
- `app/adapters/llm/privacy.py`: 번들→CloudSafe projection(`ContextBundleSnapshot` +
  `to_context_bundle_snapshot`) 추가. PrivacyGate·기존 snapshot은 불변(additive).
- `app/adapters/llm/prompts/analysis.py`(신규): 분석 system prompt 빌더 + `ANALYSIS_PROMPT_VERSION`.
  output_schema는 기존 `LLMAnalysisResult` 재사용.
- 단위 테스트(`db` 세션 fixture·`MockLLMClient`, 외부 API 없이).

비포함(후속·변경 없음):

- `llm_analysis` 모델·스키마·마이그레이션·`app/adapters/llm/*` 게이트웨이 코어 변경(재사용).
- route 노출(`api/v1/endpoints/llm_analysis.py`) — 지침 §19 "route는 마지막". 이번 단계는 도메인
  서비스까지.
- cloud provider 실호출 검증 — provider config는 두되 검증은 mock. 실호출·비용은 범위 밖.
- prompt_version 다변화·task_type별 프롬프트 분기 정교화 — v0.1은 단일 분석 프롬프트.
- 신규 alembic revision — 스키마 변경 없음, 단일 head `c3d4e5f60058` 유지.

## 3. 구성 요소

### 3.1 `LLMAnalysisRunRepository` (`app/domains/llm_analysis/repository.py`)

생성자는 `Session`을 주입받는다. 쓰기 리포지토리다.

| 시그니처 | 책임 |
| --- | --- |
| `create(data: LLMAnalysisRunCreate) -> LLMAnalysisRun` | run 영속(초기 `input_context_json`·status=PENDING) |
| `get_by_id(run_id: int) -> LLMAnalysisRun \| None` | 단건 조회 |
| `mark_succeeded(run_id, output_json, model_name, prompt_version, provider) -> LLMAnalysisRun` | 성공 결과·메타 갱신, status=SUCCEEDED |
| `mark_failed(run_id, error_message) -> LLMAnalysisRun` | 실패 사유 기록, status=FAILED |

### 3.2 `LLMAnalysisService` (`app/domains/llm_analysis/service.py`)

생성자는 `Session`과 `LLMGateway`(테스트 시 `MockLLMClient` 구성)를 주입받는다. `ContextBuilder`는
내부 구성 또는 주입한다.

| 시그니처 | 책임 |
| --- | --- |
| `run_analysis(task_type, user_id, symbols) -> LLMAnalysisRun` | 번들 조립 → `input_context_json` 영속(PENDING) → projection 변환 → 게이트웨이 호출 → 결과 파싱·`output_json`·status 갱신. 실패 시 status=FAILED |

`run_analysis` 절차(개념 순서):

1. `ContextBuilder.build_context_bundle(task_type, user_id, symbols)` → `bundle`.
2. `repository.create(...)`로 `input_context_json=bundle`(직렬화)·`related_symbols`·status=PENDING
   영속(Decision MM — 결과 전에 입력부터 저장).
3. `to_context_bundle_snapshot(bundle)` → CloudSafe projection(Decision LL).
4. `LLMGateway.complete_json(task_type, payload, LLMAnalysisResult, system_prompt)` 호출.
   system_prompt·`prompt_version`은 `prompts/analysis.py` 상수 사용.
5. 응답을 `LLMAnalysisResult`로 파싱·검증 → `mark_succeeded(output_json, model_name,
   prompt_version, provider)`.
6. 게이트웨이·파싱 실패 시 `mark_failed(error_message)`(Decision OO). 입력은 이미 영속돼 있다.

### 3.3 번들→CloudSafe projection (`app/adapters/llm/privacy.py`, additive)

| 심볼 | 타입 | 책임 |
| --- | --- | --- |
| `ContextBundleSnapshot` | `CloudSafePayload` | sensitivity=`AGGREGATED`. 번들의 cloud-safe 부분집합을 담는 projection |
| `to_context_bundle_snapshot(bundle) -> ContextBundleSnapshot` | 함수 | 민감 필드 제거·집계 변환 |

projection 매핑 규칙:

| 대상 | 소스(번들) | 규칙 |
| --- | --- | --- |
| task_type·as_of·user_intent·symbols·data_quality | 동일 필드 | 직접(비민감) |
| symbol_cards | `SymbolCard` | `price_snapshot`·`recent_news`·`signals`·`display_name`은 유지. `portfolio_context.avg_buy_price`(개인 원가)는 **제거**, `holding`·`weight`·`unrealized_return`은 유지(시장 상대·집계값) |
| portfolio_summary | `PortfolioSummary` | `cash_ratio`·`top_holding_weight`·`concentration_risk`는 이미 집계값이라 유지 |
| user_rules·recent_decisions·output_contract | 동일 필드 | 유지(정책·판단 맥락, 개인 식별정보 아님) |

`sensitivity=AGGREGATED`이므로 기존 `PrivacyGate.guard`(cloud는 `AGGREGATED`·`PUBLIC`만 허용)를
그대로 통과한다. PrivacyGate·기존 snapshot 변환은 손대지 않는다.

### 3.4 분석 프롬프트 (`app/adapters/llm/prompts/analysis.py`, 신규)

| 심볼 | 책임 |
| --- | --- |
| `ANALYSIS_PROMPT_VERSION` | prompt_version 상수(예: `"v1"`) |
| `build_analysis_system_prompt() -> str` | `LLMAnalysisResult` JSON Schema를 강제하는 system prompt 문자열 구성 |

## 4. Decisions

- **KK. 신규 실체는 service·repository·projection·프롬프트만**: `llm_analysis` 모델·스키마·
  마이그레이션(1단계)과 `app/adapters/llm/*` 게이트웨이 코어(밀스톤 #4)는 재사용하고 수정하지
  않는다. 7단계는 기존 조각을 잇는 오케스트레이션·영속·경계 변환만 더한다.
- **LL. 번들→CloudSafe projection(경계 불변)**: `LLMContextBundle`은 개인 원가 등 SEMI 정보를
  포함해 cloud에 직접 태울 수 없다. 민감 필드를 제거·집계한 `AGGREGATED` projection을 새로
  도입해 게이트웨이에 전달한다. 기존 `PrivacyGate`·CloudSafe 경계는 불변이며(additive) 아키텍처
  변경이 아니라 ADR은 불필요하다. 전체 번들은 `input_context_json`으로 로컬 영속한다.
- **MM. input 우선 영속**: 게이트웨이 호출 전에 `input_context_json`을 담은 PENDING run을 먼저
  영속하고, 이후 `output_json`·status를 갱신한다. 지침 §3.5·§17(결과만 저장 금지)을 지켜 어떤
  입력으로 그 결과가 나왔는지 재현 가능하게 한다.
- **NN. prompt_version·output_schema 관리**: prompt_version은 모듈 상수로, output_schema는 기존
  `LLMAnalysisResult`로 관리한다. v0.1은 task_type과 무관하게 단일 분석 프롬프트를 쓰며, 세분화는
  필요가 구체화되는 시점의 후속으로 둔다.
- **OO. 오케스트레이션 경계 에러 처리**: 게이트웨이 호출·응답 파싱 실패는 시스템 경계 오류다.
  예외를 조용히 삼키지 않고 run.status=FAILED + `error_message`로 기록한다. 입력은 이미 영속돼
  있어 실패도 추적 가능하다.
- **PP. route 미노출**: 분석 실행·조회 route(`llm_analysis.py`)는 노출하지 않는다(지침 §19 route는
  마지막). 이번 단계는 도메인 서비스까지이며, route는 이후 단계에서 얇게 붙인다.

## 5. 마이그레이션

없음. 스키마 변경이 없다(Decision KK). `llm_analysis_runs` 테이블은 1단계 마이그레이션
`c3d4e5f60057`로 이미 존재한다. alembic 단일 head `c3d4e5f60058` 유지.

## 6. 테스트

- 성공 경로: `run_analysis`가 번들을 조립해 `input_context_json`으로 영속하고, `MockLLMClient`가
  반환한 유효 `LLMAnalysisResult`를 `output_json`·status=SUCCEEDED로 저장한다. `model_name`·
  `prompt_version`·`provider`가 채워진다.
- 실패 경로: 게이트웨이가 예외를 던지거나 응답이 스키마 위반이면 status=FAILED·`error_message`가
  기록되고, `input_context_json`은 그대로 남는다.
- projection: `to_context_bundle_snapshot(bundle).sensitivity == AGGREGATED`, `avg_buy_price`가
  제거되며 `PrivacyGate().guard(projection)`가 통과한다.
- repository: create → get_by_id → mark_succeeded/mark_failed 왕복이 정확하다.
- 외부 API 호출 없이 통과한다(§12).
- CI 3종(ruff + mypy + pytest) 통과, 신규 타입 주석 완전화(mypy).

## 7. ADR 판단

불필요. 1단계 데이터 계약과 밀스톤 #4 게이트웨이·CloudSafe 경계를 잇는 통상 오케스트레이션이다.
번들→projection은 기존 경계 정책을 유지하는 additive 변환이라 경계·아키텍처를 바꾸지 않는다.
prompt_version 다변화·route 노출·cloud 실호출은 필요가 구체화되는 시점에 각각 별도로 판단한다.
