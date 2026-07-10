# Design — Issue 257: 시그널 상태 변경 추적 (자산별 dominant 일별 스냅샷)

자산별 dominant 시그널의 유형·score를 일별로 스냅샷하고, 인접 스냅샷 diff로 "변화"를
파생한다. 시그널 페이지의 세 요소(전일대비 KPI delta·우선순위 변화 표기·최근 변경 타임라인)가
모두 이 스냅샷에서 나온다. 선행 #252(`view=current`)의 dominant 정의를 그대로 재사용한다.

## Background

`Signal`은 append-only(생성 시각만, 갱신 없음)이고 자산별 dominant는 `view=current`로
파생되는 값이다. 시그널은 `expires_at`으로 만료되므로 새 write 없이도 자산의 dominant가
날마다 바뀔 수 있다. 따라서 "변화"를 신뢰성 있게 추적하려면 특정 시점의 dominant를 물리적으로
기록해 두고 인접 시점과 비교해야 한다. 일별 job이 `view=current` 로직을 재사용해 자산별
dominant를 스냅샷으로 남기고, 변화는 스냅샷 diff로 계산한다. 만료로 인한 변화도 job이 균일하게
포착한다.

로드맵 2단계 본체이며, 3단계(근거 불릿)·4단계(FE 연결)와 독립이다. FE 소비는 phase 4 별도
이슈에서 이 계약을 연결한다.

## Data Model

### 신규 테이블 `asset_signal_snapshots` (append-only, 자산×일 1행)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | int PK | |
| `asset_id` | int FK assets.id, index | 스냅샷 대상 자산 |
| `snapshot_date` | date, index | 스냅샷 논리 일자 (일별 dedup 키) |
| `signal_id` | int FK signals.id, nullable | 캡처 시점 dominant 시그널. 활성 dominant 없으면 null |
| `signal_type` | str(20), nullable | dominant 유형 비정규화. null = 활성 시그널 없음 |
| `score` | int, nullable | dominant score 비정규화 |
| `captured_at` | datetime(tz) | job 실행 시각 |
| `created_at` | datetime(tz), server_default now | |

- `UniqueConstraint(asset_id, snapshot_date)` — 하루 재실행 시 upsert(멱등).
- `signal_type`·`score`를 비정규화 저장해 시그널 만료·삭제 후에도 과거 dominant를 diff할 수
  있게 한다(스냅샷은 그 시점의 사실 기록).
- 우선순위 비교는 `signal_type` → `WATCHLIST_STATUS_PRIORITY` rank로 파생한다(하드코딩 금지).

## 변화(change) 파생 규칙

한 자산의 최신 스냅샷과 직전(이전 `snapshot_date`) 스냅샷을 비교해 `direction`과 `score_delta`를
계산한다.

| direction | 조건 |
|---|---|
| `NEW` | 이전 dominant 없음(null) → 현재 있음 |
| `CLEARED` | 이전 있음 → 현재 없음(null) |
| `ESCALATED` | 현재 유형의 우선순위가 이전보다 높음(rank 작아짐) |
| `DEESCALATED` | 현재 유형의 우선순위가 이전보다 낮음(rank 커짐) |
| `CHANGED` | 우선순위 동급이나 유형이 다름 |
| `UNCHANGED` | 유형 동일 |

- `score_delta` = 현재 score − 이전 score (양쪽 non-null일 때만; 아니면 null).
- 이전 스냅샷이 아예 없으면 `direction=NEW`(최초 관측)로 본다.

## 노출 계약

### 1. `view=current` 항목에 `change` projection 임베드

`SignalExpandedResponse`(또는 current 전용 응답)에 `change: SignalChange | null` 필드를 추가한다.

```
SignalChange:
  direction: str        # NEW|CLEARED|ESCALATED|DEESCALATED|CHANGED|UNCHANGED
  score_delta: int | null
  previous_type: str | null
  previous_captured_at: datetime | null
```

- 스냅샷이 없는 자산(아직 job 미실행)은 `change=null`.
- `view=all` 응답은 불변(하위호환).

### 2. `GET /signals/changes` — 최근 변경 타임라인

최근 스냅샷 일자 기준, `direction != UNCHANGED`인 자산 변화를 시간 역순으로 반환한다.

| 파라미터 | 기본 | 설명 |
|---|---|---|
| `limit` | 20 | 반환 개수 |
| `since` | null | 이 일자 이후 변화만 (옵션) |

응답 항목은 asset brief(symbol·name·market) + `change` projection + 현재 dominant 요약.

### 3. 전일대비 카테고리 delta

