# Codex Handoff Task

## Source Issue

GitHub Issue #252 — 종목당 현재 dominant 시그널 계약 신설. 설계: `docs/designs/252-current-signal-per-asset.md`.

## Task Summary

`GET /signals`에 `view=current` 모드를 추가해 자산당 dominant 시그널 1건만 반환한다.
dominant 선정은 watchlist의 `WATCHLIST_STATUS_PRIORITY`를 재사용한다. 기존 `view=all`은 불변.

## Goal

- `GET /signals?view=current` 호출 시 활성 시그널을 자산당 1건(dominant)으로 collapse해 반환한다.
- `view` 미지정/`all`이면 기존 동작 그대로.
- `expand=asset`, `asset_id`, 페이지네이션이 `current`와 조합 동작한다.
- ruff / mypy / pytest 모두 통과.

## Background

- 현재 한 종목에 고영향 뉴스가 여러 건이면 시그널이 종목당 여러 개 쌓여 시그널 페이지가
  디자인(종목당 1카드)과 어긋난다.
- dominant 규칙은 `app/domains/signals/types.py`의 `WATCHLIST_STATUS_PRIORITY`
  (RISK_ALERT > THESIS_BROKEN > SELL_REVIEW > OVERHEATED > BUY_CANDIDATE > WATCH)를 재사용한다.
  우선순위 정의는 types.py 한 곳에만 존재해야 한다(하드코딩 복제 금지).
- 활성 판정은 `SignalRepository._active_clause()`를 재사용한다.
- 설계 문서 `docs/designs/252-current-signal-per-asset.md`의 규칙·정렬·페이지네이션을 그대로 따른다.

## Implementation Scope

- `app/domains/signals/repository.py` — current 조회·카운트 메서드 추가.
- `app/domains/signals/service.py` — `view` 분기.
- `app/api/v1/signals.py` — `view` 쿼리 파라미터 추가·분기.
- `docs/knowledge/product-workflow.md` — 시그널 소비 서술에 `view=current` 반영.
- 관련 테스트 파일(`tests/` 하위 signals 테스트).

## Out of Scope

- 시그널 상태 변경 이력 저장(전일 대비·변화·최근 변경).
- 룰 엔진·시그널 생성 로직·`evidence` 구조화.
- 모델/스키마 필드 추가(계약 형태는 기존 `SignalResponse`/`SignalExpandedResponse` 그대로).
- FE 변경.

## Protected Files

없음. 위 Implementation Scope 밖 파일은 수정하지 않는다.

## Requirements

- `view` 쿼리 파라미터: `str = Query(default="all")`. 값 `current`일 때만 collapse 경로.
- **dominant 선정 규칙**(자산별 활성 시그널 중):
  1. signal_type 우선순위 = `WATCHLIST_STATUS_PRIORITY` 인덱스 오름차순. 튜플에 없는 타입은 최하위.
  2. score 내림차순.
  3. created_at 내림차순 → id 내림차순.
- **repository**:
  - `list_current_by_asset(asset_id: int | None, offset, limit) -> list[Signal]`.
    - 활성 시그널만 대상.
    - signal_type→rank를 `WATCHLIST_STATUS_PRIORITY`에서 파생한 dict로 SQLAlchemy `case()`에 주입.
    - `ROW_NUMBER() OVER (PARTITION BY asset_id ORDER BY rank asc, score desc, created_at desc,
      id desc)` 윈도우로 자산별 1위(rank=1)만 선택.
    - 바깥 정렬 `score desc, created_at desc, asset_id asc` 후 offset/limit 적용.
    - `asset_id` 지정 시 where 제한.
  - `count_current(asset_id: int | None) -> int` — 활성 시그널을 가진 distinct asset 수.
- **service**: `list_signals`/`list_signals_expanded`/`count_signals`에 `view`를 전달하거나 current
  전용 경로 분기. `current`는 `include_expired`를 무시한다. expanded의 quote 조합 로직은 재사용.
- **router**: `current`일 때 current 경로, 아니면 기존 경로. `total`은 current면 `count_current`.
- 하위호환: `view` 없거나 `all`이면 응답·정렬 완전 동일.

## Test Requirements

- dominant 우선순위: RISK_ALERT가 WATCH를 이김 등 priority 순서 검증.
- score tie-break, created_at/id tie-break.
- `view=current`가 자산당 1건(AAPL 다건 → 1건), `total` == distinct asset 수.
- `view=current`가 만료 시그널 제외(`include_expired=true`여도 무시).
- `asset_id` + `current`, `expand=asset` + `current` 조합.
- `view=all`(기본) 하위호환 — 기존 테스트 유지·불변.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

세 명령 모두 통과해야 한다. mypy 누락 금지.

## Documentation Impact

- `docs/knowledge/product-workflow.md`에 `view=current` 소비 방식 한 줄 반영.
- 설계 문서는 이미 작성됨(수정 불필요, 구현이 벗어나면 assumption으로 보고).

## ADR Need

불필요. 기존 계약의 하위호환 확장이며 아키텍처 결정 변경 없음.

## Failure Record Need

불필요.

## Risk Level

Low-medium. 윈도우 함수·CASE 정렬이 SQLite에서 결정적으로 동작하는지 tie-break 테스트로 확인.

## Expected Output

- 위 스코프 파일 변경 + 신규 테스트.
- ruff/mypy/pytest 통과 결과.
- 현재 브랜치(`feat/252-current-signal-per-asset`) 유지. 새 브랜치 만들지 말 것.
- 가정·검증 결과 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
