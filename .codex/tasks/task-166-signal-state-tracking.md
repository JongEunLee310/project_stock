# Codex Handoff Task

## Source Issue

#257 — BE: 시그널 상태 변경 추적 (자산별 dominant 일별 스냅샷·변화 파생).
설계: `docs/designs/257-signal-state-tracking.md` (먼저 정독할 것).

## Task Summary

자산별 dominant 시그널의 유형·score를 일별 스냅샷으로 기록하고, 인접 스냅샷 diff로 "변화"를
파생해 노출한다. 선행 #252(`view=current`)의 dominant 정의를 재사용한다.

## Goal

완료 시 다음이 참이어야 한다.

- 신규 테이블 `asset_signal_snapshots`와 Alembic 마이그레이션이 존재한다(자산×일 1행, upsert 멱등).
- 일별 job이 `view=current` 로직을 재사용해 자산별 dominant를 스냅샷하고 scheduler에 등록된다.
- `GET /signals?view=current` 응답 항목에 `change` projection이 임베드된다(스냅샷 없으면 null).
- `GET /signals/changes` 타임라인과 `GET /signals/summary?view=current` 전일대비 delta가 동작한다.
- `view=all` 응답은 불변(하위호환).

## Background

`Signal`은 append-only이고 dominant는 `view=current`(`SignalRepository.list_current_by_asset`,
`WATCHLIST_STATUS_PRIORITY` 기반)로 파생된다. 시그널은 `expires_at`으로 만료되므로 새 write
없이도 dominant가 날마다 바뀐다. 그래서 특정 시점 dominant를 물리적으로 기록(스냅샷)하고 인접
시점과 비교해야 한다. 상세 규칙·컬럼·시그니처는 설계 문서에 있다. 우선순위 rank와 카테고리
매핑은 `app/domains/signals/types.py` 단일 소스에서 파생하고 하드코딩하지 않는다.

## Implementation Scope

- `app/domains/signals/` — 스냅샷 model, repository, service(신규 클래스 또는 기존 확장), schema.
- `app/domains/signals/types.py` — 카테고리 매핑 상수·헬퍼 추가(없으면). 우선순위 정의는 재사용.
- `alembic/versions/` — `asset_signal_snapshots` 생성 마이그레이션(down_revision은 현재 head).
- `app/worker/jobs/signal_snapshots.py` — 일별 스냅샷 job(`collect_prices_job` 패턴).
- `app/scheduler/registry.py` — job 등록(cron은 분석 사이클 이후 1일 1회).
- `app/api/v1/endpoints/signals.py` — `view=current`에 change 임베드, `/changes`·`/summary` 추가.
- `tests/` — 아래 Test Requirements.
- `docs/knowledge/product-workflow.md` — 스냅샷 job·changes/summary 계약 서술 추가.

## Out of Scope

- FE 코드(별도 repo·phase 4).
- 근거 불릿 구조화(phase 3).
- 룰 엔진·시그널 생성 로직 변경.
- `view=all` 기존 동작 변경, `list_current_by_asset` dominant 규칙 변경.
- 스냅샷 보존기간·아카이빙.

## Protected Files

없음. 단, `app/domains/signals/types.py`의 `WATCHLIST_STATUS_PRIORITY`·`resolve_watchlist_status`
기존 정의는 변경하지 말고 재사용한다(카테고리 매핑 추가만 허용).

## Requirements

- 스냅샷 테이블은 `signal_type`·`score`를 비정규화 저장한다(시그널 만료·삭제 후에도 과거 dominant
  diff 가능해야 함). 활성 dominant 없는 자산은 `signal_type=null` 스냅샷으로 기록.
- `(asset_id, snapshot_date)` UniqueConstraint. 같은 날 job 재실행은 upsert(멱등).
- change `direction`: NEW/CLEARED/ESCALATED/DEESCALATED/CHANGED/UNCHANGED (설계 규칙표 그대로).
  `score_delta`는 양쪽 non-null일 때만, 이전 스냅샷 부재 시 direction=NEW.
- 목록 임베드는 N+1 없이 배치 조회한다.
- job은 `SessionLocal`·`JobRunService` start/succeed/fail·finally close 패턴을 따른다.
- `/summary`의 카테고리 집계는 FE `signalCategories.ts`와 동일 매핑(관망←WATCH /
  리스크←RISK_ALERT+THESIS_BROKEN / 매수←BUY_CANDIDATE / 리서치←SELL_REVIEW+OVERHEATED).

## Test Requirements

- 마이그레이션 upgrade/downgrade, `(asset_id, snapshot_date)` unique 위반.
- `capture_daily_snapshot` — 자산별 1행, 활성 없는 자산 null 스냅샷, 같은 날 재실행 멱등.
- `build_change` 순수 함수 — 6개 direction 각 케이스, score_delta, 이전 부재 시 NEW.
- `view=current` 응답 `change` 임베드(스냅샷 있음/없음), `view=all` 불변 회귀.
- `GET /signals/changes` — UNCHANGED 제외·시간 역순·limit·since.
- `GET /signals/summary` — 카테고리 집계·전일대비 delta, 스냅샷 부재 시 delta 0.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `NEWS_PROVIDER=mock uv run pytest`

로컬 `.env`의 `NEWS_PROVIDER=rss`는 뉴스 수집 테스트를 실네트워크로 돌려 무관하게 실패시킨다
(#250). 반드시 `NEWS_PROVIDER=mock` 접두사로 pytest를 실행한다. mypy는 no-untyped-def까지
통과해야 한다(CI 검사 3종: ruff+mypy+pytest).

## Documentation Impact

`docs/knowledge/product-workflow.md`에 스냅샷 job과 `/signals/changes`·`/signals/summary` 계약을
추가한다. 설계 문서는 PR에 포함된다.

## ADR Need

불필요. ADR-013 등 상위 결정 범위 내이고, 새 아키텍처 방향이 아니라 확정된 로드맵 2단계의
스키마·job 추가다.

## Failure Record Need

불필요(신규 기능, 회귀·장애 대응 아님).

## Risk Level

Medium. 신규 테이블·job·엔드포인트가 추가되나 기존 계약(`view=all`, dominant 규칙)은 불변이고
스코프가 명확하다. 만료·null dominant·멱등 upsert 경계가 주 리스크 → 테스트로 커버.

## Expected Output

`feat/257-signal-state-tracking` 브랜치에 커밋. 마이그레이션·model·repo·service·job·registry·
endpoint·테스트·설계/워크플로 문서. 3종 검증 통과. 가정과 검증 결과를 보고.

## Rules

- 현재 브랜치 `feat/257-signal-state-tracking`을 유지한다. 새 브랜치를 만들지 않는다.
- Stay within scope.
- Do not weaken verification.
- Do not modify protected definitions listed above.
- Report assumptions and verification results.
