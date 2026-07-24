# Codex Handoff Task

## Source Issue

#402 — 뉴스 인텔리전스 파이프라인 6: 처리 현황 기록(agent_runs·stages). 트래킹 #391의 6단계(마지막).

## Task Summary

1~4단계(수집·추출·군집·해석)를 순차 실행하고 그 실행을 `agent_runs`·`agent_run_stages`로 기록하는 **파이프라인 러너**를 신규 구현한다. 앞 단계들과 달리 "LLM vs 골격" 선택이 없다 — 이미 만들어진 4단계를 엮어 실행하고 기록하는 오케스트레이션이다.

## Goal

- 파이프라인을 실행하면 `agent_run` 한 건과 그 실행이 수행한 단계의 `agent_run_stages`가 기록된다.
- `agent_run` 요약(`processed_documents`·`extracted_events`·`active_topics`)이 단계 result에서 실측된다.
- 스키마·모델·마이그레이션 변경이 없다.

## Background

**착수 전 `docs/designs/402-pipeline-runner-agent-runs.md`를 읽어라.** 스키마 제약·stage 매핑·집계·실행 이력이 모두 확정돼 있다. 요지는 다음과 같다.

- 단계별 처리 건수·소요 시간을 저장할 자리가 `agent_run_stages`에 없다(`stage`·`status`·`delayed`만). 단계별 메트릭은 후속 #413이며, 이번은 **agent_run 레벨 요약**만 기록한다.
- `AgentStage` enum과 4단계가 1:1이 아니다. **실제 수행하는 단계만** 매핑해 기록한다.
- `agent_run`은 실행 이력이라 매 실행 새 레코드를 append한다(멱등 아님).

## Implementation Scope

- **파이프라인 러너** — 신규 모듈(예: `app/domains/news_insights/pipeline.py`).
  - `run_pipeline(db, extractor: EventExtractor, clusterer: EventClusterer, interpreter: TopicInterpreter) -> PipelineRunResult`.
  - 실행 순서:
    1. `agent_run` 생성 — `started_at`(=`clock.utcnow`), `status=RUNNING`, 집계 필드는 초기값.
    2. 4단계 순차 실행. 각 단계 성공 후 그 단계의 `agent_run_stage`(§stage 매핑)를 `COMPLETED`로 기록.
       - 수집 `ingest_source_documents(db)`
       - 추출 `extract_events(db, extractor)`
       - 군집 `cluster_topics(db, clusterer)`
       - 해석 `interpret_topics(db, interpreter)`
    3. `agent_run` 갱신 — `finished_at`, `status`, 집계(아래).
  - `PipelineRunResult`(projection) — `agent_run` id + 각 단계 result 요약.
- **stage 매핑**(실제 수행 단계만):
  - 수집 → `AgentStage.COLLECT`
  - 추출 → `AgentStage.EXTRACT`
  - 군집 → `AgentStage.CLUSTER`
  - 해석 → `AgentStage.LINK`
  - `NORMALIZE`·`SENTIMENT`·`IMPACT` stage는 **만들지 않는다.**
  - 각 stage `status`는 단계 결과(성공 `COMPLETED`/실패 `FAILED`). `delayed`는 `False`(골격은 지연 판정 근거 없음).
- **agent_run 집계**:
  - `processed_documents` ← 추출 result의 `processed_document_count`.
  - `extracted_events` ← 추출 result의 `created_event_count`.
  - `active_topics` ← 활성 lifecycle 토픽 수. **기존 서비스의 `active_topic_clusters` 산출과 일관되게** 조회한다(`app/domains/news_insights/service.py` 참고, 같은 lifecycle 상태 집합 사용).
  - `analysis_version` ← 골격 표식(예: `"rule-based-skeleton"`).
  - `status` ← 모든 단계 성공 시 `COMPLETED`, 단계 실패 시 `FAILED`.
  - `finished_at` ← `clock.utcnow`.
