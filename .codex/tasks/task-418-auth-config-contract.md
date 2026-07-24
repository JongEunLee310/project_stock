# Codex Handoff Task

## Source Issue

#418 — BE: 인증·설정 계약 강화 — SECRET_KEY 프로덕션 fail-fast·decode_token 계약 명시

## Task Summary

전면 코드 분석에서 확인된 인증·설정 계약의 취약 지점 두 가지를 방어 코드와 계약 명시로 강화한다. 로직 변경은 없다.

## Goal

완료 시 다음이 참이어야 한다.

- `APP_ENV=="production"`이면서 `SECRET_KEY`가 기본값(`"change-me-in-production"`)이면 `Settings` 초기화가 실패한다.
- 그 외 환경(개발·테스트)에서는 기본값이어도 정상 동작한다.
- `decode_token()`이 서명·만료만 검증하며 토큰 `type` 확인은 호출자 책임임을 docstring으로 명시한다.
- 위 두 동작에 대한 단위 테스트가 존재한다.

## Background

- `app/core/config.py`는 이미 `@model_validator(mode="after")`로 `validate_cors_credentials`를 두고 있다. 동일 패턴을 재사용한다.
- `SECRET_KEY` 기본값(`config.py:13`)은 개발 편의를 위해 유지하되, 프로덕션 유출 경로만 부팅 단계에서 차단한다.
- `decode_token()`(`security.py:21`) 호출자는 현재 두 곳(`app/api/v1/deps.py`의 access 검증, `app/domains/users/service.py`의 refresh 검증)이며 모두 `type`을 검증 중이다. 신규 호출자의 누락을 계약으로 예방하는 것이 목적이다.

## Implementation Scope

- `app/core/config.py` — `APP_ENV`/`SECRET_KEY` 조합을 검증하는 `@model_validator(mode="after")` 추가.
- `app/core/security.py` — `decode_token()`에 한국어 docstring 추가(호출자의 `type` 검증 책임 명시).
- `tests/` — 위 두 동작에 대한 단위 테스트 추가(기존 config/security 테스트 파일이 있으면 그곳에, 없으면 신규).

## Out of Scope

- `decode_token()`의 시그니처·반환 타입·검증 로직 변경 금지(docstring만 추가).
- 토큰 `type` 검증을 `decode_token` 내부로 이동시키지 말 것(호출자 책임 유지).
- CORS·기타 설정 검증 로직 변경 금지.
- `SECRET_KEY` 기본값 문자열 자체는 변경하지 말 것(개발 편의 유지).

## Protected Files

없음.

## Requirements

- 프로덕션 fail-fast는 명확한 에러 메시지를 포함한다(기존 `validate_cors_credentials`의 메시지 톤과 일관).
- `APP_ENV` 판별은 기존 설정 필드를 사용하고 새 환경 변수를 도입하지 않는다.
- docstring 본문은 한국어, 코드 기호·식별자는 영어로 작성한다.

## Test Requirements

- 프로덕션 + 기본 SECRET_KEY → 초기화 실패를 검증하는 테스트.
- 프로덕션 + 비기본 SECRET_KEY → 정상 초기화를 검증하는 테스트.
- 개발/테스트 환경 + 기본 SECRET_KEY → 정상 초기화를 검증하는 테스트.

## Verification Commands

```
uv run ruff check .
uv run mypy app
uv run pytest
```

## Documentation Impact

없음. 규약 문서화는 별도 이슈(#420)에서 다룬다.

## ADR Need

불필요. 새 도메인·테이블·외부 의존성·아키텍처 결정이 없고, 기존 검증 패턴의 확장이다.

## Failure Record Need

불필요. 장애 대응이 아니라 예방적 방어 코드 추가다.

## Risk Level

Low — 단일 파일 검증 추가와 docstring 1건, 로컬/테스트 동작 무영향.

## Expected Output

- `config.py`·`security.py` 변경과 테스트를 포함한 diff.
- `dev`를 타깃으로 하는 PR에 이 핸드오프 문서와 함께 포함될 구현.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
