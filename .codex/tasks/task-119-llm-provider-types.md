# Codex Handoff Task

## Source Issue

이슈 #133 — [LLM] Provider 봉투·타입 경계 (TaskType/Sensitivity/Risk + LLMRequest/LLMResponse + LocalLLMProvider stub)
설계: `docs/designs/053-llm-provider-types.md` (Frozen)
근거 ADR: `ADR-007`(Provider Abstraction)·`ADR-008`(Task Routing)·`ADR-009`(Cloud Data Boundary)

## Task Summary

하이브리드 LLM 오케스트레이션이 소비할 요청/응답 봉투와 분류 enum을 신설합니다.
신규 모듈 `app/adapters/llm/types.py`(enum 3종 + 봉투 2종 + 보조 타입 3종)와
`app/adapters/llm/local.py`(`LocalLLMProvider` stub)를 추가합니다. 기존 transport
컨벤션대로 **sync 시그니처를 유지**합니다. 라우터·게이트웨이·PrivacyGate 구현은 본
범위가 아닙니다.

## Goal

- `app/adapters/llm/types.py`가 설계 053 §3의 enum·봉투·보조 타입을 정의한다.
- `app/adapters/llm/local.py`의 `LocalLLMProvider`가 `LLMClient`를 구현하고 호출 시
  `NotImplementedError`를 던진다.
- 기존 `LLMClient`/`OpenAIClient`/`MockLLMClient` 동작은 불변.
- `uv run ruff check . && uv run mypy . && uv run pytest -q` 통과.

## Background — 오케스트레이터가 확정한 사실

- 설계 053이 정본이며 계약은 동결됨. 아래대로 구현할 것.
- 전 계층 sync 컨벤션 유지(ADR-007). `async def` 도입 금지. `LocalLLMProvider`
  시그니처는 `LLMClient`(`app/adapters/llm/base.py`)와 정확히 일치해야 한다.
- enum은 repo 컨벤션(`(str, Enum)` + 영어 `UPPER_SNAKE` 값)을 따른다
  (`app/domains/decision_logs/types.py` 참조).
- 봉투(`LLMRequest`/`LLMResponse`)·`TokenUsage`는 기존 어댑터 경계 객체와 같은 계열의
  `@dataclass(frozen=True)` 불변 값 객체로 둔다(`LLMMessage` 스타일).
