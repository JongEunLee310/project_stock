# Codex Handoff Task

## Source Issue

GitHub issue #260 — BE: 시그널 근거 불릿 key_points 필드.
설계: `docs/designs/260-signal-key-points.md` (반드시 먼저 읽는다).

## Task Summary

`Signal`에 한국어 불릿 배열 `key_points` 필드를 추가하고, 시그널 생성 경로
3곳이 이미 보유한 입력으로 불릿을 생성하며, 응답 계약에 `key_points:
list[str]`(null → 빈 배열)를 노출한다.

## Goal

- `signals.key_points` 컬럼(Text nullable, JSON 문자열 배열) + migration.
- 생성 경로 3곳(HighImpactNewsRule, ThesisConflictRule, 포트폴리오 집중도)이
  2~3개의 한국어 불릿을 생성한다.
- 모든 시그널 응답에 `key_points: list[str]`가 노출된다. 저장값 null → `[]`.
- 3종 검증 통과.

## Background

- `evidence` 필드가 선례다: `SignalRepository._dump_evidence`가
  `json.dumps(..., ensure_ascii=False)`로 저장, `SignalResponse.parse_evidence`
  (`field_validator, mode="before"`)가 역직렬화. `key_points`도 같은 패턴을
  따르되 dict가 아닌 `list[str]`이다.
- 불릿 언어는 한국어(#231 선례). JSON 키·symbol·enum 값은 영어 유지.
- 불릿별 정보 항목은 설계 문서의 표를 따른다. 문구는 자연스러운 한국어로
  조립하되 새 데이터 조회·LLM 호출은 하지 않는다.

## Implementation Scope

- `app/domains/signals/model.py` — `key_points: Mapped[str | None]`
  (`Text, nullable=True`).
- `alembic/versions/` — add column migration (upgrade/downgrade 대칭,
  down_revision은 현재 head에 연결, `uv run alembic heads`로 단일 head 확인).
- `app/domains/signals/schema.py` — `SignalCreate.key_points: list[str] | None
  = None`, `SignalResponse.key_points: list[str]` + before-validator(JSON 문자열
  역직렬화, None → `[]`).
- `app/domains/signals/repository.py` — `create()`에서 `key_points` 직렬화.
- `app/domains/signals/rules/high_impact_rule.py` — 불릿: 영향도(impact_level),
  감성(sentiment가 있을 때만), 대상 뉴스 요지(summary 또는 title).
- `app/domains/signals/rules/thesis_conflict_rule.py` — 불릿: 충돌
  상태(status)와 무효화 발동 여부, 충돌 사유(conflict_result.reason).
- `app/domains/portfolios/service.py`(집중도 시그널 생성부) — 불릿: 비중 vs
  임계치(weight·threshold), 평가금액(market_value).
- `tests/` — 아래 Test Requirements. `tests/test_api_contract.py`의
  `SIGNAL_CONTRACT`에 `key_points` 추가.

## Out of Scope

- LLM 불릿 생성 경로.
- 기존 `reason`·`evidence` 값·계약 변경 (HighImpactNewsRule의 영어 reason도
  그대로 둔다).
- 기존 시그널 backfill.
- `asset_signal_snapshots`·변화 파생(#257) 경로 — 스냅샷은 key_points를
  저장하지 않는다.
- FE.

## Protected Files

- `app/domains/signals/types.py` — 변경 금지.

## Requirements

- `key_points`가 없는 기존 행·`key_points=None` 생성 모두 응답에서 `[]`.
- 불릿은 각 경로가 이미 가진 값으로만 조립한다. 빈 값(예: sentiment None)은
  해당 불릿을 생략한다.
- `view=all`·`view=current` 두 경로 모두 자동 반영되는지 확인한다
  (`SignalCurrentResponse`는 `SignalResponse` 상속).
- POST /signals 수동 생성도 `key_points`를 받고 응답에 반영한다.

## Test Requirements

- migration upgrade/downgrade 왕복.
- 생성 경로 3곳 각각: 불릿 개수(2~3)와 정보 항목 포함을 단언한다. 단언은
  고정 문구 전체 일치보다 핵심 리터럴(예: impact_level 값, threshold 수치)
  포함 여부로 한다.
- sentiment가 None인 뉴스 → 감성 불릿 생략.
- `key_points` null 저장 행 → 응답 `[]`.
- POST /signals에 `key_points` 전달 → 응답 반영.
- `SIGNAL_CONTRACT` 갱신 후 기존 계약 테스트 전체 통과.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `NEWS_PROVIDER=mock uv run pytest`
- `uv run alembic heads` (단일 head)

로컬 `.env`의 `NEWS_PROVIDER=rss` 때문에 pytest는 반드시 `NEWS_PROVIDER=mock`
접두사로 실행한다(#250).

## Documentation Impact

`docs/knowledge/product-workflow.md`에 시그널 응답의 `key_points` 계약을 한 줄
추가한다(있는 섹션에 맞춰 최소로).

## ADR Need

불필요 (확정된 로드맵 3단계의 필드 추가).

## Failure Record Need

불필요.

## Risk Level

Low. 필드 추가·불릿 조립 모두 국소적이고 기존 계약은 확장만 한다.

## Expected Output

`feat/260-signal-key-points` 브랜치에 커밋. model·schema·repository·rules·
portfolio service·migration·테스트·knowledge 문서 변경. 3종 검증 + alembic
heads 통과. 가정과 검증 결과를 보고.

## Rules

- 현재 브랜치 `feat/260-signal-key-points`를 유지한다. 새 브랜치를 만들지 않는다.
- Stay within scope.
- Do not weaken verification.
- Report assumptions and verification results.