`GET /signals/summary?view=current` — 현재 dominant를 카테고리(FE 4분류와 동일 매핑)로
집계한 카운트와, 직전 스냅샷 일자 대비 증감을 반환한다.

```
SignalSummary:
  total: int
  by_category: { WATCH|RISK|BUY|RESEARCH: int }
  delta_by_category: { ...: int }   # 전일대비 증감, 스냅샷 부재 시 0
```

카테고리 매핑은 BE `SignalType` → 4분류를 단일 상수로 정의한다(FE `signalCategories.ts`와
동일 규칙: 관망←WATCH / 리스크←RISK_ALERT+THESIS_BROKEN / 매수←BUY_CANDIDATE /
리서치←SELL_REVIEW+OVERHEATED).

## 구현 스케치

### model.py (신규 `app/domains/signals/snapshot_model.py` 또는 model.py 확장)

- `AssetSignalSnapshot` — 위 테이블 매핑.

### repository.py (신규 `SignalSnapshotRepository`)

- `upsert_daily(asset_id, snapshot_date, signal_id, signal_type, score, captured_at) -> None`
  — `(asset_id, snapshot_date)` 충돌 시 갱신(멱등).
- `get_latest(asset_id) -> AssetSignalSnapshot | None`
- `get_previous(asset_id, before_date) -> AssetSignalSnapshot | None`
- `latest_pair_by_asset(asset_ids) -> dict[asset_id, (latest, previous)]` — 목록 임베드용 배치.
- `list_recent_changes(limit, since) -> list[...]` — direction != UNCHANGED 자산 변화.
- `latest_snapshot_date() / previous_snapshot_date()` — summary delta 기준 일자.

### service.py (신규 `SignalSnapshotService` 또는 `SignalService` 확장)

- `capture_daily_snapshot(snapshot_date=today) -> int` — job 진입점. `list_current_by_asset`로
  자산별 dominant를 구하고, 활성 시그널이 사라진 자산은 null 스냅샷으로 기록. upsert 후 건수 반환.
- `build_change(latest, previous) -> SignalChange | null` — diff 규칙 적용(순수 함수).
- `attach_changes(signals) -> list[...]` — current 목록에 change 임베드(배치 조회).
- `list_recent_changes(limit, since)` / `summary(view)` — 노출 계약 2·3.

우선순위 rank·카테고리 매핑은 `app/domains/signals/types.py` 단일 소스에서 파생한다.

### worker/jobs (신규 `app/worker/jobs/signal_snapshots.py`)

- `snapshot_signal_states_job() -> None` — `collect_prices_job` 패턴(SessionLocal·JobRunService
  start/succeed/fail·finally close) 따름. `SignalSnapshotService.capture_daily_snapshot` 호출.

### scheduler/registry.py

- `ScheduleDefinition(job=FunctionSchedulerJob(name="signal_snapshot", func=...), cron=...)`
  등록. cron은 분석 job 이후(장 마감·분석 사이클 뒤) 1일 1회. `enabled`는 기존 패턴 따름.

### router (signals.py)

- `view=current` 경로에서 `attach_changes` 적용(현재 응답에 `change` 추가).
- `GET /signals/changes`, `GET /signals/summary` 엔드포인트 추가.

## Out of Scope

- FE 소비 (phase 4 별도 FE 이슈에서 연결).
- 근거 불릿 구조화 (phase 3).
- 룰 엔진·시그널 생성 로직 변경.
- 스냅샷 보존기간·아카이빙 정책 (당장 불필요, 후속).

## 검증

- `uv run ruff check .` / `uv run mypy .` / `NEWS_PROVIDER=mock uv run pytest`
- 신규 테스트:
  - 마이그레이션 upgrade/downgrade, `(asset_id, snapshot_date)` unique.
  - `capture_daily_snapshot` — 자산별 dominant 1행 기록, 활성 없는 자산 null 스냅샷,
    같은 날 재실행 멱등(upsert).
  - `build_change` — NEW/CLEARED/ESCALATED/DEESCALATED/CHANGED/UNCHANGED 각 케이스,
    score_delta 계산, 이전 스냅샷 부재 시 NEW.
  - `view=current` 응답의 `change` 임베드(스냅샷 있음/없음), `view=all` 불변.
  - `GET /signals/changes` — UNCHANGED 제외·시간 역순·limit·since.
  - `GET /signals/summary` — 카테고리 집계·전일대비 delta, 스냅샷 부재 시 delta 0.

## 문서 영향

- 본 설계 문서.
- `docs/knowledge/product-workflow.md` — 스냅샷 job·changes/summary 계약 추가(핸드오프에서 반영).
