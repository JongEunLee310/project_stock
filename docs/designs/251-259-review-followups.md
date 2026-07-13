# Design — 리뷰 후속 라운드: #251 · #259

리뷰 비차단 소견에서 분리된 후속 이슈 2건을 한 라운드로 정리한다.
두 건 모두 와이어 계약(응답 스키마·쿼리 파라미터) 변경이 없다.

## 1. Issue 251 — `_process_asset` 컴프리헨션 부수 효과 분리 (`app/domains/analysis/service.py`)

- 현재 `new_results` 리스트 컴프리헨션의 `if` 절 안에서
  `raw_news_service.save_with_symbol(...)`(DB 쓰기 부수 효과)을 호출해
  신규 저장분을 걸러낸다. 동작은 정확하지만 부수 효과가 필터 조건에
  숨어 있어 읽기 어렵다.
- 명시적 `for` 루프로 풀어 저장 호출과 신규 여부 필터링을 분리한다.
  저장 결과가 `None`이 아닌 항목만 `new_results`에 담는 동일 의미를
  유지한다.
- 동작 변경 없음 — 기존 테스트가 수정 없이 통과해야 한다. 새 동작을
  추가하지 않는다.

## 2. Issue 259 — `/signals/changes` 타임라인 DB 측 계산 (`app/domains/signals/`)

### 현재 구조

`SignalService.list_recent_changes`가 `snapshot_repo.list_all_ordered()`로
`asset_signal_snapshots` 전량을 메모리에 적재한 뒤 Python에서 자산별
인접쌍 파생 → UNCHANGED 제외 → 정렬 → limit을 수행한다. append-only
테이블이라 운영 기간에 비례해 무거워진다.

### 개선 방향

인접쌍 파생·UNCHANGED 제외·since 필터·정렬·limit을 모두 쿼리로 내린다.

- **인접쌍**: LAG window 함수 — `PARTITION BY asset_id`,
  `ORDER BY snapshot_date ASC, captured_at ASC, id ASC` (기존
  `list_all_ordered` 정렬과 동일 기준). 각 행에 이전 스냅샷의
  `signal_type`·`score`·`captured_at`과 이전 행 존재 여부(예: `LAG(id)`)를
  붙인다.
- **UNCHANGED 제외 (SQL 조건)**: 다음 합집합만 남긴다.
  - 이전 행 없음 AND `signal_type IS NOT NULL` (NEW)
  - 이전 행 있음 AND `signal_type`이 이전 값과 다름 — NULL 안전 비교
    필요. SQLAlchemy `is_distinct_from` 사용 (PostgreSQL `IS DISTINCT
    FROM`, SQLite `IS NOT`으로 컴파일되어 양쪽 방언 지원).
- **since 필터**: 바깥 행의 `snapshot_date >= since`에만 적용한다.
  이전 스냅샷이 since 이전이어도 인접쌍 파생에는 사용한다 — 현행
  Python 구현과 동일한 의미(window는 전체 이력 위에서 계산).
- **정렬·limit**: `ORDER BY snapshot_date DESC, captured_at DESC,
  id DESC` + `LIMIT`. 현행 Python 정렬 키와 동일.

### Repository 시그니처 (신규·대체)

```python
class AssetSignalSnapshotRepository:
    def list_change_rows(
        self,
        *,
        since: date | None,
        limit: int,
    ) -> list[SignalChangeRow]:
        # 책임: LAG window로 이전 스냅샷 필드를 붙인 뒤 UNCHANGED 제외·
        #       since 필터·정렬·limit까지 적용한 행을 반환
```

`SignalChangeRow`는 스냅샷 컬럼 + `prev_signal_type` · `prev_score` ·
`prev_captured_at` · 이전 행 존재 여부를 담는 경량 구조(NamedTuple 또는
dataclass, 형태는 구현 재량).

`list_all_ordered`는 이 경로 외 사용처가 없으므로 대체 후 제거한다.

### Service 변경

- `list_recent_changes`는 `list_change_rows` 결과로부터
  `SignalChange`(direction·score_delta·previous_type·previous_captured_at)를
  파생한다. 방향 분류(NEW / CLEARED / ESCALATED / DEESCALATED / CHANGED)는
  기존 `build_change` 의미와 완전히 동일해야 하며,
  `signal_priority_rank`를 재사용한다 — 우선순위 로직을 SQL로 복제하지
  않는다.
- `build_change` 자체는 `changes_by_asset` 경로에서 계속 사용하므로
  유지한다. 중복을 줄이기 위해 방향 분류 부분을 공용 헬퍼로 추출해
  양쪽에서 재사용해도 된다 (구현 재량).
- 응답 조립(asset 조인, `SignalChangeTimelineItem` 구성)은 현행 유지.

### 계약 불변

`GET /api/v1/signals/changes`의 쿼리 파라미터(`limit`·`since`)와 응답
스키마는 변경하지 않는다. `docs/designs/frontend-api-spec.md` 등 계약
문서 갱신 불필요.

## Files

갱신: `app/domains/analysis/service.py`,
`app/domains/signals/repository.py`, `app/domains/signals/service.py`,
`tests/test_signal_snapshots.py` (테스트 추가).

변경 불가: `app/api/v1/endpoints/signals.py`의 계약(경로·파라미터·응답
모델), `build_change`의 외부 의미, `changes_by_asset`·`summary` 경로.

## Test / Verification

- 기존 `tests/test_signal_snapshots.py` 무회귀.
- 추가 커버리지 (#259):
  - 자산 경계 — 서로 다른 자산의 스냅샷이 인접쌍으로 섞이지 않음
    (파티션 정확성).
  - since 경계 — 이전 스냅샷이 since 이전에 있어도 인접쌍으로 사용되어
    방향이 정확히 분류됨.
  - UNCHANGED 제외 — 동일 `signal_type` 연속 행·`signal_type` 모두 NULL
    행이 결과에 없음. 첫 스냅샷이 NULL 타입이면 제외됨.
  - 정렬·limit — 최신순 정렬과 limit 절단.
- `uv run ruff check .` / `uv run mypy .` / `uv run pytest`

## Out of Scope

- 와이어 계약 변경, 뉴스 수집 경로·증분 규칙, 스냅샷 캡처 로직,
  `/signals/summary`·`changes_by_asset` 동작.

## Open Questions

- 없음. since 기본값 도입(이슈의 대안 1안)은 계약 변경이라 채택하지
  않고, LAG 방식(2안)으로 확정한다.
