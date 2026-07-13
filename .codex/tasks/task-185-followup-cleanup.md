# Codex Handoff Task

## Source

이슈 #247 · #250 · #276 — 후속 정리 라운드. 설계:
`docs/designs/247-250-276-followup-cleanup.md` (먼저 전체를 읽는다).

## Task Summary

리뷰 후속 이슈 3건을 정리한다. 동작 계약 변경 없음. 설계 문서
1~3절을 그대로 따른다:

1. `docker-compose.yml` — `backend`·`worker`·`scheduler`·`postgres`·
   `redis`에 `restart: unless-stopped` (판단 근거 주석 한 줄).
2. `tests/conftest.py` — 최상단에서 `MARKET_PROVIDER`·
   `NEWS_PROVIDER`·`DISCLOSURE_PROVIDER`·`PORTFOLIO_PROVIDER`를
   mock으로 고정 (`os.environ` + 로드된 `settings` 필드 덮어쓰기,
   WHY 주석). 로컬 `.env` 값과 무관하게 `uv run pytest`가 결정적으로
   통과해야 한다.
3. `app/domains/research_coverage/service.py` —
   `item_count == 0` 위임 분기를 `get_coverage` 호출부의
   `_collected_axis`/`_not_collected_axis` 직접 선택으로 올린다.
   `tests/test_research_coverage.py`는 수정 없이 통과해야 한다.

## Out of Scope

- 배포용 compose·CD·CI 워크플로, worker 예외 처리, 프로바이더 구현,
  coverage 응답 계약.
- `docs/designs/266-research-queue-contract.md`(추적되지 않는 파일)
  불변.

## Rules

- 현재 브랜치 `chore/247-250-276-followup-cleanup`에서 그대로
  작업한다. 새 브랜치를 만들지 않는다.
- 커밋은 1개로 만든다. push는 하지 않는다.
- 커밋 메시지는 한국어 `type: 본문` 형식으로 작성한다.

## Verification

- `docker compose config > /dev/null`
- `uv run ruff check .`
- `uv run mypy .`
- `NEWS_PROVIDER=rss uv run pytest` (전체 통과 — 격리 증명)
- `uv run pytest` (env 접두사 없이 전체 통과)
