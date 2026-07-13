# Codex Handoff Task

## Source

이슈 #282 — 과거 이벤트 이력 계약. 설계:
`docs/designs/282-earnings-event-history.md` (먼저 전체를 읽는다).

## Task Summary

과거 실적 발표 이력을 수집·저장하고 조회 계약을 신설한다.
**catalysts 계약과 earnings-summary 계약은 변경하지 않는다.** 설계
문서 1~4절을 그대로 따른다:

1. `EarningsEvent` 모델(`earnings_events`, UniqueConstraint
   `(symbol, market, event_date)`) + alembic 마이그레이션 (단일 헤드)
   + `app/db/models.py` 등록.
2. `EarningsProvider`에 `get_earnings_events` 추가 — yfinance
   `earnings_dates` 매핑(순수 함수 분리, 같은 날짜 dedup, 네트워크
   호출 테스트 금지) + mock(과거 8건·미래 1건, null 케이스 포함).
3. `EarningsIngestionService.collect_and_save` 확장 — 리포트 upsert 후
   이벤트 upsert. repository에 `upsert_event`·
   `get_events(symbol, market, start, end)` 추가. 신규 job·라우트 없음.
4. `app/domains/asset_events/` 신설 —
   `GET /assets/{asset_id}/events?range=3M` (enum `1M/3M/6M/1Y`,
   인증 필수). 과거(오늘 이하)만 event_date 오름차순 반환, surprise는
   조회 시 파생(actual·estimate null 또는 estimate 0이면 null), title
   필드 없음.

## Test

설계 문서 Test 절을 그대로 따른다. `tests/test_asset_events.py` 신규,
`tests/test_earnings_ingestion.py`·`tests/test_providers.py`·
`tests/test_api_contract.py` 갱신. 수치 단언은 픽스처 출처 주석,
id 리터럴 단언 금지.

## Out of Scope

- FE 변경, catalysts 전환, 공시 이벤트 타입, 수집 스케줄 변경.
- `app/domains/earnings/schema.py`·`service.py`,
  `app/domains/catalysts/`, worker job·라우트, 다른 도메인.
- `docs/designs/266-research-queue-contract.md`(추적되지 않는 파일)
  불변.

## Rules

- 현재 브랜치 `feat/282-event-history`에서 그대로 작업한다.
  새 브랜치를 만들지 않는다.
- 커밋은 1개로 만든다. push는 하지 않는다.
- 커밋 메시지는 한국어 `type: 본문` 형식으로 작성한다.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `NEWS_PROVIDER=mock uv run pytest`
- `uv run alembic heads` (단일 헤드)