- **실패 처리** — 어느 단계에서 예외가 나면 그 단계 stage를 `FAILED`로, `agent_run.status`를 `FAILED`로 기록하고 실행을 종료한다. 부분 실행이라도 run이 남아야 한다.
- 실행 트리거(수동 진입점·테스트)는 구현 재량. 스케줄러·주기 실행은 범위가 아니다.

## Out of Scope

- 단계별 처리 건수·소요 시간 기록·스키마 확장(#413).
- 스케줄러·워커 주기 실행 연결.
- 스키마·모델·마이그레이션 변경.
- 4단계 함수(`ingest_source_documents`·`extract_events`·`cluster_topics`·`interpret_topics`)와 각 도메인 로직 수정.
- 실 LLM·실 알고리즘 구현(각 단계 후속 #405·#407·#409).

## Protected Files

없음.

## Requirements

- **스키마를 변경하지 않는다.**
- `agent_run`은 매 실행 새로 생성한다(이력 append). 4단계 함수가 각각 멱등이므로 재실행 시 처리량이 0으로 기록되는 것은 정직한 기록이다.
- 실제 수행한 4단계(COLLECT·EXTRACT·CLUSTER·LINK)의 stage만 기록한다. 수행하지 않은 단계를 만들지 않는다.
- 집계는 단계 result에서 실측한다. 값을 지어내지 않는다. (NOT NULL 필드라 처리량 0이면 `0`이 실제 0을 뜻한다.)
- 단계 실패 시 run·stage를 `FAILED`로 기록하고 run을 남긴다.
- projection·경계 타입 이름에 `DTO`를 쓰지 않는다.

## Test Requirements

- 파이프라인 실행 → `agent_run` 1건(`COMPLETED`)과 stage 4건(COLLECT·EXTRACT·CLUSTER·LINK)이 생성되고, `processed_documents`·`extracted_events`·`active_topics`가 단계 result·DB 상태에서 실측한 값인지 값으로 단언한다(존재만 확인하지 않는다).
- stage가 정확히 4종만 생성되고 NORMALIZE·SENTIMENT·IMPACT는 없는지 단언한다.
- 어느 단계에서 예외가 나면(스텁 단계 구현으로 유발) `agent_run.status`·해당 stage가 `FAILED`이고 run이 남는지 단언한다.
- 재실행 시 `agent_run`이 2건으로 append되고, 두 번째 run의 처리량이 0인지 단언한다(4단계 멱등 반영).
- 골격 구현체(`RuleBasedEventExtractor`·`EventTypeClusterer`·`RuleBasedTopicInterpreter`)를 주입해 검증한다. 실 DB·LLM은 필요 없다.
- 기존 `tests/test_news_insights.py`의 인메모리 세션 픽스처 패턴을 따른다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

`docs/designs/402-pipeline-runner-agent-runs.md`는 이미 작성돼 있다. **고치지 않는다.** 다른 문서 변경은 없다.

## ADR Need

불요. 스키마를 변경하지 않고 기존 고정 모델에 실행 기록을 채운다. 러너는 기존 4단계 배관을 엮는 오케스트레이션이다. (단계별 메트릭 스키마 확장은 #413에서 별도 ADR로 다룬다.)

## Failure Record Need

불요. 부재하던 실행 기록 경로를 만드는 작업이다.

## Risk Level

Medium — 신규 오케스트레이션이나 스키마 변경이 없고, stage 매핑·집계·실패 처리가 설계에 확정돼 있다.

## Expected Output

- 현재 브랜치(`feat/402-pipeline-runner-agent-runs`) 위에 쌓는 커밋(한국어 메시지). push·PR은 하지 않는다.
- 검증 3종 결과 보고.
- 테스트 픽스처 기준으로 agent_run 집계·stage 구성·재실행 append가 규칙대로 나오는지 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치(`feat/402-pipeline-runner-agent-runs`)를 유지한다. 자체 브랜치 생성·push·PR을 하지 않는다.
