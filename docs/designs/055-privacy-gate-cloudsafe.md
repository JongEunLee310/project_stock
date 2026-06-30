# 055 · PrivacyGate + CloudSafe projection 경계 (원본 entity Cloud 차단)

Status: Frozen
작성: Claude Code (orchestrator)
관련: 이슈 #135, Epic #141, ADR-009(Cloud Data Boundary / CloudSafe Projection)·ADR-007·ADR-008

## 1. 배경

ADR-009는 클라우드 LLM 경계에서 원본 도메인 entity를 금지하고, 화이트리스트로 구성한
전용 CloudSafe projection만 허용하기로 결정했다. redaction(denylist)은 fail-open이라
쓰지 않고, 허용 필드만 담는 별도 타입(whitelist)으로 fail-closed를 만든다.

#133이 `SensitivityLevel`(RAW·SEMI·AGGREGATED·PUBLIC) enum을 이미 도입했다. 본 작업은
그 위에서 경계를 강제하는 두 장치를 도입한다. 하나는 클라우드로 나갈 수 있는 페이로드의
공통 base 타입이고, 다른 하나는 경계에서 그 타입과 민감도를 검사해 위반을 거부하는
`PrivacyGate`다. 첫 CloudSafe projection도 하나 함께 구현해 실제 흐름을 검증한다.

