# Codex Handoff Task

## Source Issue

BE #191 (Epic BE #174 7단계). 설계 `docs/designs/074-llm-analysis-orchestration.md`. 기준 문서
`docs/knowledge/llm-data-pipeline.md` §3.5·§6.8·§7·§7단계·§17·§18. 선행 6·6.5단계 설계
`docs/designs/072-context-builder.md`·`073-context-builder-news-signals.md`.

## Task Summary

`ContextBuilder`가 만든 `LLMContextBundle`을 LLM에 태워 분석을 실행하고 입력·출력을 재현 가능하게
영속하는 오케스트레이션을 신설한다. LLM 어댑터 스택(`app/adapters/llm/`)과 `llm_analysis` 데이터
계약(모델·스키마·마이그레이션)은 이미 존재하므로, 이를 잇는 repository·service와 번들→CloudSafe
projection만 추가한다.

## Goal

- `LLMAnalysisService.run_analysis(task_type, user_id, symbols)`가 번들을 조립해
  `input_context_json`으로 영속(PENDING)하고, `LLMGateway`를 호출해 `output_json`·status를 갱신한다.
- LLMGateway에는 번들에서 개인 원가 등 민감 필드를 제거한 CloudSafe projection만 전달된다.
- 게이트웨이·파싱 실패 시 status=FAILED·`error_message`가 기록되고 입력은 그대로 남는다.
- CI 3종(ruff + mypy + pytest) 통과, alembic 단일 head `c3d4e5f60058` 유지(마이그레이션 없음).

## Background

이미 존재하는 재사용 대상(수정 금지):

- 게이트웨이: `app/adapters/llm/gateway.py` `LLMGateway.complete_json(task_type, payload:
  CloudSafePayload, schema: type[BaseModel], system_prompt: str) -> dict[str, Any]`. cloud provider면
  `PrivacyGate.guard(payload)`를 거친다. `LLMRouter`는 모든 task_type을 `"cloud"`로 라우팅한다.
- 경계: `app/adapters/llm/privacy.py` `CloudSafePayload`(`sensitivity: ClassVar[SensitivityLevel]`,
  `as_payload()`), `PrivacyGate`(cloud는 `AGGREGATED`·`PUBLIC`만 허용).
- 데이터 계약: `app/domains/llm_analysis/model.py` `LLMAnalysisRun`(필드: `user_id`, `task_type`,
  `related_symbols: list[str]`, `input_context_json: dict`, `output_json: dict | None`, `status`,
  `model_name`, `prompt_version`, `provider`, `related_decision_log_id`, `error_message`).
  `app/domains/llm_analysis/schema.py` `LLMAnalysisResult`(출력 스키마), `LLMAnalysisRunCreate`,
  `RunStatus`(PENDING/SUCCEEDED/FAILED).
- 번들: `app/domains/llm_context/context_builder.py` `ContextBuilder(db).build_context_bundle(
  task_type: LLMTaskType, user_id: int, symbols: list[tuple[str, str]]) -> LLMContextBundle`.
  번들 구조는 `app/domains/llm_context/schema.py` 참조. `SymbolCard.portfolio_context`는
  `holding`·`weight`·`avg_buy_price`·`unrealized_return`를 가진다.
- 테스트용 클라이언트: `app/adapters/llm/mock.py` `MockLLMClient(responses)` — `complete_json`이
  `responses[schema.__name__]`을 반환한다. 게이트웨이는 `LLMGateway(clients={"cloud":
  MockLLMClient(...)})`로 구성한다.
- 참조 리포지토리 패턴: `app/domains/signals/repository.py`(생성자 `db: Session`, create/commit/
  refresh 패턴).

## Implementation Scope

수정·신설 대상:

- 신설 `app/domains/llm_analysis/repository.py`: `LLMAnalysisRunRepository(db: Session)`.
  - `create(data: LLMAnalysisRunCreate) -> LLMAnalysisRun`.
  - `get_by_id(run_id: int) -> LLMAnalysisRun | None`.
  - `mark_succeeded(run_id, output_json: dict, model_name, prompt_version, provider)
    -> LLMAnalysisRun` — status=SUCCEEDED.
  - `mark_failed(run_id, error_message: str) -> LLMAnalysisRun` — status=FAILED.
