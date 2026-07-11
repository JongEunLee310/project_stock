# Codex Handoff Task

## Source Issue

#269 — BE: 촉매(이벤트) 타임라인 계약 — 실적·제품·규제 등 예정 이벤트
`gh issue view 269`

설계 문서: `docs/designs/269-catalyst-timeline.md` (반드시 먼저 읽는다)

## Task Summary

`GET /api/v1/assets/{asset_id}/catalysts?limit=10`을 신설한다. 신규 도메인
`app/domains/catalysts/`에 결정적 mock 템플릿 기반 `CatalystService`를
구현한다. 신규 테이블·마이그레이션 없음.

## Goal

작업 완료 시 다음 상태여야 한다.

- 엔드포인트가 `{ asset_id, events: [...] }`를 반환한다. 이벤트 필드는
  `event_date`(date) · `title`(한국어) · `event_type`(설계 문서 enum 10값) ·
  `is_estimated`(bool). `event_date` 오름차순, 오늘(UTC) 이후만, limit 적용.
- 자산 미존재 404 `ASSET_NOT_FOUND`, 미인증 401 (기존 패턴 동일).
- mock은 `asset.id` 기반 템플릿 로테이션으로 결정적이며, 오늘 기준 상대
  일자로 이벤트 4~5건을 생성한다 (설계 문서 Service 절).
- `uv run ruff check .`, `uv run mypy .`,
  `NEWS_PROVIDER=mock uv run pytest`가 전부 통과한다.

## Background

- 선례: `app/domains/research_summary/`(mock 템플릿 로테이션 구조 참고),
  라우트 등록은 `app/api/v1/endpoints/assets.py`의
  `research-summary`·`news-disclosure`와 같은 방식.
- 응답 projection 네이밍: 'DTO' 금지, `*Projection`/`*Response` 사용.
- 로컬 `.env`의 `NEWS_PROVIDER=rss` 때문에 검증은 `NEWS_PROVIDER=mock`으로
  실행한다.

현재 브랜치 `feat/269-catalyst-timeline`에서 그대로 작업한다. 새 브랜치를
만들지 않는다.

## Implementation Scope

**신설**
- `app/domains/catalysts/__init__.py`, `schema.py`, `service.py`
- `tests/test_catalysts.py`

**갱신**
- `app/api/v1/endpoints/assets.py` — GET 라우트 1개 추가.

**변경 불가**
- 다른 도메인, alembic, 시장 어댑터.

## Test Requirements

- 정상 응답: 구조·정렬(오름차순)·오늘 이후 필터·limit 적용·enum 값 유효성.
- 결정성: 같은 asset_id 두 번 호출 시 동일 응답.
- 404(자산 미존재)·401(미인증).
- autoincrement 등 실행 순서 의존 단언 금지 (PR #273 B1 전례 — id 리터럴
  하드코딩 금지).

## Out of Scope

- 촉매 실수집(테이블·잡·실 소스), next_earnings_date 라이브 연동, FE.

## Rules

- 커밋은 1개로 만든다. push는 하지 않는다.
- 커밋 메시지는 한국어 `type: 본문` 형식으로 작성한다.
- 필요하지 않은 추상화를 추가하지 않는다.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `NEWS_PROVIDER=mock uv run pytest`
