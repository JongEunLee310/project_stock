# Codex Handoff Task

## Source Issue

없음(운영 결함 대응). dev 브랜치의 `tests/test_news_insights.py` 3건이 **날짜가 바뀌면서** 깨졌고,
그 결과 dev 대상 모든 BE PR의 CI가 실패한다.

## Task Summary

news-insights 도메인의 "현재 시각" 획득 지점을 주입 가능한 함수 하나로 모으고, 테스트에서 그 시계를
`SEEDED_AT`으로 고정해 시간이 흘러도 결과가 변하지 않게 만든다.

## Goal

- `tests/test_news_insights.py`가 실행 날짜와 무관하게 통과한다.
- `uv run pytest` 전체 통과, `uv run ruff check .`·`uv run mypy .` 통과.
- 운영 동작(API 응답)은 그대로 — 실제 실행에서는 여전히 `datetime.now(UTC)`를 쓴다.

## Background — 근본 원인 (조사 완료, 재확인 불필요)

- `tests/test_news_insights.py:41`이 `SEEDED_AT = datetime(2026, 7, 21, 10, tzinfo=UTC)`로 **절대 시각**을
  고정하고, seed는 이 시각 기준으로 데이터를 심는다(`detected_at = SEEDED_AT - 1h50m`).
- 반면 서비스는 요청 시점의 `datetime.now(UTC)`로 `as_of`를 잡고 window를 적용한다
  (`app/domains/news_insights/repository.py`의 집계는 `detected_at >= start AND < end`).
- 2026-07-23 기준 시드 데이터가 24시간 창 밖으로 밀려나 집계가 0이 됐다. 07-22까지는 창 안이라
  통과했다(PR #384 CI green이 증거).
- 현재 실패: `test_overview_returns_four_summary_metrics_and_grounded_briefing`(집계 0),
  `test_topic_map_applies_window_and_topic_limit`(window 필터), 
  `test_calendar_returns_upcoming_market_events_with_related_topics`(예정 이벤트가 창 안팎으로 이동).

### 현재 now 호출 지점 (총 6곳, 모두 `as_of or datetime.now(UTC)` 형태)

`app/domains/news_insights/service.py`: 138, 179, 208, 236, 271, 320행.
(`seed.py:75`의 `now or datetime.now(UTC)`는 이미 인자로 주입 가능하므로 **변경하지 않는다**.)

## Implementation Scope

- `app/domains/news_insights/clock.py`(신규, 소형) — `def utcnow() -> datetime: return datetime.now(UTC)`
  한 함수만 둔다. 도메인 내부 시계 주입 지점.
- `app/domains/news_insights/service.py` — 위 6곳의 `datetime.now(UTC)`를 `utcnow()` 호출로 교체.
  `as_of or utcnow()` 형태는 유지(기존 인자 우선순위 그대로).
- `tests/test_news_insights.py` — 테스트 시계를 `SEEDED_AT`으로 고정한다. pytest `monkeypatch`(또는
  autouse fixture)로 `app.domains.news_insights.service.utcnow`를 `lambda: SEEDED_AT`로 대체하는 방식을
  쓴다. 개별 테스트마다 흩뿌리지 말고 **모듈 단위 autouse fixture 하나**로 적용한다.
  - 고정 후 기대값이 달라지는 단언이 있으면 **테스트 기대값을 시드 기준으로 맞춘다**(운영 로직을
    기대값에 맞추려고 서비스/리포지토리를 고치지 말 것).
- 다른 테스트 파일에서 같은 시간 의존이 발견되면 같은 방식으로 고정한다(예: `tests/test_news_insights_models.py`가
  이미 `now=` 인자를 넘기고 있다면 손대지 않는다).

## Out of Scope

- 서비스·리포지토리의 **집계 로직·계약·응답 스키마 변경**. window 기본값 변경. seed 데이터 값 변경.
- 다른 도메인의 시각 처리 리팩터링. 새 의존성 추가(freezegun 등 **설치 금지** — monkeypatch로 충분).

## Protected Files

없음.

## Requirements

- 운영 경로 동작 불변: `utcnow()`는 `datetime.now(UTC)`를 그대로 반환한다.
- 테스트는 실행 날짜·시각과 무관하게 동일한 결과를 낸다(내일 돌려도 통과).
- 기대값을 느슨하게 만들어 통과시키지 않는다(예: `>= 0`으로 완화 금지). 시드 기준의 정확한 값으로 맞춘다.
- 기존 테스트를 약화하지 않는다.

## Test Requirements

- 실패 중인 3건이 통과한다.
- 시계 고정이 실제로 걸렸는지 확인 가능한 형태여야 한다(fixture가 모든 테스트에 적용).
- `uv run pytest` 전체 통과.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`  (전체 — tests·alembic 포함)
- `uv run pytest`
- 추가: 날짜 독립성 확인을 위해 `TZ=UTC uv run pytest tests/test_news_insights.py -q`와
  `faketime` 없이도 논리적으로 시각 의존이 남지 않았는지 코드로 확인(고정 fixture 적용 범위 점검).

## Documentation Impact

없음(내부 테스트 인프라). 설계문서 계약 변경 없음.

## ADR Need

불요. 테스트 시계 주입 지점 추가로, 아키텍처·계약 변경이 아니다.

## Failure Record Need

**필요.** 날짜 경과만으로 dev 전체 CI가 멈춘 사례다. `docs/failures/`(기존 관례 확인 후 해당 위치)에
짧게 기록한다: 증상(3건 동시 실패)·근본 원인(절대 시각 픽스처 + 서비스의 실시간 now)·조치(시계 주입)·
재발 방지(시간 의존 테스트는 시계를 고정한다). 기존 실패 기록 형식이 있으면 그 형식을 따른다.

## Risk Level

Medium — 테스트 인프라 변경이라 회귀 범위는 좁지만, 시계 고정 후 기대값 조정 과정에서 단언을 느슨하게
만들 유혹이 있다. 그 경우 결함을 덮는 셈이 되므로 금지한다.

## Expected Output

- `clock.py`·service 교체·테스트 시계 고정·실패 기록 커밋(한국어 메시지). PR·push는 하지 마라.
- 검증 3종 결과와, 어떤 기대값을 왜 조정했는지 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치(fix/news-insights-test-clock)를 유지한다(자체 브랜치 생성·push·PR 금지).
