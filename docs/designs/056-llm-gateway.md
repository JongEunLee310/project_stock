# 056 · LLMGateway 오케스트레이터 조립 + Phase 1 경계 테스트

Status: Frozen
작성: Claude Code (orchestrator)
관련: 이슈 #136, Epic #141, ADR-007(Provider Abstraction)·ADR-008(Task Routing)·ADR-009(Cloud Data Boundary)

## 1. 배경

#133이 분류 enum·요청/응답 봉투를, #134가 `LLMRouter`와 factory `get_llm_client()`를,
#135가 `PrivacyGate`와 첫 CloudSafe projection을 도입했다. 세 조각은 모두 "도입 후
소비는 다음 이슈" 패턴으로 단위 테스트까지만 되어 있고 살아있는 호출 경로에는 아직
연결되지 않았다.

본 작업은 그 조각들을 하나의 진입점 `LLMGateway`로 묶는다. ADR-007이 모든 클라우드
호출 앞에 단일 choke point를 두기로 했고, ADR-009 §4가 경계 검사를 transport 선택
전에 게이트웨이 내부에서 수행하도록 못박았다. 즉 라우팅(어느 provider로)과 프라이버시
검사(무엇이 경계를 넘을 수 있는가)를 게이트웨이가 함께 책임진다.

Phase 1 범위는 조립과 경계 테스트다. ADR-008 §3.2에 따라 출시는 클라우드 우선이라
모든 task가 `cloud`로 라우팅되며, 따라서 `LocalLLMProvider`는 게이트웨이를 통해서도
아직 실제로 호출되지 않는다.

## 2. 범위

포함:

- 신규 모듈 `app/adapters/llm/gateway.py` — `LLMGateway`(라우터·프라이버시 게이트·
  transport 맵 조립).