- 본 작업은 타입·stub만 도입한다. CloudSafe projection 파생/차단, 라우팅, 캐시,
  출력 검증은 구현하지 않는다(#134/#135/#136/#137). `CachePolicy`/`ValidationStatus`는
  Phase 2 자리만 잡는 enum이며 Phase 1은 기본값으로만 흐른다.
- `LLM_PROVIDER` 설정이나 factory 배선은 추가하지 않는다(#134 범위).

## Implementation Scope

- `app/adapters/llm/types.py` (신규)
  - `LLMTaskType(str, Enum)`: `NEWS_SUMMARY`, `THESIS_CONFLICT`, `PORTFOLIO_BRIEFING`,
    `DASHBOARD_BRIEFING`, `WATCHLIST_NOTE`, `TAG_SENTIMENT`, `AGENT`.
  - `SensitivityLevel(str, Enum)`: `RAW`, `SEMI`, `AGGREGATED`, `PUBLIC`.
  - `RiskLevel(str, Enum)`: `LOW`, `MEDIUM`, `HIGH`.
  - `CachePolicy(str, Enum)`: `BYPASS`, `READ_WRITE`, `READ_ONLY`.
  - `ValidationStatus(str, Enum)`: `NOT_VALIDATED`, `PASSED`, `FAILED`.
  - `TokenUsage` `@dataclass(frozen=True)`: `prompt_tokens: int`,
    `completion_tokens: int`, `total_tokens: int`.
  - `LLMRequest` `@dataclass(frozen=True)`: 설계 053 §3.2 필드/타입/기본값
    (`task_type`, `input_payload`, `system_prompt`, `output_schema`,
    `temperature`, `max_tokens`, `sensitivity_level`, `risk_level`, `cache_policy`,
    `timeout_ms`, `metadata`). 기본값: `temperature`는 합리적 기본(예 0.0~0.2 중
    프로젝트에 맞게), `max_tokens=None`, `cache_policy=CachePolicy.BYPASS`,
    `timeout_ms=None`, `metadata`/`input_payload`는 빈 dict default(가변 기본값은
    `field(default_factory=dict)` 사용).
  - `LLMResponse` `@dataclass(frozen=True)`: 설계 053 §3.3 필드/타입. 기본값:
    `structured_output=None`, `token_usage=None`, `cache_hit=False`,
    `finish_reason=None`, `validation_status=ValidationStatus.NOT_VALIDATED`.
- `app/adapters/llm/local.py` (신규)
  - `class LocalLLMProvider(LLMClient)`: `complete`/`complete_json` 모두
    `raise NotImplementedError("Local LLM provider is not ready yet.")`.
    시그니처는 `LLMClient`와 동일.
- `app/adapters/llm/__init__.py`
  - 기존 export 스타일을 따라 신규 타입·`LocalLLMProvider`를 재노출(기존 export가
    명시적 `__all__`/직접 import면 그 방식을 따른다).

## Out of Scope

- `LLMGateway`/`LLMRouter`/PrivacyGate/CloudSafe projection 구현.
- `LLM_PROVIDER` 설정 추가·factory 배선.
- 기존 `LLMClient`/`OpenAIClient`/`MockLLMClient` 동작 변경.
- `app/worker/jobs/analysis.py`의 `MockLLMClient` 직접 생성 정리(#134).
- DB 모델·마이그레이션, HTTP 라우터·`schema` 변경.
- 봉투를 실제로 소비하는 호출 경로 연결.

## Protected Files

없음. (`docs/decisions/`·`AGENTS.md`·`CLAUDE.md` 등 보호 파일은 건드리지 않는다.
설계 053과 본 핸드오프 문서는 오케스트레이터가 이미 작성함.)

## Requirements

- 순수 타입·stub 도입. 외부 호출·I/O 없음.
- mypy strict 통과: 전 필드·메서드·테스트 함수에 타입 주석 필수
  (과거 #126 `no-untyped-def` CI 실패 전례).
- frozen dataclass의 가변 기본값은 `field(default_factory=...)`로 둔다.
- `output_schema`는 `type[BaseModel] | None`(Pydantic `BaseModel`).

## Test Requirements

`tests/adapters/test_llm_types.py`(또는 repo 테스트 배치 컨벤션에 맞는 위치) 신규:

- 각 enum의 멤버 집합·문자열 값이 설계 053 표와 정확히 일치.
- `LLMRequest`/`LLMResponse`/`TokenUsage`가 frozen(필드 재할당 시
  `FrozenInstanceError`).
- `LLMRequest`/`LLMResponse`의 기본값이 명세와 일치(예 `cache_policy=BYPASS`,
  `validation_status=NOT_VALIDATED`, `cache_hit=False`).
- 가변 기본값(`input_payload`/`metadata`)이 인스턴스 간 공유되지 않음.

`tests/adapters/test_local_provider.py`(또는 동일 컨벤션) 신규:

- `LocalLLMProvider().complete(...)`가 `NotImplementedError`.
- `LocalLLMProvider().complete_json(...)`가 `NotImplementedError`.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest -q`

## Documentation Impact

- `docs/designs/053-llm-provider-types.md` 추가됨(정본, 오케스트레이터 작성).
- 본 핸드오프 문서 추가.
- README·ADR 변경 불요(ADR-007~009가 이미 결정을 고정).

## ADR Need

불요. ADR-007~009가 본 작업의 결정을 이미 고정했으며, 본 작업은 그 계약을 타입으로
구현할 뿐 신규 아키텍처 결정이 없다.

## Failure Record Need

불요. 신규 모듈의 국소 추가, 회귀는 테스트로 커버.

## Risk Level

Low. 순수 additive 타입·stub 모듈. 기존 동작 불변, I/O·외부 호출 없음.

## Expected Output

- `app/adapters/llm/types.py`·`app/adapters/llm/local.py` 신규 + `__init__.py` 재노출.
- 위 신규 테스트 2종.
- 최신 `main`에서 분기한 feature 브랜치(예 `feat/llm-provider-types`)에 커밋
  (한국어 메시지, `type: 본문` 형식).
- 검증 3종 통과 결과 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
