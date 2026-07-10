# Design — Issue 252: 종목당 현재 dominant 시그널 계약

시그널 목록이 "종목당 현재 시그널"(자산당 1건) 뷰를 제공하도록 `GET /signals` 계약을
확장한다. dominant 선정 규칙은 watchlist의 `WATCHLIST_STATUS_PRIORITY`를 재사용한다.
기존 전체 조회는 하위호환으로 유지한다.

## Background

현재 `GET /signals`는 활성 시그널 행을 전부 반환한다. 한 종목에 고영향 뉴스가 여러 건이면
시그널이 종목당 여러 개 쌓여(실측 AAPL RISK_ALERT 5건, 005930 1건) 시그널 페이지에 애플
카드가 5개 뜨는 등 디자인(종목당 1카드)과 어긋난다. 종목당 하나의 "현재 상태"를 뽑는 규칙은
watchlist에 이미 있다 — `resolve_watchlist_status`(`app/domains/signals/types.py`)가
`WATCHLIST_STATUS_PRIORITY` 순서로 dominant signal_type을 고른다. 같은 우선순위 개념을
시그널 목록에도 적용한다.

이 계약은 로드맵 2단계(시그널 상태 변경 추적)의 기반이다. dominant 정의가 있어야 이후
"전일 대비·변화·최근 변경"도 이 기준 위에서 계산할 수 있다.

## Contract

`GET /signals`에 `view` 쿼리 파라미터를 추가한다.

| 파라미터 | 값 | 의미 |
|---|---|---|
| `view` | `all`(기본) | 기존 동작. 활성(또는 `include_expired` 시 만료 포함) 시그널 행을 모두 반환. |
| `view` | `current` | 자산당 dominant 시그널 1건만 반환. |

- `view=current`는 활성(미만료) 시그널만 대상으로 한다. `include_expired`는 `current`에서
  무시한다(문서·description에 명시). "현재 상태"의 정의상 만료 시그널은 dominant 후보가 아니다.
- `asset_id` 필터, `expand=asset`, 페이지네이션(`page`/`size`)은 기존 규약을 그대로 따른다.
  `asset_id` 지정 시 `current`는 해당 자산의 dominant 1건(있으면)을 반환한다.
- 기본값 `all`이므로 기존 FE·호출자는 영향 없음.

## Dominant 선정 규칙

자산별로 활성 시그널 중 하나를 dominant로 고른다. 정렬 키(우선순위 높은 순):

1. **signal_type 우선순위** — `WATCHLIST_STATUS_PRIORITY` 튜플의 인덱스 오름차순
   (RISK_ALERT > THESIS_BROKEN > SELL_REVIEW > OVERHEATED > BUY_CANDIDATE > WATCH).
   튜플에 없는 미지의 타입은 최하위로 정렬한다(방어적).
2. **score 내림차순** — 동순위 tie-break.
3. **created_at 내림차순 → id 내림차순** — 그 다음 tie-break(결정성 보장).

각 자산에서 위 정렬의 첫 번째 행이 dominant다.

### 목록 정렬·페이지네이션

collapse 후(자산당 1건) 목록 자체의 정렬은 `score desc → created_at desc → asset_id asc`로
한다(FE가 우선순위/신뢰도 기준으로 소비). `total`은 활성 시그널을 가진 서로 다른 자산 수다.
`offset`/`limit`은 collapse된 목록에 적용한다.

## 구현 스케치

### repository.py

- `list_current_by_asset(asset_id: int | None, offset, limit) -> list[Signal]`
  - 활성 시그널만 대상(`_active_clause()` 재사용).
  - signal_type → 우선순위 rank를 `CASE` 식으로 매핑(상수는 `WATCHLIST_STATUS_PRIORITY`에서
    파생, 하드코딩 금지). 미지 타입은 큰 값.
  - `ROW_NUMBER() OVER (PARTITION BY asset_id ORDER BY rank asc, score desc,
    created_at desc, id desc)` 윈도우로 자산별 1위를 표시하고 rank=1 행만 선택.
  - 바깥 쿼리에서 `score desc, created_at desc, asset_id asc` 정렬 후 `offset`/`limit` 적용.
  - `asset_id` 지정 시 해당 자산으로 `where` 제한.
- `count_current(asset_id: int | None) -> int` — 활성 시그널을 가진 distinct asset 수
  (`asset_id` 지정 시 0/1).

CASE 우선순위 매핑은 `WATCHLIST_STATUS_PRIORITY`를 순회해 `{signal_type.value: index}`를 만들어
`case()`에 주입한다. 우선순위 정의가 한 곳(types.py)에만 존재하도록 유지한다.

### service.py

- `list_signals`·`list_signals_expanded`·`count_signals`에 `view` 인자를 추가하거나
  `current` 전용 경로를 분기한다. `list_signals_expanded`의 quote 조합 로직은 재사용한다
  (입력 시그널 목록만 current 기준으로 교체).
- `current`는 `include_expired`를 강제로 무시.

### router (signals.py)

- `view: str = Query(default="all")` 추가. `current`일 때 repo/service의 current 경로로 분기.
- `all` 경로는 기존 코드 그대로.

## Out of Scope

- 시그널 상태 변경 이력 저장(전일 대비·변화·최근 변경) — 로드맵 2단계 후속.
- 룰 엔진·시그널 생성 로직 변경.
- FE 소비(별도 FE 이슈에서 이 계약 연결).
- `evidence` 구조화(로드맵 3단계).

## 검증

- `uv run ruff check .` / `uv run mypy .` / `uv run pytest`
- 신규 테스트:
  - dominant 선정 — 우선순위 순서(RISK_ALERT가 WATCH를 이김 등), score tie-break,
    created_at/id tie-break.
  - `view=current`가 자산당 1건 반환(AAPL 다건 → 1건), `total`이 distinct asset 수.
  - `view=current`가 만료 시그널 제외(`include_expired=true`여도).
  - `asset_id` + `current` 조합, `expand=asset` + `current` 조합.
  - `view=all`(기본) 하위호환 — 기존 동작 불변.

## 문서 영향

- 본 설계 문서.
- `docs/knowledge/product-workflow.md` 시그널 소비 서술에 `view=current` 추가(핸드오프에서 반영).
