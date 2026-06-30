# ADR-007: LLM Provider Abstraction (Transport vs. Gateway, Sync 컨벤션)

## Status

Proposed

## Context

백엔드는 로컬/클라우드 하이브리드 LLM 설계(Epic #141) 위에서 실사용 AI 투자
비서로 발전하고 있다. 현재 `app/adapters/llm/`에는 transport 계층이 이미 존재한다.
`LLMClient`(ABC)와 그 구현인 `OpenAIClient`·`MockLLMClient`, `complete_json`을 통한
구조화 출력, `prompts/` 하위의 프롬프트 분리, 생성자 기반 DI가 갖춰져 있다. 다른
어댑터의 provider 선택은 이미 정착된 패턴을 따른다 — `adapters/factory.py`의
`get_X_provider()`가 `settings.X_PROVIDER` 값으로 분기한다.

하이브리드 스펙(§1)은 transport 클라이언트에 속하지 않는 오케스트레이션 관심사를
도입한다. 작업을 provider로 라우팅하고, 클라우드 호출 전에 데이터 경계를 강제하며,
(추후) 캐시·폴백·출력 검증을 수행하는 일이다. #133–#136 어느 것을 만들기 전에 다음 두
네이밍·컨벤션 질문을 먼저 고정해야 한다.

1. **오케스트레이션이 어디 사는가.** 스펙은 transport와 라우팅·정책을 한데 섞는
   `LLMProvider` 인터페이스를 스케치한다. 이는 repo의 기존 의미(`LLMClient`=transport,
   `XxxProvider`=factory 레벨 외부 어댑터)와 충돌하고, 하나의 객체에 두 책임을
   과적재한다.
2. **Sync vs. async.** 스펙은 `async def generate(...)`를 제안한다. repo 전체 —
   서비스·리포지토리·라우터·워커 — 가 동기다. 한 서브시스템만 async를 도입하면
   호출부 전반에 `async`/`await` 색칠을 강제하거나 모든 경계에 브리지 코드를 끼워야
   한다.

## Decision

transport 계층은 그대로 두고, 그 위에 별도의 오케스트레이션 계층을 추가한다.

1. **두 계층, 두 책임.**
   - **Transport**는 `LLMClient`(ABC) + 구체 클라이언트(`OpenAIClient`,
     `MockLLMClient`, 향후 로컬 클라이언트)로 유지한다. 단일 모델 엔드포인트를 호출하는
     법(`complete` / `complete_json`)만 안다.
   - **Orchestration**은 신설 `LLMGateway`로, 호출부(서비스·워커)가 사용하는 단일
     진입점이다. 라우팅·프라이버시 경계·(Phase 2) 캐시/폴백/검증을 소유하고, 실제
     모델 호출은 `LLMClient`에 위임한다.
2. **네이밍.** 오케스트레이터는 스펙의 `LLMProvider`가 아니라 `LLMGateway`로 한다.
   이로써 repo 컨벤션(`LLMClient`=transport, `XxxProvider`=factory 레벨 외부 어댑터)을
   보존한다. "로컬 모델 백엔드"를 나타내는 target별 stub은 `LocalLLMProvider`
   (transport 쪽, `LLMClient` 구현)로, #133에서 도입한다.
3. **Sync 유지.** `async def`를 도입하지 않는다. `LLMGateway`와 모든 `LLMClient`
   메서드는 repo 나머지와 동일하게 동기로 둔다. 스펙의 `async def generate`는 기각한다.
   동시성이 정말 필요해지면 LLM API를 색칠하는 대신 워커/잡 레벨에서 처리한다.
4. **DI·선택은 그대로.** `LLMGateway`는 기존 factory 패턴으로 조립한다. transport
   선택은 신규 `LLM_PROVIDER` 설정(ADR-008) 뒤로 옮긴다. 생성은 현재 어댑터와 동일한
   명시적 생성자 주입을 쓴다.

## Alternatives

- **transport + 정책을 섞은 단일 `LLMProvider`(스펙 그대로).** 기각. 한 객체에 변경
  이유가 둘 생기고, repo의 `LLMClient`/`XxxProvider` 어휘와 충돌하며, 프라이버시 경계를
  독립적으로 테스트하기 어렵게 만든다.
- **async 채택(`async def generate`).** 기각. repo가 일관되게 동기라, async는
  서비스·워커 전반에 `await`를 전파시키거나 모든 호출부에 브리지를 요구하며, 현재
  규모에서 동시성 이득이 없다.
- **라우팅을 `LLMClient` 구현 안에 넣기.** 기각. transport 클라이언트가 다른
  클라이언트를 알아야 하고, 의존성이 역전되며, 백엔드마다 라우팅 로직이 중복된다.

## Consequences

- 쉬워지는 것: 호출부는 안정적인 단일 `LLMGateway` 표면에만 의존한다. transport
  백엔드(클라우드 → 로컬)를 호출부 수정 없이 교체할 수 있다. 프라이버시 경계와 라우팅을
  실제 모델과 분리해 단위 테스트할 수 있다.
- 어려워지는 것/리스크: 조립·문서화할 계층이 하나 늘고, 기여자는 `LLMClient`
  (transport) vs. `LLMGateway`(orchestration) 구분을 익히고 async 재도입을 자제해야 한다.
- 신규 런타임 의존성·DB 변경 없음. 본 ADR은 문서 전용이며 #133의 타입 경계 작업을
  잠금 해제한다.

## Follow-up

- #133 — TaskType/Sensitivity/Risk enum, `LLMRequest`/`LLMResponse`,
  transport 쪽 `LocalLLMProvider` stub.
- #134 — `LLMRouter` + factory 및 `LLM_PROVIDER` 선택(ADR-008).
- #136 — `LLMGateway` 조립 및 Phase 1 테스트.
- ADR-010 / ADR-011 / ADR-012(Phase 2, #137) — 게이트웨이 내부의 폴백/escalation·캐시·
  출력 검증. 브리핑 소비처가 생길 때까지 보류(deferred).

## Related Documents

- `JongEunLee310/project_stock#132`(본 ADR), Epic `#141`
- `docs/designs/013-llm-adapter.md`(기존 transport 계층)
- `docs/decisions/ADR-008-llm-task-routing-policy.md`
- `docs/decisions/ADR-009-cloud-data-boundary-cloudsafe-projection.md`
