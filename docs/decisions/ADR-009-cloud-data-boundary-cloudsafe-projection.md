# ADR-009: Cloud Data Boundary / CloudSafe Projection

## Status

Accepted

## Context

하이브리드 설계는 출시 시 여러 작업을 클라우드 LLM으로 라우팅한다(ADR-008). 그
작업들은 사용자가 비공개로 남기를 합리적으로 기대하는 금융 데이터 — 포트폴리오 보유,
계좌 잔액, 개별 거래, 식별자 — 를 다룬다. 스펙(§3)은 어떤 원본 도메인 entity도
프로세스를 떠나 클라우드 provider로 가지 않도록 요구하되, 클라우드 작업이 절대
포지션이나 신원을 노출하지 않으면서도 유용할 만큼의 맥락(예: 집중도, 섹터 구성, 최근
변동)으로 추론할 수 있게 해야 한다.

질문은 그 경계를 *어떻게* 지속적으로 강제하느냐다. ADR-007이 모든 클라우드 호출 앞에
단일 choke point(`LLMGateway`)를 두었음을 전제로:

1. **무엇이 경계를 넘을 수 있는가**를 호출별 판단이 아니라 계약으로 표현.
2. **유출을 어떻게 막는가** — 알려진 객체에서 필드를 제거(redaction/denylist)할지,
   허용된 필드만 담는 별도 객체를 구성(whitelist)할지.
3. **민감도의 공통 어휘**를 두어 라우팅과 리뷰가 위험을 일관되게 추론.

## Decision

클라우드 경계에서 원본 entity를 금지하고, 화이트리스트로 구성한 전용 CloudSafe
projection을 요구한다. (CloudSafe projection은 HTTP 라우터의 `schema`가 아니라, 기존
어댑터 경계 객체와 같은 계열의 게이트웨이 경계 전용 타입이다 — entity에서 화이트리스트·
집계로 파생한 뷰라는 뜻으로 "projection"을 쓴다.)

1. **원본 entity는 절대 클라우드로 보내지 않는다.** ORM/도메인 entity — `Portfolio`,
   `Account`, `Holding`, `Trade` 및 동급 — 를 클라우드 `LLMRequest`에 직렬화하지 않는다.
   게이트웨이의 프라이버시 게이트(`PrivacyGate`, #135)는 페이로드가 등록된 CloudSafe
   projection이 아닌, 클라우드로 라우팅된 모든 요청을 거부한다.
2. **redaction이 아니라 whitelist.** CloudSafe projection은, 구성상 명시적으로 허용된
   집계·익명화 필드(예: 비중, 비율, 버킷, 파생 신호 — 절대 수량·잔액·계좌번호·사용자
   신원은 제외)만 담는 별도 타입이다. entity를 받아 필드를 벗기는 방식(denylist)은
   쓰지 않는다. denylist는 fail-open이기 때문이다 — 새로 추가된 entity 필드가 기본적으로
   유출된다. whitelist는 fail-closed다 — 새 필드는 누군가 의도적으로 projection에 더하기
   전까지 존재하지 않는다.
3. **민감도 등급**을 라우팅(ADR-008)과 프라이버시 게이트가 함께 쓰는 공통 어휘로:
   - `RAW` — 원본 entity / PII / 절대 포지션. 클라우드로 절대 안 나감.
   - `SEMI` — 부분 식별 가능 또는 부분 집계. CloudSafe projection으로 변환 후에만 클라우드.
   - `AGGREGATED` — 익명화된 집계/파생 지표. 클라우드 가능.
   - `PUBLIC` — 이미 공개된 데이터(예: 시장 뉴스 텍스트). 클라우드 가능.
   클라우드 라우팅은 `AGGREGATED` / `PUBLIC` 페이로드(또는 변환된 `SEMI`)에만 허용된다.
   `RAW`는 로컬 전용.
4. **단일 choke point에서 강제.** 경계 검사는 transport 선택 전에 게이트웨이 내부에서
   수행하므로 어떤 호출부도 우회할 수 없다(ADR-008의 fail-closed 라우팅과 일관). 로컬로
   라우팅된 작업은 데이터가 프로세스를 떠나지 않으므로 projection 요구에서 면제된다.
5. **정본 영어 `UPPER_SNAKE` enum**을 민감도 등급에 사용해 repo의 wire-enum 컨벤션
   (ADR-002 / C8)을 따른다.

## Alternatives

- **entity에 redaction / denylist.** 기각. fail-open이다. 새 entity 필드·관계·`__repr__`
  변경마다 비공개 데이터가 조용히 나갈 위험이 있다. 안전한 기본값은 "보내지 않음"이어야
  한다.
- **각 호출부가 안전한 데이터를 넘기리라 신뢰.** 기각. 보안 결정을 강제 없이 여러
  호출부에 분산시킨다. 한 번의 실수가 유출이다.
- **원본 데이터를 암호화/토큰화해 전송.** 기각. 클라우드 모델이 암호문으로 추론할 수
  없고, 토큰화해도 구조·신원은 여전히 나간다. 전송 비밀성은 풀어도 "모델이 비공개
  포지션을 본다"는 문제는 못 푼다.
- **자유형 dict 페이로드 + 런타임 필드 검사.** 기각. 정적 타이핑을 잃고 whitelist를
  암묵적으로 만든다. 타입 있는 projection은 허용 표면을 한곳에서 리뷰 가능하게 한다.

## Consequences

- 쉬워지는 것: 허용된 클라우드 표면이 리뷰 가능한 소수의 projection 타입 집합이 된다. 필드
  추가가 의도적이고 diff로 드러나는 행위가 된다. 라우팅과 리뷰가 하나의 민감도 어휘를
  공유한다. 경계에 테스트 가능한 단일 choke point가 생긴다.
- 어려워지는 것/리스크: 각 클라우드 작업은 손수 만든 projection과 원본 entity로부터의 매핑이
  필요해 entity를 그대로 던지는 것보다 선행 작업이 많다. 집계 로직 자체가
  소규모·엣지 포트폴리오의 재식별을 피해야 한다(호출부 책임, 브리핑 기능 설계에 기재).
- DB 변경 없음. projection 타입과 `PrivacyGate`를 도입한다. 본 ADR 단계에서는 문서 전용.
  프라이버시 민감 경계이므로 구현(#135)은 머지 전 명시적 사람 리뷰가 필요하다.

## Follow-up

- #133 — 여기서 쓰는 `Sensitivity` enum(및 `TaskType`/`Risk`) 정의.
- #135 — 게이트웨이 경계에서 `PrivacyGate`와 첫 CloudSafe projection 구현. 클라우드로 라우팅된
  원본 entity가 거부되는지 테스트 추가.
- 브리핑 기능 설계(Phase 2) — 포트폴리오 브리핑 출시 전, 소규모 포트폴리오의 재식별을
  피하는 집계 정의.

## Related Documents

- `JongEunLee310/project_stock#132`(본 ADR), Epic `#141`
- `docs/decisions/ADR-007-llm-provider-abstraction.md`
- `docs/decisions/ADR-008-llm-task-routing-policy.md`
- `docs/decisions/ADR-002-domain-error-code-enum.md`(wire-enum 컨벤션)
