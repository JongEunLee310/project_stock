# FAILURE-004: News Insights 테스트 시계 드리프트

## Status

Accepted

## Background

`tests/test_news_insights.py`는 `SEEDED_AT`이라는 절대 시각을 기준으로 뉴스 인사이트 데이터를
심고, 서비스 API의 시간 창 필터 결과를 검증했다. 이 테스트는 작성 당시와 가까운 날짜에는
통과했지만 실행 날짜가 시드 시각에서 멀어지면 같은 데이터와 코드로도 결과가 달라졌다.

## Failed Approach

테스트 데이터의 시각만 `SEEDED_AT`으로 고정하고, 서비스의 기준 시각은 요청 시점의
`datetime.now(UTC)`를 그대로 사용했다. 고정된 시드와 움직이는 서비스 시계가 같은 시간 축에
있다고 전제한 채 24시간 집계, 토픽 맵, 예정 이벤트를 단언했다.

## Failure Cause

집계와 조회는 서비스가 만든 현재 시각을 기준으로 시간 창을 계산한다. 시드 이벤트는
`SEEDED_AT` 기준으로 고정되어 있으므로 실제 날짜가 흐를수록 조회 창 밖으로 이동한다.
2026-07-23에는 시드 이벤트와 토픽이 24시간 창 밖으로 밀렸고, 캘린더의 예정 이벤트도
실시간 기준 창과 시드 기준 창 사이에서 포함 여부가 달라졌다.

## Impact

`tests/test_news_insights.py`의 overview, topic map, calendar 테스트 3건이 동시에 실패해 dev 대상
백엔드 PR의 전체 CI를 막았다. 운영 API의 집계 로직이나 응답 계약에는 결함이 없었지만,
실행 날짜에 따라 테스트 결과가 달라져 회귀 검증을 신뢰할 수 없었다.

## Replacement Decision

news-insights 도메인에 실제 운영 시각을 반환하는 `utcnow()` 진입점을 하나 두고, 서비스의 현재
시각 획득을 모두 이 함수로 모은다. 운영에서는 계속 `datetime.now(UTC)`를 반환한다. 테스트
모듈에서는 pytest `monkeypatch` 기반 autouse fixture로 서비스 시계를 `SEEDED_AT`에 고정하고,
캘린더 입력과 기대값도 같은 시드 시각을 기준으로 정확히 검증한다.

시간 창이나 예정 시각에 의존하는 테스트는 데이터 시각만 고정하지 않고, 조회 기준 시계도 함께
고정한다. 기대값을 범위 단언으로 완화하지 않고 고정 시계에서 나오는 정확한 값을 사용한다.

## Retry Conditions

실시간 시계를 사용하는 기존 방식으로 돌아갈 조건은 없다. 테스트가 실제 시간 경과 자체를
검증해야 한다면 별도의 테스트에서 명시적으로 시계를 진행시키고 경계 전후의 정확한 결과를
단언한다.

## Related Documents

- `.codex/tasks/task-news-insights-test-clock.md`
- `app/domains/news_insights/clock.py`
- `tests/test_news_insights.py`