본 작업은 타입·게이트·첫 projection의 **도입과 단위테스트까지**다. 이것을 실제 클라우드
호출 경로에 묶는 `LLMGateway` 조립은 ADR-009·ADR-008이 #136으로 명시했다. 라우터(#134)와
타입(#133)이 그랬듯, 본 경계 장치도 도입·테스트만 하고 살아있는 소비처는 #136이 연결한다.

## 2. 범위

포함:

- 신규 모듈 `app/adapters/llm/privacy.py`:
  - `CloudSafePayload` — 클라우드 반출 가능한 projection의 공통 base 타입.
  - 첫 구체 projection `PortfolioConcentrationSnapshot`(`Portfolio`/`Position`에서 파생한
    집계·구간화 뷰).
  - 원본 entity → 집계 → projection 매핑 함수.
  - `PrivacyGate` — 경계에서 페이로드 타입·민감도 검사(fail-closed).
- `app/adapters/llm/exceptions.py` — `CloudBoundaryViolationError` 추가.
- `app/adapters/llm/__init__.py` — 신규 공개 심볼 re-export.

비포함:

- `LLMGateway`·gateway.py 조립과 PrivacyGate의 실제 배선(#136, ADR-009 Follow-up).
- 라우터/transport/factory 동작 변경(#134에서 완료).
- 캐시·검증(#137), escalation(#140).
- 첫 projection 외의 추가 CloudSafe 타입(브리핑 기능 설계, Phase 2).
- 소규모·엣지 포트폴리오 재식별 방지를 위한 집계 정밀화(ADR-009 Follow-up, Phase 2).
- DB 모델·마이그레이션, HTTP 라우터·schema 변경.

## 3. 계약

### 3.1 `CloudSafePayload` base 타입 (`app/adapters/llm/privacy.py`)

클라우드로 나갈 수 있는 모든 projection의 공통 base다. 타입 수준 화이트리스트의 표지
역할을 한다 — 클라우드 transport(#136)는 이 base를 받도록 시그니처를 좁혀, 원본 entity나
자유형 dict를 인자로 받을 수 없게 만든다.

| 멤버 | 종류 | 책임 |
|------|------|------|
| `sensitivity` | `ClassVar[SensitivityLevel]` | 이 projection의 민감도 등급. 서브클래스가 선언 |
| `as_payload` | `() -> dict[str, Any]` | transport로 보낼 직렬화 dict 반환 |

- frozen pydantic `BaseModel` 기반(불변, 검증 가능, 직렬화 가능). 기존 결과 schema 계열과
  같은 컨벤션.
- base 자체는 추상 표지이며 직접 인스턴스화하지 않는다. `sensitivity`는 서브클래스에서
  반드시 선언한다.

### 3.2 첫 projection `PortfolioConcentrationSnapshot` (`app/adapters/llm/privacy.py`)

`Portfolio`와 그 `Position` 목록에서 파생한, 포지션을 노출하지 않는 집중도 집계 뷰다.
정확 수치(수량·잔액·비중) 대신 **구간(band)과 불리언**만 담는다.

| 필드 | 타입 | 제약 | 책임 |
|------|------|------|------|
| `position_count_band` | `str` | 구간 라벨 | 보유 종목 수 구간(예: `1-5`, `6-15`, `16+`) |
| `largest_position_band` | `str` | 구간 라벨 | 최대 단일 포지션 비중 구간(예: `0-25%`, `25-40%`, `40%+`) |
| `cash_band` | `str` | 구간 라벨 | 현금 비중 구간 |
| `is_concentrated` | `bool` | — | 최대 비중이 `concentration_threshold`를 초과하는지 |

- `sensitivity = SensitivityLevel.AGGREGATED`.
- 절대 수량·잔액·계좌번호·`user_id`·종목 식별자는 담지 않는다(화이트리스트 원칙).
- 구간 경계값은 구현 세부다. 본 단계는 최소·예시 수준으로 두고, 소규모 포트폴리오
  재식별 방지를 위한 정밀화는 Phase 2(브리핑 기능 설계)로 이연한다.

#### 매핑 함수

| 함수 | 시그니처 | 책임 |
|------|----------|------|
| `to_concentration_snapshot` | `(portfolio: Portfolio, positions: Sequence[Position]) -> PortfolioConcentrationSnapshot` | 원본 entity에서 화이트리스트·구간화로 projection 파생(`RawPortfolio → Aggregate → CloudSafe DTO`) |

- 입력은 원본 entity, 출력은 CloudSafe projection이다. 이 함수가 ADR-009의 변환 단계를
  구체화한다.

### 3.3 `PrivacyGate` (`app/adapters/llm/privacy.py`)

클라우드 경계 직전에서 페이로드를 검사한다. 등록된 CloudSafe projection이 아니거나
민감도가 클라우드 허용 등급이 아니면 거부한다. 호출별 판단이 아니라 단일 지점의 계약
강제다(ADR-009 §4, ADR-008의 fail-closed와 일관).

| 멤버 | 시그니처 | 책임 |
|------|----------|------|
| `CLOUD_ALLOWED` | `frozenset[SensitivityLevel]` | 클라우드 허용 등급 = `{AGGREGATED, PUBLIC}`(모듈/클래스 상수) |
| `guard` | `(payload: object) -> CloudSafePayload` | 페이로드가 `CloudSafePayload`이고 민감도가 허용 등급이면 그대로 반환, 아니면 `CloudBoundaryViolationError` |

- `guard`의 거부 조건:
  - `CloudSafePayload` 인스턴스가 아님(원본 entity·자유형 dict 등) → 거부.
  - `payload.sensitivity`가 `CLOUD_ALLOWED`에 없음(`RAW`/`SEMI`) → 거부.
- 안전한 기본값은 "보내지 않음"이다. 알 수 없는 타입은 통과시키지 않는다(fail-closed).
- 로컬로 라우팅된 작업은 프로세스를 떠나지 않으므로 게이트 대상이 아니다(#136에서 클라우드
  분기에만 게이트를 건다).

#### 경계 예외 (`app/adapters/llm/exceptions.py`)

| 타입 | 기반 | 책임 |
|------|------|------|
| `CloudBoundaryViolationError` | 기존 LLM 예외 계열(`LLMCallError`) | 원본 entity 또는 비허용 민감도 페이로드를 클라우드로 보내려는 시도(fail-closed) |

## 4. 검증

- `uv run ruff check .`
- `uv run mypy .` — 신규 코드 전 필드·메서드에 타입 주석(과거 #126 `no-untyped-def` CI
  실패 전례). `ClassVar` 주석 포함.
- `uv run pytest -q` — 신규 테스트:
  - `PrivacyGate.guard`가 `AGGREGATED` CloudSafe projection을 그대로 반환.
  - `guard`가 원본 `Portfolio` entity를 받으면 `CloudBoundaryViolationError`.
  - `guard`가 자유형 dict를 받으면 거부.
  - `RAW`/`SEMI`를 선언한 `CloudSafePayload` 서브클래스는 `guard`가 거부(fail-closed).
  - `to_concentration_snapshot`이 구간·불리언만 담은 projection을 만들고, 그 `as_payload()`
    출력에 절대 수량·잔액·`user_id`가 없으며, 결과가 `guard`를 통과.
  - 기존 LLM/worker 테스트가 계속 통과(회귀 없음).

## 5. 비고

- 본 단계는 ADR-009의 "문서 전용" 다음 첫 구현 단계다. ADR-009 Consequences가 명시하듯
  **프라이버시 민감 경계이므로 머지 전 명시적 사람 리뷰가 필요**하다. 핸드오프·로컬 리뷰는
  진행하되 최종 머지 권한은 개발자에게 있다.
- PrivacyGate는 도입·테스트만 하고, 클라우드 분기에 실제로 거는 배선은 #136(gateway)이
  소유한다(#133 타입·#134 라우터의 선행 도입 패턴과 동일).
- "타입 수준 강제(원본 entity 인자 불가)"는 #136의 클라우드 transport 시그니처를
  `CloudSafePayload`로 좁힘으로써 완성된다. 본 작업은 그 base 타입과 런타임 게이트를
  먼저 마련한다 — 타입은 정적 1차 방어, 게이트는 런타임 fail-closed 2차 방어다.
- 첫 projection은 `Portfolio`/`Position`에서 파생하되 어떤 라이브 호출 경로도 바꾸지
  않는다. 현재 LLM 호출(news/thesis)은 보유 데이터를 접촉하지 않으므로 경계는
  forward-looking이다(이슈 §근거).
