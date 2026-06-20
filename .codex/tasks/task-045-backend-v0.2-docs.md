# Codex Handoff Task

## Source Issue

Issue #65 (제목 Issue 45): `[BE] Backend v0.2 통합 문서 정리`

## Task Summary

프론트엔드 연결과 후속 개발을 위해 Backend v0.2 기준 통합 문서를 정리한다. 로컬 실행, 환경 변수, API 사용 흐름, Mock/Real provider 전환, 도메인 구조, 프론트 연동 주의사항, 테스트 실행을 한 문서에서 따라 할 수 있게 한다.

## Goal

- 프론트엔드 작업자가 백엔드 코드를 깊게 보지 않아도 API를 사용할 수 있다.
- 신규 개발자가 로컬 실행부터 API 테스트까지 따라 할 수 있다.
- Mock Provider와 실제 Provider 전환 방식이 설명된다.

## Background

- **설계문서 우선**: `docs/designs/045-backend-v0.2-docs.md`를 먼저 읽고 따른다.
- README에 로컬 실행/스택/일부 환경 변수 존재. `docs/testing.md`(테스트), `docs/designs/*`(도메인 설계)에 정보 산재.
- 설정은 `app/core/config.py`의 단일 `Settings`. provider env(`*_PROVIDER`)는 mock/real.
- 권장 순서상 #62~#64(로깅·health·scheduler) 반영 후 작성.

## Implementation Scope

- 단일 통합 문서(`docs/backend-v0.2.md` 또는 README 확장):
  - 로컬 실행(`uv sync`, `.env`, uvicorn, DB/Redis docker-compose).
  - 환경 변수 항목별 설명·기본값·민감 정보 주입.
  - API 사용 흐름(인증 → 핵심 엔드포인트, 요청/응답 샘플).
  - Mock/Real provider 전환.
  - 주요 도메인 구조 요약.
  - 프론트 연동 주의(공통 envelope, 페이지네이션 meta, CORS, 에러 코드).
  - 테스트 실행(`uv run pytest`).

## Out of Scope

- 코드/동작 변경(문서 전용 작업).
- 중복 본문 작성 — 기존 README/`testing.md`/설계문서는 링크로 연결.

## Protected Files

변경하지 않는다: `AGENTS.md`, `CLAUDE.md`, `.github/workflows/ci.yml`, `docs/harness/`, `docs/decisions/`.

## Requirements

- 신규 개발자가 로컬 실행→API 호출→테스트까지 단일 문서로 따라 할 수 있다.
- provider 전환 방식이 명시된다.
- 기존 문서와 중복 없이 링크로 정리된다.

## Test Requirements

- 코드 변경 없음 — 문서가 실제 명령/엔드포인트와 일치하는지 수동 확인.
- 회귀 방지로 `uv run pytest` 통과 확인.

## Verification Commands

```bash
uv run ruff check .
uv run pytest
```

## Documentation Impact

- 신규 `docs/backend-v0.2.md`(또는 README), `docs/designs/045-backend-v0.2-docs.md`. 기존 README/`testing.md`와의 링크 정합성.

## ADR Need

불필요 — 문서 정리.

## Failure Record Need

없음.

## Risk Level

Low — 문서 전용.

## Expected Output

- Backend v0.2 통합 문서 + 기존 문서 링크 정리.
- pytest 통과. PR body에 `Closes #65`.

## Rules

- 코드 변경 금지(문서 전용).
- 중복 본문 금지 — 링크로 연결.
- 문서가 실제 명령/엔드포인트와 일치하는지 검증.
- 보호 파일 변경 금지.