- 신설 `app/domains/llm_analysis/service.py`: `LLMAnalysisService`. 생성자는 `db: Session`,
  `gateway: LLMGateway`를 주입받는다(`ContextBuilder`는 내부 구성 또는 주입).
  - `run_analysis(task_type: LLMTaskType, user_id: int, symbols: list[tuple[str, str]])
    -> LLMAnalysisRun`. 절차: 번들 조립 → `input_context_json` 영속(PENDING) → projection 변환 →
    `gateway.complete_json(...)` → `LLMAnalysisResult` 파싱 → `mark_succeeded`. 실패 시 `mark_failed`.
- 추가 `app/adapters/llm/privacy.py`(additive, 기존 심볼 불변): `ContextBundleSnapshot(
  CloudSafePayload)`(`sensitivity = AGGREGATED`) + `to_context_bundle_snapshot(bundle:
  LLMContextBundle) -> ContextBundleSnapshot`. `app/adapters/llm/__init__.py` `__all__`에 신규
  export 추가.
- 신설 `app/adapters/llm/prompts/analysis.py`: `ANALYSIS_PROMPT_VERSION` 상수 +
  `build_analysis_system_prompt() -> str`(`LLMAnalysisResult` JSON Schema 강제. 기존
  `prompts/news_summary.py` 스타일 참조).

## projection 매핑 규칙

`to_context_bundle_snapshot`:

- `task_type`·`as_of`·`user_intent`·`symbols`·`data_quality`·`user_rules`·`recent_decisions`·
  `output_contract`: 그대로 반영(비민감).
- `symbol_cards`: `price_snapshot`·`recent_news`·`signals`·`display_name`·`symbol`·`market` 유지.
  `portfolio_context`에서 `avg_buy_price`(개인 원가)는 **제거**하고 `holding`·`weight`·
  `unrealized_return`만 담는다. 낙관적으로 원가를 남기지 않는다(Decision LL).
- `portfolio_summary`: `cash_ratio`·`top_holding_weight`·`concentration_risk` 유지(이미 집계값).
- projection 필드 타입은 CloudSafe 하위 모델로 정의한다. sensitivity는 `AGGREGATED`로 두어
  `PrivacyGate.guard`를 통과하게 한다.

## run_analysis 절차

1. `bundle = context_builder.build_context_bundle(task_type, user_id, symbols)`.
2. `run = repository.create(LLMAnalysisRunCreate(user_id=user_id, task_type=task_type,
   related_symbols=[symbol for symbol, _market in symbols],
   input_context_json=bundle.model_dump(mode="json"), status=RunStatus.PENDING))`.
3. `payload = to_context_bundle_snapshot(bundle)`.
4. `output = gateway.complete_json(task_type, payload, LLMAnalysisResult,
   build_analysis_system_prompt())`.
5. `LLMAnalysisResult(**output)`로 파싱·검증 → `repository.mark_succeeded(run.id,
   output_json=output, model_name=..., prompt_version=ANALYSIS_PROMPT_VERSION, provider=...)`.
6. 4·5에서 예외 발생 시 `repository.mark_failed(run.id, error_message=str(exc))` 후 run 반환.
   `model_name`·`provider`는 응답 메타에서 얻을 수 없으면 `None` 허용.

## Out of Scope

- `app/domains/llm_analysis/model.py`·`schema.py` 변경, 신규 alembic revision.
- `app/adapters/llm/gateway.py`·`router.py`·`base.py`·`types.py` 등 게이트웨이 코어 변경.
- `PrivacyGate`·기존 CloudSafe snapshot(`Portfolio*Snapshot` 등) 변경.
- `ContextBuilder`·`app/domains/llm_context/*` 변경.
- route 노출(`app/api/v1/endpoints/llm_analysis.py`) — 이후 단계.
- cloud provider 실호출·비용 검증, task_type별 프롬프트 분기 정교화.

## Protected Files

- `app/domains/llm_analysis/model.py`·`schema.py` — 소비만, 변경 금지.
- `app/adapters/llm/gateway.py`·`router.py`·`base.py`·`types.py`·`mock.py`·`exceptions.py` — 참조만.
- `app/adapters/llm/privacy.py` — 신규 projection·변환 함수 **추가만** 허용. 기존 심볼(`PrivacyGate`·
  `CloudSafePayload`·기존 snapshot·헬퍼)은 불변.
