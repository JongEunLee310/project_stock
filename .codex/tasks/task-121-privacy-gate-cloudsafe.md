# Codex Handoff Task

## Source Issue

JongEunLee310/project_stock#135 — [LLM] PrivacyGate + CloudSafe DTO 경계 — 원본 portfolio/account/holding/trade Cloud 차단

설계: `docs/designs/055-privacy-gate-cloudsafe.md` (Status: Frozen) — 본 핸드오프는 이 설계를 그대로 구현한다.

## Task Summary

클라우드 LLM 경계에서 원본 도메인 entity를 차단하고, 화이트리스트로 구성한 CloudSafe
projection만 허용하는 두 장치를 도입한다: `CloudSafePayload` base 타입과 `PrivacyGate`.
첫 구체 projection(`PortfolioConcentrationSnapshot`)과 매핑 함수도 함께 구현한다.
도입·단위테스트까지이며, 실제 gateway 배선은 #136 범위이므로 건드리지 않는다.

## Goal

작업 완료 시 다음이 참이어야 한다:

- `app/adapters/llm/privacy.py`에 `CloudSafePayload`, `PortfolioConcentrationSnapshot`,
  `to_concentration_snapshot`, `PrivacyGate`가 존재한다.
- `PrivacyGate.guard`가 비-CloudSafe 페이로드(원본 entity·dict)와 `RAW`/`SEMI` 민감도
  페이로드를 `CloudBoundaryViolationError`로 거부하고, `AGGREGATED`/`PUBLIC` CloudSafe
  projection은 그대로 반환한다(fail-closed).
- 첫 projection이 구간·불리언만 담고 절대 수량·잔액·`user_id`를 노출하지 않는다.
- `ruff`/`mypy`/`pytest`가 모두 통과한다.

## Background

- ADR-009(Cloud Data Boundary / CloudSafe Projection)가 근거다. whitelist(fail-closed)
  방식이며 redaction/denylist(fail-open)는 금지다.
- `SensitivityLevel`(RAW·SEMI·AGGREGATED·PUBLIC) enum은 #133에서 이미
  `app/adapters/llm/types.py`에 정의됨. 재정의하지 말고 import해 쓴다.
- 클라우드 허용 등급은 `{AGGREGATED, PUBLIC}`. `RAW`/`SEMI`는 클라우드 금지.
- `Portfolio`/`Position` 모델은 `app/domains/portfolios/model.py`에 있다.
- 본 작업은 #133 타입·#134 라우터와 같은 "도입 후 소비는 다음 이슈" 패턴이다. gateway에
  실제로 거는 배선은 #136이다.

## Implementation Scope

Codex가 변경해도 되는 파일:

- `app/adapters/llm/privacy.py` (신규) — 설계 §3.1~§3.3:
  - `CloudSafePayload` — frozen pydantic `BaseModel` base. `sensitivity: ClassVar[SensitivityLevel]`,
    `as_payload() -> dict[str, Any]`(`model_dump`).
  - `PortfolioConcentrationSnapshot(CloudSafePayload)` — `sensitivity = AGGREGATED`. 필드:
    `position_count_band: str`, `largest_position_band: str`, `cash_band: str`,
    `is_concentrated: bool`.
  - `to_concentration_snapshot(portfolio: Portfolio, positions: Sequence[Position]) -> PortfolioConcentrationSnapshot`
    — 원본 entity에서 구간화·집계로 projection 파생. 구간 경계는 최소·합리적 수준으로
    구현(예시 수준).
  - `PrivacyGate` — `CLOUD_ALLOWED: frozenset[SensitivityLevel] = frozenset({AGGREGATED, PUBLIC})`,
    `guard(payload: object) -> CloudSafePayload`(fail-closed).
- `app/adapters/llm/exceptions.py` — `CloudBoundaryViolationError(LLMCallError)` 추가.
- `app/adapters/llm/__init__.py` — 신규 공개 심볼 re-export(`CloudSafePayload`,
  `PortfolioConcentrationSnapshot`, `PrivacyGate`, `CloudBoundaryViolationError`,
  `to_concentration_snapshot`). `__all__` 알파벳 정렬 유지.
- `tests/` — 신규 테스트 파일(예: `tests/test_llm_privacy.py`).

## Out of Scope

- `LLMGateway`·gateway.py 조립, PrivacyGate의 실제 배선(#136).
- 라우터/transport/factory/worker 동작 변경.
- 첫 projection 외 추가 CloudSafe 타입(Phase 2).
- 재식별 방지를 위한 집계 정밀화(Phase 2).
- DB 모델·마이그레이션, HTTP 라우터·schema 변경.
- 캐시·검증(#137), escalation(#140).

## Protected Files

없음. 보호 파일(`docs/decisions/`, `docs/harness/`, `AGENTS.md`, `CLAUDE.md`, `.codex/`,
`.github/workflows/ci.yml`)은 변경하지 않는다. 설계 문서 `docs/designs/055-*.md`는 이미
작성되어 있으니 수정하지 않는다.

## Requirements

- whitelist 방식만. entity에서 필드를 벗기는 denylist/redaction 금지.
- `PrivacyGate.guard`는 fail-closed: 알 수 없는 타입은 통과시키지 않고 거부.
- projection은 절대 수치 대신 구간/불리언만 노출. 절대 수량·잔액·계좌번호·`user_id`·
  종목 식별자를 담지 않는다.
- `CloudSafePayload`는 불변(frozen). `sensitivity`는 `ClassVar`로 서브클래스가 선언.
- 기존 코드 동작 변경 없음. 라이브 호출 경로를 건드리지 않는다.
- 에러 처리는 경계에서만(`guard`). 불필요한 추상화 추가 금지.

## Test Requirements

`tests/test_llm_privacy.py`(신규):

- `guard`가 `AGGREGATED` CloudSafe projection을 그대로 반환.
- `guard`가 원본 `Portfolio` entity를 받으면 `CloudBoundaryViolationError`.
- `guard`가 자유형 dict를 받으면 거부.
- `RAW`/`SEMI`를 선언한 `CloudSafePayload` 테스트용 서브클래스는 `guard`가 거부.
- `to_concentration_snapshot`이 구간·불리언만 담은 projection을 만들고, `as_payload()`
  출력에 절대 수량·잔액·`user_id`가 없으며, 결과가 `guard`를 통과.
- 기존 LLM/worker 테스트가 계속 통과(회귀 없음).

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest -q`

## Documentation Impact

설계 `docs/designs/055-privacy-gate-cloudsafe.md`가 이미 본 작업을 기술한다. 추가 문서
변경은 불필요하다. ADR-009가 근거이며 본 구현이 그 Follow-up이다.

## ADR Need

불필요. ADR-009가 이미 경계 결정을 확정했고 본 작업은 그 첫 구현이다.

## Failure Record Need

불필요. 신규 기능 도입이며 회귀·장애 대응이 아니다.

## Risk Level

Medium. 프라이버시·보안 경계 코드이나, 도입 후 소비는 #136이라 라이브 경로 동작 변경이
없다. 단, ADR-009 Consequences에 따라 **머지 전 명시적 사람 리뷰가 필수**다(로컬 리뷰 후
개발자 최종 승인).

## Expected Output

- 위 Implementation Scope의 파일 변경.
- feature 브랜치 `feat/privacy-gate-cloudsafe`에 커밋, PR 생성(`Closes #135`).
- 세 검증 커맨드 통과 로그.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
