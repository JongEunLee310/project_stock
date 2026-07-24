# BE 설계: 뉴스 인텔리전스 파이프라인 6 — 처리 현황 기록(agent_runs·stages) — 이슈 #402

상태: **설계 확정** — 2026-07-24. 트래킹 #391의 6단계(마지막), 에픽 #307 후속. 선행은 1~4단계
(#397~#400).

이 문서는 1~4단계를 순차 실행하고 그 실행을 `agent_runs`·`agent_run_stages`로 기록하는
파이프라인 러너의 범위와 계약을 스켈레톤 수준으로 확정한다. 실제 실행 로직은 담지 않는다.

## 배경

1~4단계(#397~#400)로 수집·추출·군집·해석 경로가 각각 완성됐고, 각 단계는 result projection을
반환한다(`ingest_source_documents`·`extract_events`·`cluster_topics`·`interpret_topics`).
그러나 이 실행을 기록하는 코드가 없어 `agent_runs`·`agent_run_stages`는 `seed.py`로만 채워지고,
`#394`(처리 지표)·`#389`(단계 내역)가 시드 1건을 반영한다.

이 단계는 4단계를 순차 실행하고 실행 현황을 기록하는 러너를 만든다. 앞 단계들과 달리 "LLM
vs 골격" 같은 선택이 없다 — 이미 만들어진 4단계를 엮어 실행하고 기록하는 오케스트레이션이다.

## 1. 두 가지 스키마 제약

- **단계별 처리 건수·소요 시간을 저장할 자리가 없다.** `agent_run_stages`는 `stage`·`status`·
  `delayed`만 담는다. 단계별 메트릭은 스키마 확장이 필요하므로 후속 **#413**으로 분리한다.
  이번 단계는 처리 건수·소요 시간을 **agent_run 레벨 요약**으로만 기록한다.
- **`AgentStage` enum(COLLECT·NORMALIZE·EXTRACT·CLUSTER·SENTIMENT·IMPACT·LINK)과 실제 4단계가
  1:1이 아니다.** 실제 수행하는 단계만 매핑해 기록하고, 수행하지 않는 단계는 만들지 않는다
  (§3).

## 2. 파이프라인 러너

신규 모듈 `app/domains/news_insights/pipeline.py`(파일명 재량).

| 함수 | 시그니처(개략) | 책임 |
|---|---|---|
| `run_pipeline` | `(db, extractor, clusterer, interpreter) -> PipelineRunResult` | agent_run 생성 → 4단계 순차 실행·stage 기록 → agent_run 갱신 |
| `PipelineRunResult`(projection) | — | agent_run id + 각 단계 result 요약 |

실행 순서와 처리:

1. `agent_run` 생성 — `started_at`, `status=RUNNING`.
2. 4단계 순차 실행. 각 단계마다 `agent_run_stage` 기록(§3).
3. `agent_run` 갱신 — `finished_at`, `status`, 집계(§4).

- 각 단계 함수는 이미 존재한다. 러너는 이를 주입받은 구현체(골격 extractor·clusterer·
  interpreter)와 함께 호출한다.
- 실행 트리거(수동 진입점·테스트)는 구현 재량. 스케줄러·주기 실행은 이번 범위가 아니다.

## 3. stage 매핑 — 실제 수행 단계만

| 실제 단계 | `AgentStage` | 근거 |
|---|---|---|
| 수집(`ingest`) | `COLLECT` | 명확 대응 |
| 추출(`extract`) | `EXTRACT` | 명확 대응 |
| 군집(`cluster`) | `CLUSTER` | 명확 대응 |
| 해석(`interpret`) | `LINK` | 근거 이벤트↔인사이트(`key_evidence`) 연결이 LINK에 가장 근접 |

- `NORMALIZE`·`SENTIMENT`·`IMPACT`는 골격 파이프라인이 별도 단계로 수행하지 않으므로 **stage를
  만들지 않는다.** 값이 없는 단계를 지어내지 않는다(원칙).
- 각 stage의 `status`는 해당 단계 실행 결과(성공 `COMPLETED`, 실패 `FAILED`)를 반영한다.
  `delayed`는 골격에서 판정 근거가 없으므로 `False`로 둔다(지연 판정은 #413/실 운영에서).

## 4. agent_run 요약 집계

- `processed_documents` — 이번 run이 처리한 문서 수. 추출 단계가 처리한(EXTRACTED로 전이한)
  문서 수를 잇는다.
- `extracted_events` — 이번 run이 생성한 이벤트 수(추출 result).
- `active_topics` — `lifecycle_status`가 활성인 토픽 수(군집 이후 집계).
- `analysis_version` — 골격 표식(예: `"rule-based-skeleton"`).
- `status` — 모든 단계 성공 시 `COMPLETED`, 단계 실패 시 `FAILED`.
- `finished_at` — 실행 종료 시각(`clock.utcnow`).

각 값은 단계 result에서 실측한다. 값이 없으면 비우되, 이 필드들은 NOT NULL이므로 처리량이
0이면 `0`이 실제 처리량 0을 뜻한다(문서·이벤트가 실제로 없었던 경우).

## 5. 실행 이력 — run은 append

- `agent_run`은 **실행 이력**이다. 러너를 실행할 때마다 새 `agent_run`을 생성한다(멱등 아님).
  `#394`가 "최신 run"을 조회하는 것과 일관된다.
- 앞 4단계 함수는 각각 멱등이므로, 두 번째 실행에서는 처리량이 대부분 0으로 기록된다. 이는
  정직한 기록이다(이미 처리된 데이터를 다시 세지 않는다).
- 러너 자체의 재실행 안전성은 "이력이 하나 더 쌓인다"는 의미이며, 데이터 중복 생산이 아니다
  (4단계 멱등이 보장).

## 6. 결정 현황 — 확정(2026-07-24)

- **파이프라인 러너 + agent_run/stage 기록.** 4단계 골격 구현체를 주입해 순차 실행한다.
- **단계별 메트릭은 스키마 부재로 이번 범위 밖(#413).** agent_run 레벨 요약만 기록한다.
- **stage는 실제 수행 단계(COLLECT·EXTRACT·CLUSTER·LINK)만.** 수행하지 않는 단계를 만들지
  않는다.

## 7. ADR·실패 기록 판단

- ADR: **불요**. 스키마를 변경하지 않고 기존 고정 모델에 실행 기록을 채운다. 러너는 기존 4단계
  배관을 엮는 오케스트레이션이다. (단계별 메트릭 스키마 확장은 #413에서 별도 ADR로 다룬다.)
- 실패 기록: 해당 없음. 부재하던 실행 기록 경로를 만드는 작업이다.
