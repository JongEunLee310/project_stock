# Codex Handoff Task

## Source Issue

Issue #58 (제목 Issue 38): `[BE] 환경 변수 및 설정 구조 정리`

## Task Summary

개발/테스트/운영 환경 설정을 분리하고 민감 정보가 코드에 포함되지 않도록 설정 구조를 정리한다. `.env.example`을 현재 `Settings`와 일치하도록 보강하고 `APP_ENV`와 mock/real 전환을 명확히 한다. #57(CORS)·#59(마이그레이션)의 선행 작업이다.

## Goal

- 신규 개발자가 `.env.example`만으로 로컬 환경을 구성할 수 있다.
- 민감 정보가 repository에 포함되지 않는다(placeholder만).
- mock/real provider 전환 설정이 명확하다.
- 개발/테스트/운영 구분이 가능하다(`APP_ENV`).

## Background

- **설계문서 우선**: `docs/designs/038-config-structure.md`를 먼저 읽고 따른다. 달라지면 갱신.
- 현재 `app/core/config.py`는 `pydantic-settings` 단일 `Settings`(`env_file=".env"`). `.env.example`은 `OPENAI_API_KEY`/`LLM_TIMEOUT_SECONDS` 등 일부 변수 누락.
- `.gitignore`는 `.env*` 무시 + `!.env.example` 예외 — 민감 파일 추적 안전(유지).
- mock/real 전환 변수(`MARKET/NEWS/DISCLOSURE/PORTFOLIO_PROVIDER`) 이미 존재 — 어댑터 팩토리와 연결됨, 동작 변경 금지.

## Implementation Scope

- `app/core/config.py` — `APP_ENV: Literal["dev","test","prod"] = "dev"` 추가. 단일 `Settings` 유지. prod placeholder 경고 등 검증은 최소 범위만(선택).
- `.env.example` — 현재 `Settings`의 모든 변수를 placeholder/주석과 함께 망라(누락분 보강).
- `docs/designs/038-config-structure.md` — 달라지면 갱신.
- `README.md` 또는 설정 문서 — 환경 변수 구성/로딩 방식 간단 설명(필요 시).

## Out of Scope

- 환경별 Settings 서브클래스/다중 config 파일 도입.
- 실제 secret/키 값 커밋.
- 어댑터 팩토리(`app/adapters/factory.py`) 동작 변경.
- CORS 설정(= #57 범위).

## Protected Files

변경하지 않는다: `AGENTS.md`, `CLAUDE.md`, `.github/workflows/ci.yml`, `docs/harness/`, `docs/decisions/`.

## Requirements

- `APP_ENV` 추가, 단일 `Settings` 유지.
- `.env.example`이 모든 변수를 placeholder로 망라, 실제 민감 값 없음.
- mock/real 전환 변수 의미를 `.env.example` 주석으로 명확화.
- 기존 설정 로딩 동작 불변.

## Test Requirements

- `Settings`가 env에서 값을 로드하고 기본값을 적용함을 확인하는 테스트.
- `APP_ENV` 기본값/오버라이드 테스트.
- `.env.example`의 키 집합이 `Settings` 필드와 일치하는지 확인하는 테스트(권고).
- `uv run pytest` 전체 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/designs/038-config-structure.md`, `.env.example`, `README.md`(환경 구성 안내).

## ADR Need

불필요 — 기존 설정 구조 보강. 환경별 서브클래스 등 구조 변경 없음.

## Failure Record Need

없음.

## Risk Level

Low — 설정 항목 추가 + 문서. 단, 다른 작업(#57/#59)의 선행이므로 먼저 머지 권장.

## Expected Output

- `config.py`(`APP_ENV`) + `.env.example` 보강 + 테스트.
- lint/typecheck/pytest 통과. PR body에 `Closes #58`.

## Rules

- 단일 Settings 유지(서브클래스 도입 금지).
- 실제 민감 값 커밋 금지.
- 보호 파일 변경 금지.
- 가정(APP_ENV 기본 dev, 검증 범위)과 결과 보고.
