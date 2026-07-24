# BE 설계: 뉴스 인텔리전스 파이프라인 4 — 해석(topic_insights·explanations) — 이슈 #400

상태: **설계 확정** — 2026-07-24. 트래킹 #391의 4단계, 에픽 #307 후속. 선행은 3단계 군집
(#399, `docs/designs/399-clustering-topics-keywords.md`).

이 문서는 `topic_clusters`에서 `topic_insights`·`topic_explanations`·`explanation_factors`를
생성하는 해석 경로의 범위와 계약을 스켈레톤 수준으로 확정한다. 실제 해석 로직은 담지 않는다.

## 배경

3단계(#399)로 `topic_clusters`가 생성된다. 해석 단계는 각 토픽에 대해 인사이트
(`topic_insights`)와 설명가능성 메타(`topic_explanations`·`explanation_factors`)를 만든다.

관련 모델의 성격을 먼저 정리한다.

- **`topic_insights`는 LLM 산출 전용이다.** `model_name`·`prompt_version`으로 생성 출처를
  기록하고, `executive_summary`·`why_it_matters`·`risk_points`·`counter_arguments`는 서술,
  `key_evidence`(JSON `[{"event_id": int}]`)가 근거 연결이다. `version`은 `topic_id`와
  UniqueConstraint로 누적된다(#373 토대).
- **`explanation_factors.contribution_ratio`는 정량 기여 비율**이다(307 phase3: 정량 집계·규칙
  산출, LLM 생성 금지).

## 1. 이번 단계 방침 — 배관·계약 우선, 골격 해석기

**실 LLM 해석은 후속 #409로 분리한다.** #398·#399와 같은 순서다. 이번 단계는 해석기
인터페이스(Port)와 배관을 세우고, 근거 연결·버전 멱등을 골격 해석기로 안정화한다.

**스키마를 변경하지 않는다.** #399와 마찬가지로 event↔topic membership이 없으므로, 토픽의 근거
이벤트는 `event_type`(slug에서 역산)으로 재조회한다.

## 2. 해석기 Port

`ABC` + `@abstractmethod` + frozen dataclass 결과(기존 경계 패턴).

| 요소 | 시그니처(개략) | 책임 |
|---|---|---|
| `TopicInterpreter`(ABC) | `interpret(topic: TopicCluster, events: list[ExtractedEvent]) -> TopicInterpretationDraft \| None` | 근거 이벤트로 토픽 해석 초안 생성. 근거 없으면 `None` |
| `TopicInterpretationDraft`(frozen) | — | insight 필드 + explanation 필드 + factor 초안 |

- 경계 타입 이름에 `DTO`를 쓰지 않는다.
- **근거 없는 인사이트를 만들지 않는다.** 근거 이벤트가 없는 토픽은 `None`을 반환해 해석에서
  제외한다.

## 3. 골격 해석기 — 규칙 기반

이번 단계의 구현체는 `RuleBasedTopicInterpreter`(이름 재량)로 둔다.

### 3.1 `topic_insights`

- `key_evidence` — 토픽의 근거 이벤트 id 목록 `[{"event_id": int}]`(실측 연결). 모든 id는 실제
  이벤트여야 한다(`validate_evidence_event_ids` 규약). 근거가 비면 인사이트를 만들지 않는다.
- `executive_summary`·`why_it_matters`·`risk_points`·`counter_arguments` — 골격 placeholder
  텍스트. 실 서술은 #409. **없는 사실을 지어내지 않는다** — 골격 텍스트는 토픽 제목·집계에서
  파생한 사실 진술에 그친다.
- `impact_score`·`confidence_score` — 토픽 집계(`impact_score`·`confidence_score`)를 잇거나
  중립 placeholder. 실측·검증은 #409.
- `model_name` = 골격 표식(예: `"rule-based-skeleton"`). `prompt_version` = `"v0-skeleton"`.
- `version` — 골격은 결정론적이므로 토픽당 `version=1`로 고정한다(§5 멱등).

### 3.2 `topic_explanations`·`explanation_factors`

- `data_coverage`·`confidence` — 중립 placeholder. 실측은 #409.
- `missing_data`·`limitations` — 골격의 한계를 정직하게 담는다(예: `"실 해석기 미도입"`,
  `"근거 연결이 event_type 기준 재조회"`).
- `already_priced_in` — 판정 근거가 없으므로 `False`, `already_priced_in_note`는 `None`.
- `analysis_version` — 골격 표식.
- **`explanation_factors`** — `contribution_ratio`는 정량이며 LLM이 생성하지 않는다. 골격은
  근거 있는 기여도 산출식이 없으므로 **factors를 비운다**(행 0건). 값을 지어내지 않는다. 정량
  기여도는 #409/정량 집계에서 다룬다.

## 4. 근거 연결 — event_type 재조회

- membership이 없으므로, 토픽 slug에서 `event_type`을 역산해 같은 `event_type`의
  `extracted_events`를 근거로 조회한다(#399의 재파생과 일관).
- `key_evidence`의 모든 `event_id`는 조회된 이벤트의 부분집합이어야 한다. 이 규약은 실 해석기
  (#409)에서도 그대로 강제된다.

## 5. 멱등 — 버전·설명 upsert

- `topic_insights` — `(topic_id, version=1)` upsert. 골격은 결정론적이라 재실행해도 새 버전을
  만들지 않고 v1을 갱신한다. 분석 변경 시 버전을 올리는 것은 실 해석기(#409)의 몫이다.
- `topic_explanations` — `topic_id`당 1개 upsert. 갱신 시 그 설명의 `explanation_factors`는
  재파생으로 대체한다(오래된 요인을 남기지 않는다).
- 재실행이 안전해야 한다 — 인사이트·설명 행 수가 늘지 않는다.

## 6. 파이프라인 배관 — 함수 골격

신규 모듈 `app/domains/news_insights/interpretation.py`(파일명 재량).

| 함수 | 시그니처(개략) | 책임 |
|---|---|---|
| `interpret_topics` | `(db, interpreter: TopicInterpreter) -> InterpretationResult` | 토픽 조회 → 근거 이벤트 조회 → 해석 → insight·explanation upsert 조율 |
| `InterpretationResult`(projection) | — | 생성·갱신 인사이트·설명·요인·근거 없어 스킵한 토픽 건수 집계 |

- 해석기는 인자로 주입한다(테스트는 골격/스텁, #409는 LLM 해석기).

## 7. 결정 현황 — 확정(2026-07-24)

- **배관+계약 우선, 골격 해석기.** #398·#399에서 확립된 패턴을 잇는다. 실 LLM 해석·버전 관리·
  정량 기여도는 후속 **#409**. 이번 단계는 Port·배관·근거 연결·버전 멱등을 세운다.
- **골격의 한계를 계약에 정직하게 반영.** placeholder 서술·점수, 빈 `explanation_factors`,
  `event_type` 기준 근거 재조회는 골격의 한계이며 #409가 해소한다. 값을 지어내지 않는다.

## 8. ADR·실패 기록 판단

- ADR: **불요**. 스키마를 변경하지 않고 기존 고정 모델에 데이터를 채운다. 해석기 Port는 기존
  경계 패턴의 연장이다. `topic_insights`의 LLM 산출 성격과 사실·추론 분리는 ADR-009의 연장이라
  새 결정이 아니다.
- 실패 기록: 해당 없음. 부재하던 해석 경로를 만드는 작업이다.
