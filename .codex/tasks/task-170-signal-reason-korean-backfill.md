# Codex Handoff Task

## Source Issue

GitHub issue #264 — 시그널 reason 한국어 전환 및 기존 시그널 key_points
backfill (실사용 피드백 라운드, 이슈는 핸드오프 후 발번).
설계: `docs/designs/264-signal-reason-korean-backfill.md` (반드시 먼저 읽는다).

## Task Summary

`HighImpactNewsRule`의 영어 보일러플레이트 reason을 간결한 한국어로 바꾸고,
key_points 도입(#260) 이전에 생성된 기존 시그널 행을 데이터 마이그레이션으로
backfill한다(reason 접두어 제거 + key_points 재구성).

## Goal

- 신규 시그널 reason: `영향도 {impact_level} 뉴스: {summary}`
- 기존 접두어(`High-impact news requires review: `) 행: reason이 새 형식으로
  바뀌고, `key_points`가 NULL이던 행은 룰과 동일한 불릿으로 채워진다.
- 3종 검증 통과.

## Background

- 문구 위치는 `app/domains/signals/rules/high_impact_rule.py:25` 한 곳뿐이다.
- 해당 룰은 `risk_level` 컬럼에 impact_level(HIGH/CRITICAL)을 그대로 저장하고,
  `evidence` JSON에 `impact_level`·`sentiment`(null 가능)를 보존한다.
- `key_points` 컬럼은 Text에 JSON 문자열 배열을 직렬화해 저장한다. 직렬화
  규약은 `app/domains/signals/service.py`의 기존 저장 경로를 확인해 따른다.
- 현재 alembic head는 `c3d4e5f60062`다.

## Implementation Scope

- `app/domains/signals/rules/high_impact_rule.py` — reason 문자열을 Goal의
  형식으로 교체. key_points 불릿 3종은 변경하지 않는다.
- `alembic/versions/` 새 데이터 마이그레이션 (down_revision =
  `c3d4e5f60062`)
  - upgrade: 접두어로 시작하는 행을 조회해 행별로 reason을 새 형식으로 갱신.
    impact_level은 `risk_level` 컬럼에서 읽고, NULL이면 접두어 제거만 한다.
    `key_points IS NULL`인 행은 설계 문서의 불릿 3종(감성은 evidence의
    sentiment가 non-null일 때만)으로 backfill한다.
  - connection 조회 → Python 변환 → 행별 UPDATE. ORM 모델 import 금지.
  - downgrade: no-op. 사유를 docstring에 남긴다.
- `tests/test_signals.py` 등 기존 HighImpactNewsRule 테스트의 reason 리터럴
  단언을 새 형식으로 갱신 (HIGH·CRITICAL 두 경로).

## Out of Scope

- ThesisConflictRule·포트폴리오 집중도 reason (이미 한국어).
- key_points 불릿 문구 변경.
- 응답 계약(schema)·FE 변경.
- 마이그레이션 pytest (수동 검증 절차는 설계 문서 참고).

## Protected Files

- `app/domains/signals/types.py` — 변경 금지.
- 기존 `alembic/versions/*.py` — 변경 금지 (새 파일만 추가).

## Rules

- 현재 브랜치 `feat/signal-reason-korean-backfill`에서 그대로 작업한다. 새
  브랜치를 만들지 않는다.
- 커밋은 1개로, 메시지는 한국어 `type: 본문` 형식으로 만든다. push는 하지
  않는다.
- 필요하지 않은 추상화를 추가하지 않는다.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `NEWS_PROVIDER=mock uv run pytest`

## Acceptance Criteria

- 신규 HIGH 뉴스 시그널의 reason이 `영향도 HIGH 뉴스: {summary}` 형식으로
  생성된다 (CRITICAL도 동일 형식).
- 마이그레이션 upgrade가 접두어 행의 reason을 새 형식으로 바꾸고, key_points
  NULL 행을 불릿 3종(또는 sentiment 없으면 2종)으로 채운다. 접두어가 없는
  행은 건드리지 않는다.
- downgrade는 no-op으로 실행 가능하다.
- 기존 테스트 전체와 갱신된 리터럴 단언이 통과한다.
