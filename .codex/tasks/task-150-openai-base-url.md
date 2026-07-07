# Codex Handoff Task

## Source Issue

https://github.com/JongEunLee310/project_stock/issues/221

## Task Summary

`OPENAI_BASE_URL` 설정을 추가해 OpenAI 호환 로컬 프록시(openai-oauth)로 LLM 호출을 보낼 수 있게 한다.

## Goal

- `OPENAI_BASE_URL`이 비어 있으면 기존 동작과 완전히 동일하다.
- `OPENAI_BASE_URL`이 설정되면 OpenAI SDK가 해당 주소로 요청을 보낸다.
- `OPENAI_BASE_URL` 설정 + `OPENAI_API_KEY` 미설정 조합에서 RuntimeError가 발생하지 않고 더미 키로 대체된다.

## Background

개발 기간 동안 ChatGPT 구독 기반 로컬 프록시(openai-oauth, https://github.com/EvanZhouDev/openai-oauth )를 사용한다. `npx openai-oauth` 실행 시 `http://127.0.0.1:10531/v1`에 OpenAI 호환 엔드포인트가 뜬다(출처: 이슈 #221에 링크된 소개 글 — 구현 시 리터럴을 하드코딩하지 말고 설정으로만 받는다). 프록시는 API 키를 검증하지 않으므로 키 없이 동작해야 한다. 개발 전용 기능이지만 코드에는 "개발 전용" 분기를 두지 않고 설정 하나로 켜고 끈다.

현재 코드:

- `app/core/config.py` — `OPENAI_API_KEY: str | None`, `OPENAI_MODEL: str` 설정 존재. `OPENAI_BASE_URL` 없음.
- `app/adapters/factory.py` `get_llm_client()` — `cloud` 분기에서 `OPENAI_API_KEY` 미설정 시 `RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=cloud")`를 던지고 `OpenAIClient(api_key=..., model=...)`를 생성.
- `app/adapters/llm/openai.py` `OpenAIClient.__init__(self, api_key, model)` — `openai.OpenAI(api_key=api_key)` 생성. `base_url` 미지원.

## Implementation Scope

- `app/core/config.py` — `OPENAI_BASE_URL: str | None = None` 필드 추가.
- `app/adapters/llm/openai.py` — `OpenAIClient.__init__`에 `base_url: str | None = None` 파라미터 추가, `openai.OpenAI(api_key=..., base_url=...)`로 전달 (None이면 SDK 기본 동작).
- `app/adapters/factory.py` — `get_llm_client()` cloud 분기에서 `settings.OPENAI_BASE_URL`을 `OpenAIClient`에 전달. `OPENAI_BASE_URL`이 설정된 경우에는 `OPENAI_API_KEY`가 비어 있어도 RuntimeError를 던지지 않고 더미 키(예: `"local-proxy"`)를 사용. `OPENAI_BASE_URL`이 없으면 기존 검증 그대로 유지.
- `.env.example` — `OPENAI_BASE_URL=` 항목 추가. 주석에 로컬 프록시 용도, 그리고 Docker Compose 내부에서 백엔드를 실행하는 경우 호스트의 프록시에 접근하려면 `http://host.docker.internal:10531/v1`을 사용해야 한다는 안내 포함.
- `tests/test_llm_factory.py` — 아래 Test Requirements 반영.

## Out of Scope

- `LLMGateway`, budget/cache/escalation, local/mock provider 로직 변경.
- 새 의존성 추가.
- Dockerfile, docker-compose, CI 워크플로우 변경.
- openai-oauth 자체의 설치·실행 자동화(사용자가 별도 터미널에서 실행).

## Protected Files

없음. 보호 파일을 수정하지 않는다.

## Requirements

- `OPENAI_BASE_URL` 미설정(기본 None) 시 기존 코드 경로·에러 메시지가 그대로 유지된다.
- `base_url` 전달은 `OpenAIClient` 생성자에서만 처리하고, `complete()` 등 호출 경로는 변경하지 않는다.
- 더미 키 리터럴은 factory 안에 상수로 두고, "개발 전용" 조건 분기(예: APP_ENV 검사)는 추가하지 않는다.

## Test Requirements

`tests/test_llm_factory.py`에 추가:

- `OPENAI_BASE_URL` 설정 + `OPENAI_API_KEY` 없음 → `get_llm_client("cloud")`가 RuntimeError 없이 `OpenAIClient`를 반환하고, 클라이언트의 base_url이 설정값을 반영한다.
- `OPENAI_BASE_URL` 없음 + `OPENAI_API_KEY` 없음 → 기존 RuntimeError 유지.
- `OPENAI_BASE_URL` 설정 + `OPENAI_API_KEY` 설정 → 두 값 모두 반영.

기존 테스트를 약화하거나 삭제하지 않는다. 실제 네트워크 호출 없이 생성자 속성 검증으로 확인한다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

`.env.example` 주석으로 충분하다. README·설계 문서 갱신은 불필요.

## ADR Need

불필요. 새 도메인·테이블·외부 의존성·아키텍처 결정이 없고, 기존 어댑터에 설정 하나를 통과시키는 변경이다.

## Failure Record Need

불필요. 반복 실패 이력이 없다.

## Risk Level

Low — 설정 미사용 시 기존 동작과 동일하고, 변경 파일이 4개 이내로 좁다.

## Expected Output

- 변경 파일: `app/core/config.py`, `app/adapters/llm/openai.py`, `app/adapters/factory.py`, `.env.example`, `tests/test_llm_factory.py`
- 검증 3종 통과 결과 보고
- 가정·잔여 위험 보고

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치에서 그대로 작업한다. 새 브랜치를 만들지 않는다.
