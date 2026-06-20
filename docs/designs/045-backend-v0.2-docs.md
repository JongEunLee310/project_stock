# 045 Backend v0.2 Integration Docs

## Scope

프론트엔드 연결과 후속 개발을 위해 Backend v0.2 기준 통합 문서를 정리한다. 로컬 실행, 환경 변수, API 사용 흐름, Mock/Real provider 전환, 주요 도메인 구조, 프론트엔드 연동 주의사항, 테스트 실행을 한 곳에서 따라 할 수 있게 한다. v0.2 시점 기준이며 후속 기능은 범위 외.

## Current State

- README에 로컬 실행/스택/일부 환경 변수 설명 존재.
- `docs/testing.md`(테스트 실행), `docs/designs/*`(도메인별 설계)에 정보 산재.
- 신규 개발자/프론트 작업자용 통합 온보딩 문서 없음.

## Structure

단일 진입 문서(`docs/backend-v0.2.md` 또는 README 확장):

| 섹션 | 내용 |
| --- | --- |
| 로컬 실행 | `uv sync`, `.env` 준비, uvicorn 실행, DB/Redis(docker-compose). |
| 환경 변수 | `app/core/config.py` Settings 항목별 설명·기본값·민감 정보 주입 방식. |
| API 사용 흐름 | 인증 → 핵심 엔드포인트 호출 예시(요청/응답 샘플 수준). |
| Mock Provider | provider env(mock/real) 전환, 기본 mock 동작. |
| 도메인 구조 | watchlist/asset/news/signal/portfolio 요약. |
| 프론트 연동 주의 | 공통 envelope, 페이지네이션 meta, CORS, 에러 코드. |
| 테스트 실행 | `uv run pytest` 등. |

## Decisions

- 신규 통합 문서로 작성하되 기존 README/`testing.md`와 중복 본문은 만들지 않고 링크로 정리한다.
- 코드 예시는 요청/응답 샘플 수준 — 구현 세부는 설계문서 링크로 대체.
- 순서상 042~044(로깅·health·scheduler) 반영 후 정리하는 것이 이상적(권장 마지막 진행).
