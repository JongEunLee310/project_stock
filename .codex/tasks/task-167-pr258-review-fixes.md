# Codex Handoff Task

## Source Issue

PR #258 로컬 리뷰(`docs/reviews/pr-258.md`) 비차단 소견 S2·S3 반영.

## Task Summary

시그널 스냅샷 변화 파생의 두 가지 경계를 개선한다 — (S2) dominant 없는 자산의 최초
스냅샷이 타임라인에 NEW로 노출되는 노이즈 제거, (S3) `upsert_daily`의 IntegrityError
복구를 savepoint 기반으로 바꿔 같은 배치의 선행 flush 유실 방지.

## Goal

- 최초 스냅샷의 `signal_type`이 null인 자산은 `/signals/changes` 타임라인에 나타나지 않는다.
- `upsert_daily`가 unique 충돌을 복구할 때 같은 세션에서 앞서 flush된 다른 스냅샷이
  유실되지 않는다.
- 기존 계약·테스트는 모두 유지된다(3종 검증 통과).

## Background

- **S2**: `build_change`(`app/domains/signals/service.py`)는 `previous is None`이면 무조건
  `NEW`를 반환한다. 최초 스냅샷의 `signal_type`이 null(활성 시그널 없음)인 자산도 `NEW`가
  되어 `/changes` 타임라인에 dominant 없는 항목으로 노출된다. job 첫 실행일에 시그널 없는
  자산 전부가 타임라인에 등장하는 노이즈가 생긴다.
- **S3**: `SignalSnapshotRepository.upsert_daily`(`app/domains/signals/repository.py`)는
  IntegrityError 시 `self.db.rollback()`으로 세션 전체를 되돌린다. `capture_daily_snapshot`
  루프는 flush만 하고 마지막에 commit하므로, 충돌 복구가 같은 배치의 선행 자산 스냅샷을
  함께 되돌린 뒤 해당 자산만 재시도해 선행 기록이 조용히 유실될 수 있다(동시 기록자 존재 시).

## Implementation Scope

- `app/domains/signals/service.py` — `build_change`: `previous is None and
  latest.signal_type is None`일 때 `NEW` 대신 `UNCHANGED`를 반환한다(타임라인은
  UNCHANGED를 제외하므로 노출이 사라짐). `view=current` 임베드의 `change`도 동일 규칙을
  따른다(최초 관측이지만 상태 없음 = 변화 없음).
- `app/domains/signals/repository.py` — `upsert_daily`: 신규 insert를
  `self.db.begin_nested()` savepoint로 감싸고, IntegrityError 시 savepoint만 롤백한 뒤
  기존 행을 다시 조회해 갱신 경로로 진행한다. 세션 전체 `rollback()` 호출을 제거한다.
- `tests/test_signal_snapshots.py` — 아래 Test Requirements.

## Out of Scope

- S1(`/changes` 전량 메모리 적재) — 후속 이슈 #259로 분리됨.
- 스냅샷 스키마·마이그레이션 변경.
- direction 6종 규칙표의 나머지 케이스 변경.
- `view=all` 경로.

## Protected Files

없음.

## Requirements

- S2 변경 후에도 "이전 스냅샷 부재 + 현재 dominant 있음"은 여전히 `NEW`다. 바뀌는 것은
  "이전 부재 + 현재도 null"인 단일 케이스뿐이다.
- S3의 savepoint 복구 후에는 기존과 동일하게 최신 값으로 갱신·flush까지 완료한다. 복구
  불가(재조회에도 없음) 시 기존처럼 예외를 전파한다.

## Test Requirements

- `build_change(latest(signal_type=None), previous=None)` → `UNCHANGED` (기존 NEW 기대를 수정).
- `/signals/changes`에 최초 null 스냅샷 자산이 나타나지 않는 케이스.
- `upsert_daily` 충돌 복구 시 같은 세션의 선행 flush가 보존되는 테스트 — 같은
  `(asset_id, snapshot_date)` 행을 별도 커넥션(또는 사전 커밋)으로 만들어 IntegrityError를
  유도하고, 복구 후 선행 자산 스냅샷과 충돌 자산의 갱신 값이 모두 남는지 확인한다.
  테스트 구성이 과도하게 복잡해지면 단순화 가능하되 "선행 flush 보존"은 반드시 검증한다.
- 기존 테스트 전체 통과 유지.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `NEWS_PROVIDER=mock uv run pytest`

로컬 `.env`의 `NEWS_PROVIDER=rss` 때문에 pytest는 반드시 `NEWS_PROVIDER=mock` 접두사로
실행한다(#250).

## Documentation Impact

없음(내부 경계 개선, 계약 불변). 리뷰 기록 R2는 orchestrator가 작성한다.

## ADR Need

불필요.

## Failure Record Need

불필요.

## Risk Level

Low. 두 개선 모두 국소적이고 기존 계약·테스트로 회귀가 방어된다.

## Expected Output

`feat/257-signal-state-tracking` 브랜치에 커밋. service·repository·테스트 변경.
3종 검증 통과. 가정과 검증 결과를 보고.

## Rules

- 현재 브랜치 `feat/257-signal-state-tracking`을 유지한다. 새 브랜치를 만들지 않는다.
- Stay within scope.
- Do not weaken verification.
- Report assumptions and verification results.
