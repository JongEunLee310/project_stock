# Codex Handoff Task

## Source Issue

#394 — BE: 에이전트 파이프라인 집계 지표 확장 — 처리 지연·정확도 (세부 수정)

## Task Summary

`GET /api/v1/news-insights/agent-runs` 응답에 `collected_sources`와
`average_run_duration_seconds` 두 필드를 추가한다. 둘 다 기존 컬럼에서 파생하므로 모델·마이그
레이션 변경은 없다. `정확도`는 정의가 없어 이번 범위에서 제외한다.

## Goal

- `GET /agent-runs` 응답이 `collected_sources`(int)와 `average_run_duration_seconds`
  (int | None)를 포함한다.
- 두 값이 시드 데이터에서 실제로 계산돼 나온다. 상수·하드코딩이 아니다.
- 기존 필드(`processed_documents`·`extracted_events`·`active_topics`·`stages`·
  `analysis_version`·`has_delay`·`last_processed_at`)는 이름·의미 모두 그대로다.

## Background

설계 정본은 `docs/designs/394-agent-pipeline-metrics.md`다. **작업 전에 반드시 읽는다.**
산출 정의·이름을 정한 이유·제외 판단이 모두 그 문서에 있다.

요약하면 이렇다.

- **`collected_sources`** — 최근 run의 처리 구간(`agent_runs.started_at` ~ `finished_at`,
  `finished_at`이 `null`이면 조회 시각)에 `collected_at`이 들어오는 `source_documents`의
  `source_name` distinct 개수.
- **`average_run_duration_seconds`** — `finished_at`이 `null`이 아닌 `agent_runs`를
  `started_at` 내림차순 최대 20건 모아 `finished_at - started_at`의 평균(초, 반올림).
  완료된 run이 하나도 없으면 `null`.
- **이름을 `delay`로 두지 않는다.** 목표 처리 시간이 정의된 적이 없어 지연이라 부를 근거가
  없다. 설계 문서 §3에 이유가 있다.
- **`정확도`는 만들지 않는다.** 정답 레이블을 담는 테이블이 없다. 설계 문서 §4 참조.

기존 조회는 `NewsInsightsRepository.latest_agent_run_records()`가 최근 run 1건과 그 스테이지를
가져오고, `NewsInsightsService._agent_runs_response()`가 응답으로 옮긴다. 두 신규 값도 이
경로에 얹는다.

## Implementation Scope

- `app/domains/news_insights/schema.py` — `AgentRunsResponse`에 두 필드 추가.
- `app/domains/news_insights/repository.py` — `AgentRunRecords`에 두 파생값을 담고, 산출에
  필요한 조회를 추가한다. 집계는 **DB 측에서** 수행한다(전량 적재 후 파이썬 집계 금지).
- `app/domains/news_insights/service.py` — 응답 매핑.
- `tests/test_news_insights.py` — 아래 테스트 요구 참조.

## Out of Scope

- 모델·마이그레이션 변경. 두 값 모두 기존 컬럼에서 파생한다. **새 컬럼·새 테이블 금지.**
- `정확도` 관련 필드. 정의가 없으므로 만들지 않는다.
- `active_topics` 제거. 화면에서 빠졌어도 계약에서 빼지 않는다.
- 다른 엔드포인트, 다른 도메인.
- 시드 데이터 값 변경. 기존 시드로 계산이 되는지 확인만 한다. 계산이 되지 않으면 **값을 고치지
  말고 보고한다.**

## Protected Files

없음.

## Requirements

- `collected_sources`는 `ge=0`. 해당 구간에 문서가 없으면 `0`이다. `null`이 아니다.
- `average_run_duration_seconds`는 완료 run이 없을 때만 `null`이다. 0초로 대체하지 않는다.
  없는 것과 0은 다르다.
- 반올림은 초 단위 정수로 한다.
- 시각 비교는 기존 도메인 관례(`UtcDatetime`·`_as_utc`)를 따른다. naive datetime과 aware
  datetime을 섞어 비교하지 않는다.
- 표본 상한 20건은 시각에 의존하지 않게 만들기 위한 값이다. 시간 창(`24h` 등)으로 바꾸지 않는다.
- 타입 힌트를 빠짐없이 붙인다. mypy가 CI 검사에 포함된다.

## Test Requirements

- `GET /agent-runs` 응답에 두 필드가 실제 계산값으로 담기는지 확인하는 테스트를 추가한다.
  **필드 존재만 확인하는 테스트는 받지 않는다.** 값이 맞는지 단언한다.
- `average_run_duration_seconds`가 `null`이 되는 경우(완료 run 없음)를 별도로 덮는다.
- `collected_sources`가 `0`이 되는 경우(구간에 문서 없음)를 덮는다.
- 표본이 20건을 넘을 때 최근 20건만 평균에 들어가는지 확인한다.
- 기존 `agent-runs` 테스트의 단언을 약화시키지 않는다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

세 가지 모두 CI 검사에 포함된다. mypy를 건너뛰지 않는다.

## Documentation Impact

- `docs/designs/307-news-intelligence-phase2.md` §3.6의 `GET /agent-runs` 응답 필드 목록에
  두 필드를 반영한다. 산출 정의는 `docs/designs/394-agent-pipeline-metrics.md`가 정본이므로
  §3.6에서는 필드 이름과 nullable 여부만 적고 그 문서를 참조한다.
- `docs/designs/394-agent-pipeline-metrics.md`는 이미 작성돼 있다. 구현 중 정의를 바꿔야 할
  이유가 생기면 **문서를 고치지 말고 보고한다.**

## ADR Need

불요. 기존 테이블에서 파생하는 응답 필드 추가이고 와이어 컨벤션도 그대로다. 판단 근거는 설계
문서 §7에 있다.

## Failure Record Need

불요. 계약 부족을 메우는 작업이며 실패한 접근을 대체하지 않는다.

## Risk Level

Low — 단일 엔드포인트의 응답 필드 두 개 추가이고 스키마 변경이 없다. 주의할 곳은 시각 비교의
타임존 정합과 평균의 표본 경계다.

## Expected Output

- 위 범위의 커밋(한국어 메시지, `type: 본문` 형식). push·PR은 하지 않는다.
- 검증 3종 결과 보고.
- 시드 데이터로 계산했을 때 두 값이 각각 얼마로 나오는지 보고.
- 산출 정의를 그대로 따를 수 없었던 지점이 있으면 그 이유.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치를 유지한다(자체 브랜치 생성·push·PR 금지).
