# Design — 후속 정리 라운드: #247 · #250 · #276

리뷰 비차단 소견에서 분리된 후속 이슈 3건을 한 라운드로 정리한다.
세 건 모두 동작 계약 변경이 없다 (compose 정책 · 테스트 격리 ·
리팩터링).

## 1. Issue 247 — compose restart 정책 (`docker-compose.yml`)

- `worker` · `scheduler` · `backend`에 `restart: unless-stopped`
  적용. worker 크래시 시 잡 소비가 멈춘 채 방치되는 문제(오늘도
  worker가 Exited 상태로 발견됨)의 직접 대응.
- `postgres` · `redis`에도 동일 적용 — 판단 근거: 데모·상시 구동에서
  데이터 서비스만 수동 복구로 남길 이유가 없고, `unless-stopped`는
  개발 중 의도적 `docker compose stop`을 존중하므로 로컬 워크플로를
  해치지 않는다. 이 근거를 compose 주석 한 줄로 남긴다.
- crash loop 원인 확인은 기존 `docker logs`로 충분 (별도 변경 없음).

## 2. Issue 250 — pytest 프로바이더 격리 (`tests/conftest.py`)

- conftest 최상단(다른 `app.*` import보다 앞)에서 프로바이더 env
  4종을 mock으로 고정: `MARKET_PROVIDER` · `NEWS_PROVIDER` ·
  `DISCLOSURE_PROVIDER` · `PORTFOLIO_PROVIDER` = `mock`.
  `os.environ` 설정 + 이미 로드된 `settings` 객체 필드도 함께
  덮어쓴다 (pydantic settings가 import 시 `.env`를 읽는 순서 문제
  방어 — WHY 주석).
- 이후 `uv run pytest`는 `.env` 값과 무관하게 결정적으로 통과해야
  한다 — 기존 검증 관례의 `NEWS_PROVIDER=mock` 접두사는 더 이상
  필요 없다 (있어도 무해).
- 개별 테스트가 특정 프로바이더 값을 명시적으로 setenv/monkeypatch
  하는 경우는 그대로 동작해야 한다 (전역 기본값만 고정).

## 3. Issue 276 — research_coverage 분기 가독성 (`app/domains/research_coverage/service.py`)

- `item_count == 0 → _not_collected_axis` 위임 분기를
  `_collected_axis` 내부에서 `get_coverage` 호출부로 올린다:
  집계 결과의 `item_count > 0` 여부로 `_collected_axis` /
  `_not_collected_axis`를 직접 선택. 4개 축(NEWS · PRICE ·
  EARNINGS · VALUATION) 공통 헬퍼로 중복을 줄여도 된다.
- 동작 변화 없음 — 기존 `tests/test_research_coverage.py`가 수정
  없이 통과해야 한다 (테스트 파일 변경 금지).

## Files

갱신: `docker-compose.yml`, `tests/conftest.py`,
`app/domains/research_coverage/service.py`.

변경 불가: 배포용 compose·CD 워크플로, 프로바이더 구현, coverage
응답 계약·기존 테스트 파일들(#250에서 실네트워크 호출 테스트를
mock으로 바꿔야 하는 경우만 예외적으로 해당 테스트 수정 허용).

## Test / Verification

- `docker compose config` 통과 (restart 정책 문법 확인).
- `uv run ruff check .` / `uv run mypy .`
- `NEWS_PROVIDER=rss uv run pytest`와 `NEWS_PROVIDER=mock uv run
  pytest` 결과 동일 (전체 통과 — #250 수용 기준).
- env 접두사 없는 `uv run pytest`도 통과.

## Out of Scope

- worker 예외 처리 로직, 프로바이더 구현, 분석 파이프라인, CI
  워크플로.

## Open Questions

- 없음. restart 정책 전 서비스 일관 적용과 conftest 전역 mock
  고정은 이 문서로 확정한다.