- `app/domains/llm_context/*`·`app/domains/news/*`·`app/domains/signals/*`·기타 소스 도메인 — 참조만.
- `alembic/versions/*` — 신규 revision 금지.

## Requirements

- 반환·중간 타입 이름에 `Dto`를 쓰지 않는다(projection 네이밍).
- `input_context_json`은 게이트웨이 호출 **전에** 영속한다(결과만 저장 금지, §17).
- 게이트웨이·파싱 실패를 조용히 삼키지 않고 status=FAILED·`error_message`로 기록한다(시스템 경계).
- projection의 sensitivity는 `AGGREGATED`이며 개인 원가(`avg_buy_price`)를 포함하지 않는다.
- 타입 주석 완전화(mypy `no-untyped-def` 회피). SQLAlchemy 커밋·refresh는 참조 리포지토리 패턴을 따른다.

## Test Requirements

`tests/test_llm_analysis_service.py`(신규, `db` 세션 fixture 사용):

- 성공 경로: 필요한 엔티티(User·Asset·StockPriceBar 등)를 직접 생성하고 `run_analysis`를 호출하면
  `input_context_json`이 번들로 채워지고, `MockLLMClient`가 반환한 유효 `LLMAnalysisResult` dict가
  `output_json`·status=SUCCEEDED로 저장되며 `prompt_version`이 채워진다.
- 실패 경로: `MockLLMClient`가 스키마 위반 응답을 반환하거나 예외를 던지도록 구성하면 status=FAILED·
  `error_message`가 기록되고 `input_context_json`은 남는다.
- projection: `to_context_bundle_snapshot(bundle).sensitivity == SensitivityLevel.AGGREGATED`,
  projection payload에 `avg_buy_price`가 없으며 `PrivacyGate().guard(projection)`가 통과한다.
- repository: create → get_by_id → mark_succeeded/mark_failed 왕복.
- 외부 API 호출 없이 통과한다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`
- `uv run alembic heads`  # 단일 head c3d4e5f60058 확인(마이그레이션 없음)

## Documentation Impact

설계 `docs/designs/074-llm-analysis-orchestration.md`·본 핸드오프가 같은 PR에 포함된다. 지침서
§6.8·§7단계 서술은 이미 오케스트레이션·영속을 포함하므로 별도 갱신 불필요.

## ADR Need

불필요. 1단계 데이터 계약과 밀스톤 #4 게이트웨이·CloudSafe 경계를 잇는 통상 오케스트레이션이며,
번들→projection은 기존 경계 정책을 유지하는 additive 변환이다(설계 074 §7).

## Failure Record Need

불필요. 신규 오케스트레이션 구현이며 알려진 실패 패턴 대응이 아니다.

## Risk Level

Medium. 신규 파일 위주지만 privacy 경계·영속 순서·실패 경로 정확성이 관건이다. projection이 민감
필드를 흘리지 않는지, `input_context_json`이 결과 전에 영속되는지, 실패가 status로 추적되는지가
핵심 검증 지점이다. 게이트웨이·모델·마이그레이션 변경이 없어 회귀 위험은 제한적이다.

## Expected Output

`repository.py`·`service.py`·`prompts/analysis.py` 신설 + `privacy.py`·`llm/__init__.py` additive
수정 + `tests/test_llm_analysis_service.py` 신설. 검증 명령 4종 결과와 함께 요약.

## Decisions 요약 (설계 074 참조)

- **KK. 신규 실체는 service·repository·projection·프롬프트만**: 모델·스키마·마이그레이션·게이트웨이
  코어 불변.
- **LL. 번들→CloudSafe projection(경계 불변)**: 민감 필드 제거·집계한 `AGGREGATED` projection 도입,
  PrivacyGate 불변(additive), ADR 불필요.
- **MM. input 우선 영속**: 게이트웨이 호출 전 PENDING run으로 `input_context_json` 영속.
- **NN. prompt_version·output_schema 관리**: prompt_version 상수 + `LLMAnalysisResult` 출력 스키마.
- **OO. 오케스트레이션 경계 에러 처리**: 실패는 status=FAILED·`error_message`로 기록.
- **PP. route 미노출**: 분석 route는 이후 단계.
