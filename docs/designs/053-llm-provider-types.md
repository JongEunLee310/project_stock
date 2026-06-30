# 053 · LLM Provider 봉투·타입 경계 (TaskType / Sensitivity / Risk + LLMRequest/Response)

Status: Frozen
작성: Claude Code (orchestrator)
관련: 이슈 #133, Epic #141, ADR-007(Provider Abstraction)·ADR-008(Task Routing)·ADR-009(Cloud Data Boundary)

## 1. 배경

하이브리드 LLM 구조(ADR-007)에서 transport 계층(`LLMClient`)은 단일 모델 호출만
담당하고, 상위 오케스트레이션(`LLMGateway`, #136)이 라우팅·프라이버시 경계·캐시를
소유한다. 그 오케스트레이션이 다루는 **요청/응답 봉투**와, 라우팅·프라이버시·위험도
판단의 공통 어휘가 되는 **분류 enum**을 먼저 신설한다.

이 작업은 타입·enum·stub만 도입하는 선행 계약이다. 라우터(#134)·게이트웨이(#136)·
PrivacyGate(#135)는 이 타입을 소비할 뿐 본 범위에 포함하지 않는다. transport는 기존
`LLMClient`(ABC) 컨벤션대로 **sync 시그니처를 유지**한다(ADR-007).

## 2. 범위

포함:

- 신규 모듈 `app/adapters/llm/types.py` — 분류 enum 3종 + 요청/응답 봉투 2종.
- 신규 모듈 `app/adapters/llm/local.py` — `LocalLLMProvider` stub(`LLMClient` 구현,
  호출 시 `NotImplementedError`).
- `app/adapters/llm/__init__.py` 재노출(기존 export 스타일을 따른다).

비포함:

- `LLMGateway`·`LLMRouter`·PrivacyGate·CloudSafe projection 구현 없음(#134/#135/#136).
- `LLM_PROVIDER` 설정·factory 배선 없음(#134, ADR-008).
- 기존 `LLMClient`/`OpenAIClient`/`MockLLMClient` 동작 변경 없음.
- DB 모델·마이그레이션 없음(전부 in-memory 값 객체).
- `app/worker/jobs/analysis.py`의 `MockLLMClient` 직접 생성 정리는 #134 범위.

## 3. 계약

### 3.1 분류 enum (`app/adapters/llm/types.py`)

기존 도메인 컨벤션(`(str, Enum)` + 영어 `UPPER_SNAKE` 값)을 따른다.

#### `LLMTaskType`

라우팅 키(ADR-008). 현행 소비처가 있는 작업과 향후 작업을 함께 정의한다.

| 값 | 의도 | 현 소비처 |
|----|------|-----------|
| `NEWS_SUMMARY` | 뉴스/공시 요약 | `analysis.service` 뉴스 요약 |
| `THESIS_CONFLICT` | 투자 논거 충돌 분석 | `analysis.service` 충돌 분석 |
| `PORTFOLIO_BRIEFING` | 포트폴리오 브리핑 | 향후(Phase 2 소비처) |
| `DASHBOARD_BRIEFING` | 대시보드 브리핑 | 향후 |
| `WATCHLIST_NOTE` | 워치리스트 관찰 메모 | 향후 |
| `TAG_SENTIMENT` | 태그/감성/중복제거 | 향후 |
| `AGENT` | 에이전트(향후) | 향후 |

- 값 추가는 ADR-008 라우팅 표와 동기화한다. 미정의 작업을 라우터에 넘기면
  fail-closed(에러)이므로(ADR-008), 향후 작업도 enum에는 미리 둔다.

#### `SensitivityLevel`

데이터 민감도 등급(ADR-009 §민감도). 라우팅·프라이버시 게이트 공통 어휘.

| 값 | 의미 |
|----|------|
| `RAW` | 원본 entity 필드(클라우드 전송 금지 대상) |
| `SEMI` | 부분 식별 가능·준식별 |
| `AGGREGATED` | 집계·익명화되어 재식별 위험 낮음 |
| `PUBLIC` | 공개 정보(시세·뉴스 원문 등) |

- 등급은 낮음(PUBLIC) → 높음(RAW) 방향의 의미 순서를 가지나, 본 범위에서는
  비교 연산을 구현하지 않는다(게이트 정책은 #135).

#### `RiskLevel`

작업 입력의 위험도. Phase 2 escalation(#140)의 입력 신호.

| 값 | 의미 |
|----|------|
| `LOW` | 일반 |
| `MEDIUM` | 주의 |
| `HIGH` | 고위험(escalation 후보) |

### 3.2 요청 봉투 `LLMRequest`

게이트웨이 진입점이 받는 단일 요청 객체. 기존 어댑터 경계 객체와 같은 계열의
`@dataclass(frozen=True)`로 둔다(불변 값 객체).

| 필드 | 타입 | 책임 |
|------|------|------|
| `task_type` | `LLMTaskType` | 라우팅 키(ADR-008) |
| `input_payload` | `dict[str, Any]` | 작업 입력 데이터(프롬프트 렌더링 전 구조화 입력) |
| `system_prompt` | `str` | 시스템 프롬프트 |
| `output_schema` | `type[BaseModel] \| None` | 구조화 출력 스키마. `None`이면 자유 텍스트 |
| `temperature` | `float` | 샘플링 온도(기본값 보유) |
| `max_tokens` | `int \| None` | 최대 출력 토큰. `None`이면 provider 기본 |
| `sensitivity_level` | `SensitivityLevel` | 입력 민감도(프라이버시 경계 판단용) |
| `risk_level` | `RiskLevel` | 입력 위험도(향후 escalation용) |
| `cache_policy` | `CachePolicy` | 캐시 사용 정책(아래 §3.4) |
| `timeout_ms` | `int \| None` | 호출 타임아웃(ms). `None`이면 설정 기본 |
| `metadata` | `dict[str, Any]` | 부가 추적 정보(로깅·관측) |

- `input_payload`는 아직 원본일 수 있으며, RAW 필드의 클라우드 차단은 #135
  PrivacyGate가 담당한다. 본 타입은 민감도를 **표현**만 한다.

### 3.3 응답 봉투 `LLMResponse`

게이트웨이가 호출부에 돌려주는 단일 응답 객체. 동일하게
`@dataclass(frozen=True)`.

| 필드 | 타입 | 책임 |
|------|------|------|
| `text` | `str` | 자유 텍스트 응답 |
| `structured_output` | `dict[str, Any] \| None` | 구조화 출력 결과. `output_schema` 없으면 `None` |
| `provider` | `str` | 응답을 만든 provider 식별(`cloud`/`local`/`mock`) |
| `model` | `str` | 모델명 |
| `latency_ms` | `int` | 호출 소요 시간(ms) |
| `token_usage` | `TokenUsage \| None` | 토큰 사용량(아래 §3.4) |
| `cache_hit` | `bool` | 캐시 적중 여부(Phase 1은 항상 `False`) |
| `finish_reason` | `str \| None` | 종료 사유(provider 원문) |
| `validation_status` | `ValidationStatus` | 출력 검증 결과(아래 §3.4) |

### 3.4 보조 타입

| 타입 | 형태 | 책임 |
|------|------|------|
| `CachePolicy` | `(str, Enum)`: `BYPASS` / `READ_WRITE` / `READ_ONLY` | 요청별 캐시 정책. Phase 1 기본 `BYPASS`(캐시는 #137) |
| `ValidationStatus` | `(str, Enum)`: `NOT_VALIDATED` / `PASSED` / `FAILED` | 출력 검증 상태. Phase 1 기본 `NOT_VALIDATED`(검증은 #137) |
| `TokenUsage` | `@dataclass(frozen=True)`: `prompt_tokens: int`, `completion_tokens: int`, `total_tokens: int` | 토큰 사용량 |

- `CachePolicy`/`ValidationStatus`는 Phase 2 기능(#137)의 자리만 잡는 enum이다.
  Phase 1에서 의미 있는 분기는 없고 기본값으로만 흐른다.

### 3.5 `LocalLLMProvider` stub (`app/adapters/llm/local.py`)

`LLMClient`(ABC)를 구현하는 transport 쪽 stub(ADR-007 §2).

| 메서드 | 시그니처 | 동작 |
|--------|----------|------|
| `complete` | `(messages, timeout=None) -> str` | `NotImplementedError("Local LLM provider is not ready yet.")` |
| `complete_json` | `(messages, schema, timeout=None) -> dict[str, Any]` | 동일하게 `NotImplementedError` |

- 시그니처는 `LLMClient`와 정확히 일치(sync 유지). 라우팅 표상 `future_primary`가
  로컬인 작업이 코드 변경 없이 config만으로 이관될 자리를 마련한다(ADR-008).

## 4. 검증

- `uv run ruff check .`
- `uv run mypy .` — 신규 타입 모듈은 `no-untyped-def` 위반이 없도록 전 메서드·필드에
  타입 주석을 단다(과거 #126 mypy 실패 전례).
- `uv run pytest -q` — 신규 테스트:
  - enum 멤버·문자열 값이 표와 일치(`LLMTaskType`/`SensitivityLevel`/`RiskLevel`/
    `CachePolicy`/`ValidationStatus`).
  - `LLMRequest`/`LLMResponse`가 불변(frozen)이고 기본값이 명세와 일치.
  - `LocalLLMProvider.complete`/`complete_json`이 `NotImplementedError`를 던짐.

## 5. 비고

- 본 설계는 ADR-009의 "CloudSafe projection"을 도입하지 않는다. 여기서는 민감도를
  **표현하는 enum**만 두고, 화이트리스트 파생·차단은 #135 PrivacyGate 범위다.
- `provider` 식별 문자열(`cloud`/`local`/`mock`)은 ADR-008의 `LLM_PROVIDER`
  설정 값과 어휘를 맞춘다(#134에서 설정 도입).
- `input_payload`/`metadata`의 `dict[str, Any]`는 Phase 1 단순성을 위한 선택이며,
  작업별 구체 타입화는 소비처가 생기는 Phase 2에서 재검토한다.
