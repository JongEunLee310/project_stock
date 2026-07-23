# Codex Handoff Task

## Source Issue

#394 후속 — `collected_sources` 산출 정의 정정

## Task Summary

직전 커밋(`3b5e625`)의 `collected_sources`가 최근 run의 처리 구간으로 문서를 잘라 세도록
구현돼 있다. 이 정의가 틀렸다. 시간 구간을 없애고 `source_documents` 전체의 고유
`source_name` 개수로 바꾼다.

## Goal

- `collected_sources`가 `source_documents`의 고유 `source_name` 개수를 반환한다.
- 시드 데이터로 조회하면 `0`이 아니라 실제 출처 수가 나온다.
- `average_run_duration_seconds`의 동작은 그대로다.

## Background

**정정 이유는 `docs/designs/394-agent-pipeline-metrics.md` §2를 읽어라.** 설계 문서는 이미
갱신돼 있다.

요지는 이렇다. run은 자기가 도는 동안 들어온 문서가 아니라 **그 전에 쌓인 문서를 처리**한다.
run 구간(`started_at` ~ `finished_at`)으로 `collected_at`을 자르면 처리 대상과 무관한 집합을
세게 된다. 시드 데이터에서 이 오류가 그대로 드러나 값이 `0`이 됐다. 문서는 기준 시각
1시간 55분·1시간 25분 전에 수집되고 run은 15분 전에 시작해 2분 전에 끝나기 때문이다.

화면에 `수집 소스 0`이 뜨는 것은 **출처가 없다는 거짓 진술**이다. 값을 모른다는 `—`보다 나쁘다.

## Implementation Scope

- `app/domains/news_insights/repository.py` — `collected_sources` 산출에서 시간 조건을 제거한다.
  `latest_agent_run_records`가 더 이상 `as_of`를 쓰지 않게 되면 **파라미터도 함께 제거한다.**
  쓰이지 않는 인자를 남기지 않는다.
- `app/domains/news_insights/service.py` — 위 시그니처 변경에 맞춘다.
- `tests/test_news_insights.py` — 아래 테스트 요구 참조.

## Out of Scope

- `average_run_duration_seconds`의 산출 정의·표본 상한.
- 스키마·모델·마이그레이션.
- 시드 데이터 값.
- 다른 엔드포인트.

## Protected Files

없음.

## Requirements

- `source_documents`가 하나도 없으면 `0`이다. 이때의 `0`은 실제로 출처가 없다는 뜻이므로 맞다.
- distinct 집계는 DB 측에서 수행한다.

## Test Requirements

- `test_agent_runs_returns_seeded_metrics_and_zero_sources_without_documents` — **이름과 단언이
  모두 틀렸다.** 시드에는 문서가 있는데 이름은 "without documents"라고 말하고 `0`을 단언한다.
  시드의 실제 고유 출처 수를 단언하도록 고치고 이름도 그에 맞게 바꾼다.
- 직전 커밋에서 추가한 나머지 테스트는 새 정의에 맞게 기대값을 조정한다. **단언을 삭제하지
  않는다.**
- 같은 `source_name`을 가진 문서가 여러 건일 때 1로 세는지 확인하는 단언을 유지한다.
- run 구간 밖에서 수집된 문서도 세어지는지 확인하는 단언을 **새로 추가한다.** 이번 정정의
  핵심이므로 회귀를 막을 자리가 필요하다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

`docs/designs/394-agent-pipeline-metrics.md`는 이미 갱신돼 있다. **고치지 않는다.**
`docs/designs/307-news-intelligence-phase2.md` §3.6은 필드 이름만 적고 있으므로 변경 없다.

## ADR Need

불요.

## Failure Record Need

불요. 이번 라운드 안에서 리뷰가 잡아낸 정의 오류이며, 반복될 성질의 실패 유형이 아니다.

## Risk Level

Low — 조회 조건 제거와 그에 따른 테스트 기대값 조정이다.

## Expected Output

- 직전 커밋 위에 쌓는 커밋(한국어 메시지). push·PR은 하지 않는다.
- 검증 3종 결과 보고.
- 시드 데이터에서 `collected_sources`가 몇으로 나오는지 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치(feat/394-agent-pipeline-metrics)를 유지한다(자체 브랜치 생성·push·PR 금지).