- `app/adapters/factory.py` — `get_llm_gateway()` 추가(설정 기반 조립 seam, ADR-008
  Follow-up이 #136으로 명시).
- `app/adapters/llm/__init__.py` — `LLMGateway` re-export(`__all__` 알파벳 정렬 유지).
- `tests/test_llm_gateway.py` — Phase 1 경계 테스트.

비포함:

- 살아있는 소비처(`NewsAnalysisService`·`ThesisAnalysisService`)를 게이트웨이로 이관.
  두 서비스는 현행 `LLMClient` 직접 호출을 그대로 유지한다(동작·시그니처 불변 =
  호환 유지). 이관에는 뉴스·thesis용 PUBLIC/SEMI projection이 선행되어야 하는데
  ADR-009가 추가 projection을 뒤로 미뤘으므로 본 범위가 아니다.
- 텍스트 `complete`(자유형) 진입점. 현재 소비처가 모두 구조화(JSON) 호출이라
  필요해질 때 추가한다.
- 캐시·검증(#137), escalation(#140), 추가 CloudSafe projection·재식별 정밀화(Phase 2).
- `LLMResponse` 조립(latency·token·model 추적) — 검증 단계(#137) 소관.
- 라우터·privacy·transport 자체 동작 변경. DB·HTTP·worker 변경.

## 3. 계약

### 3.1 `LLMGateway` (`app/adapters/llm/gateway.py`)

라우터로 provider를 고르고, 클라우드 경로에서 `PrivacyGate`로 페이로드를 검사한 뒤,
선택된 transport에 위임한다. 검사는 transport 선택·호출 전에 수행한다(ADR-009 §4).

#### 생성자

| 인자 | 타입 | 기본값 | 책임 |
|------|------|--------|------|
| `clients` | `Mapping[str, LLMClient]` | (필수) | 논리 provider 이름(`"cloud"`/`"local"`) → 실제 transport |
| `router` | `LLMRouter \| None` | `None`(→ 기본 `LLMRouter()`) | task_type → provider 해소 |
| `privacy_gate` | `PrivacyGate \| None` | `None`(→ 기본 `PrivacyGate()`) | 클라우드 경계 검사 |

- `clients`를 주입받는 구조라 테스트에서 `{"cloud": MockLLMClient(...)}`로 손쉽게
  대체할 수 있다.

#### 메서드

| 메서드 | 시그니처 | 책임 |
|--------|----------|------|
| `complete_json` | `(task_type: LLMTaskType, payload: CloudSafePayload, schema: type[BaseModel], system_prompt: str) -> dict[str, Any]` | 라우팅 → (클라우드면)프라이버시 검사 → 메시지 변환 → transport 위임 |

동작 순서:

1. `provider = router.resolve(task_type)` — 미정의 task_type은 라우터가 fail-closed.
2. `clients`에서 해당 provider transport 조회. 없으면 fail-closed(`LLMRoutingError`).
3. provider가 `"cloud"`면 `privacy_gate.guard(payload)`로 검사한 결과만 본문으로 쓴다.
   비-CloudSafe·`RAW`/`SEMI`는 여기서 `CloudBoundaryViolationError`로 차단된다.
   provider가 `"local"`이면 데이터가 프로세스를 떠나지 않으므로 projection 검사에서
   면제된다(ADR-009 §4). Phase 1에서는 모든 task가 `cloud`라 이 분기에 도달하지 않는다.
4. 검사를 통과한 페이로드의 `as_payload()` 결과(dict)와 `system_prompt`로
   `list[LLMMessage]`를 구성한다. 원본 entity는 본문에 들어가지 않는다.
5. `client.complete_json(messages, schema)`에 위임해 결과 dict를 반환한다.

- 클라우드 경로에 들어갈 수 있는 것은 `as_payload()`를 거친 CloudSafe projection
  뿐이다("CloudSafe DTO만 provider request로 변환"). 절대 수량·잔액·`user_id`·종목
  식별자는 projection이 이미 배제했다(#135).
- 본 메서드는 dict를 그대로 반환한다. `LLMResponse` 봉투 조립은 #137 검증 소관이다.

### 3.2 factory 조립 (`app/adapters/factory.py`)

| 함수 | 시그니처 | 책임 |
|------|----------|------|
| `get_llm_gateway` | `() -> LLMGateway` | `settings.LLM_PROVIDER` 기준 transport 맵을 구성해 게이트웨이 조립 |

- transport 바인딩(#134 §5가 게이트웨이 소관으로 미룬 결합 정책):
  - `mock` → 단일 `MockLLMClient`를 `"cloud"`/`"local"` 두 슬롯에 매핑(dev).
  - `cloud` → `"cloud"`=`OpenAIClient`, `"local"`=`LocalLLMProvider`.
  - `local` → `"local"`=`LocalLLMProvider`, `"cloud"`=`LocalLLMProvider`.
- 기존 `get_llm_client()`를 재사용해 transport를 만든다. 본 함수는 조립 seam이며 아직
  소비처가 없다(도입 후 소비는 후속). 라이브 경로 변경 없음.

## 4. 검증

- `uv run ruff check .`
- `uv run mypy .` — 신규 코드 전 필드·메서드에 타입 주석(과거 #126 `no-untyped-def`
  CI 실패 전례).
- `uv run pytest -q` — 신규 테스트(`tests/test_llm_gateway.py`):
  - 원본 `Portfolio` entity를 payload로 넘기면 클라우드 transport에 도달하기 전
    `CloudBoundaryViolationError`로 차단된다(transport `complete_json` 미호출 확인).
  - `RAW`/`SEMI`를 선언한 CloudSafe 서브클래스 payload도 차단된다.
  - `PortfolioConcentrationSnapshot`(AGGREGATED)은 통과해, transport에 전달된 메시지
    본문이 `as_payload()` 결과(구간·불리언)만 담고 절대 수치·식별자를 담지 않는다
    ("CloudSafe DTO만 provider request로 변환").
  - task_type에 따라 라우터가 provider를 고르고 해당 transport가 선택된다.
  - 기본 라우팅 표에서는 어떤 task도 `local`로 가지 않아 `LocalLLMProvider`가 실제로
    호출되지 않는다.
  - `MockLLMClient`를 `"cloud"` 슬롯에 주입해 게이트웨이/라우터 전체 경로를 테스트할
    수 있다.

## 5. 비고

- ADR-009 Consequences에 따라 프라이버시 민감 경계 코드이므로 머지 전 개발자의 명시적
  리뷰가 필요하다.
- 게이트웨이의 타입 있는 API는 payload를 일괄 `CloudSafePayload`로 받는다. 따라서
  로컬 경로에도 원본 entity를 직접 흘릴 수 없다(ADR-009가 허용하는 "raw→local"보다
  엄격하나, 로컬 소비처가 없는 Phase 1에서는 안전한 기본값이다). 필요해지면 후속에서
  완화한다.
- 살아있는 뉴스·thesis 서비스의 게이트웨이 이관은 PUBLIC/SEMI projection 도입(Phase 2)
  후의 후속 작업이다. 본 작업은 게이트웨이를 도입·테스트만 하고 소비는 잇지 않는다
  (#133/#134/#135와 같은 선행 패턴).
