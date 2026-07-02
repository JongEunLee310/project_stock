# ADR-008: LLM Task Routing Policy (task_type → provider, 클라우드 우선)

## Status

Accepted

## Context

하이브리드 LLM 설계(Epic #141, 스펙 §2)는 주어진 작업을 어느 모델 백엔드가 처리할지
정하는 규칙을 필요로 한다. 같은 게이트웨이가 이질적인 작업 — 포트폴리오 브리핑,
대시보드 브리핑, 워치리스트 관찰 메모, 뉴스/공시 요약, 태그·감성, 향후 에이전트 — 을
처리해야 하며, 각 작업은 프라이버시 프로파일과 장기 귀착지(클라우드 vs. 로컬)가 다르다.

정책을 제약하는 사실 두 가지:

1. **출시 시점 로컬은 stub 전용.** 초기 릴리스는 클라우드 우선이며, 로컬 백엔드는
   실제 추론 없는 `LocalLLMProvider` stub(#133)으로만 존재한다. 라우팅 계층은 해당
   백엔드가 살아있지 않은 상태에서도 "이 작업의 미래 primary는 로컬"임을 이미 표현해야
   하며, 그래야 나중의 이관이 코드 변경이 아니라 config 변경이 된다.
2. **라우팅은 호출부 로직이 아니라 지속적 정책.** 각 서비스가 제 백엔드를 고르면
   클라우드→로컬 이관 시 모든 호출부를 고쳐야 하고, 프라이버시 경계(ADR-009)가 호출마다
   우회될 수 있다.

ADR-007은 라우팅을 `LLMGateway` / `LLMRouter`에 두었다. 본 ADR은 그 라우터가 *어떻게*
결정하는지를 고정한다.

## Decision

**작업 유형(task type)** 기준으로, config 주도로 라우팅하되 명시적 클라우드 우선
기본값과 기록된 로컬 target을 둔다.

1. **`TaskType`을 라우팅 키로.** 정본 `TaskType` enum(#133에서 정의, 영어
   `UPPER_SNAKE`)이 각 작업 종류를 식별한다. 라우터는 `task_type → provider`를
   매핑하고, 호출부는 `LLMRequest`에 `task_type`을 실어 보낼 뿐 백엔드를 직접 지정하지
   않는다.
2. **하드코딩 분기가 아닌 config 주도 매핑.** 매핑은 `if task_type == ...` 체인이
   아니라 configuration에 둔다. 신규 `LLM_PROVIDER` 설정
   (`Literal["cloud", "local", "mock"]`, 기본 `cloud`)이 factory가 만들 transport
   백엔드를 선택하며, 기존 `MARKET_PROVIDER` / `NEWS_PROVIDER` 패턴을 답습한다. 작업별
   라우팅 표는 라우터가 읽는 데이터로 표현해, 작업 재배치가 config 수정이 되게 한다.
3. **클라우드 우선 + `future_primary`.** 각 작업은 두 개념을 지닌다. **현재** provider
   (출시 시 클라우드 또는 템플릿)와, 로컬이 성숙하면 가야 할 **미래 primary**
   (`future_primary`). 출시 시 라우팅되는 모든 작업은 클라우드로 귀결되며, 이관 1순위
   후보(워치리스트 메모 최우선, 이후 대시보드 브리핑·뉴스 요약·태그/감성)에는
   `future_primary = local`을 기록해 target을 구전이 아닌 문서로 남긴다.
4. **초기 라우팅 표**(Epic #141 출처, 정본은 거기):

   | TaskType(의도)              | 출시            | 미래 primary              |
   | --------------------------- | --------------- | ------------------------- |
   | 포트폴리오 브리핑           | Cloud           | Cloud (CloudSafe projection) |
   | 대시보드 브리핑             | Cloud           | Local + Cloud escalation  |
   | 워치리스트 관찰 메모        | Cloud/Template  | Local (이관 #1)           |
   | 뉴스 / 공시 요약            | Cloud           | Local + 검증              |
   | 태그 / 감성 / 중복제거      | Local (목표)    | Local                     |
   | 에이전트(향후)             | Cloud           | Cloud + 로컬 microtask    |

5. **미지의 task type은 fail-closed.** 매핑 없는 `task_type`은 조용한 클라우드
   기본값이 아니라 에러다 — 누락된 매핑은 드러나야 하며, 프라이버시 결정이 결부되지
   않은 민감 데이터를 실어 보낼 수 있기 때문이다(ADR-009).

## Alternatives

- **호출부별 라우팅(호출부가 백엔드 선택).** 기각. 정책을 흩뜨리고, 클라우드→로컬
  이관을 N개 파일 수정으로 만들며, 호출부가 프라이버시 게이트를 우회하게 한다.
- **`if task_type` 하드코딩 라우팅.** 기각. 재배치마다 코드 변경·배포가 필요하다.
  config 주도 데이터는 이관을 설정 한 번 바꾸는 일로 줄인다.
- **지금 capability/비용 기반 동적 라우팅.** 시기상조로 기각. 아직 살아있는 로컬
  백엔드도 비용 신호도 없다. 이는 Phase 2 escalation 영역(#140)이지 출시가 아니다.
- **미지의 task type을 클라우드로 기본 처리.** 기각. 프라이버시 경계에서 fail-open
  이다. 매핑 없는 작업이 모르는 새 raw 데이터를 클라우드로 보낼 수 있다.

## Consequences

- 쉬워지는 것: 로컬 백엔드가 실제화되면 작업의 클라우드→로컬 이관이 config 변경이 된다.
  라우팅 표가 의도의 살아있는 문서를 겸한다. 프라이버시 게이트가 지킬 choke point가
  하나로 모인다.
- 어려워지는 것/리스크: 라우팅 표와 `future_primary` 메타데이터를 Epic #141과 동기화해
  유지해야 한다. fail-closed 라우팅은 새 작업 추가 시 의도적 매핑 항목을 요구한다
  (의도된 마찰).
- DB 변경 없음. 설정 하나(`LLM_PROVIDER`)와 라우팅 config 표면을 추가한다. 본 ADR
  단계에서는 문서 전용.

## Follow-up

- #133 — 여기서 소비하는 `TaskType`(및 `Sensitivity`/`Risk`) enum 정의.
- #134 — `LLMRouter`, `LLM_PROVIDER` 설정, factory 배선 구현, 그리고 factory/게이트웨이를
  거치지 않고 `MockLLMClient`를 직접 생성하는 `app/worker/jobs/analysis.py` 정리.
- Phase 2 #140 — 정적 표를 런타임에 덮어쓸 수 있는 위험도 기반 escalation(예: 고위험
  입력 시 로컬 primary → 클라우드).

## Related Documents

- `JongEunLee310/project_stock#132`(본 ADR), Epic `#141`
- `docs/decisions/ADR-007-llm-provider-abstraction.md`
- `docs/decisions/ADR-009-cloud-data-boundary-cloudsafe-projection.md`
- `app/adapters/factory.py`(provider 선택 패턴)
