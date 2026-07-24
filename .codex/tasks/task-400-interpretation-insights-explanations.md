# Codex Handoff Task

## Source Issue

#400 — 뉴스 인텔리전스 파이프라인 4: 해석(topic_insights·explanations). 트래킹 #391의 4단계.

## Task Summary

`topic_clusters`(3단계에서 생성됨)에서 인사이트(`topic_insights`)와 설명가능성 메타(`topic_explanations`·`explanation_factors`)를 생성하는 **해석 배관과 계약**을 신규 구현한다. 실 LLM 해석은 후속 #409이며 이 작업의 범위가 아니다. 이번 단계는 해석기 Port·배관·근거 연결·버전 멱등을 세운다.

## Goal

- 근거 이벤트가 있는 각 토픽에 대해 `topic_insights`(v1)와 `topic_explanations`가 생성/갱신된다.
- `topic_insights.key_evidence`의 모든 `event_id`가 실제 근거 이벤트다.
- 같은 해석을 다시 실행해도 인사이트·설명 행 수가 늘지 않는다(버전 멱등).
- 스키마·모델·마이그레이션 변경이 없다.

## Background

**착수 전 `docs/designs/400-interpretation-insights-explanations.md`를 읽어라.** 방침(배관·계약 우선, 골격 해석기)·Port·근거 연결·버전 멱등이 모두 확정돼 있다. 요지는 다음과 같다.

- 이번 단계는 **배관+계약 우선, 골격 해석기**다. 실 LLM 해석·버전 관리·정량 기여도는 후속 #409이며 만들지 않는다.
- `topic_insights`는 `model_name`·`prompt_version`을 기록하는 LLM 산출 전용 테이블이다. 골격은 이를 골격 표식으로 채운다.
- membership이 없으므로 토픽의 근거 이벤트는 `event_type`(slug에서 역산)으로 재조회한다(#399와 일관).
- **근거 없는 인사이트를 만들지 않는다.**

## Implementation Scope

- **해석기 Port** — `ABC` + `@abstractmethod` + frozen dataclass 결과.
  - `TopicInterpreter(ABC)` — `interpret(topic: TopicCluster, events: list[ExtractedEvent]) -> TopicInterpretationDraft | None`. 근거 이벤트가 없으면 `None`.
  - `TopicInterpretationDraft`(frozen) — insight 필드 + explanation 필드 + factor 초안(이번 골격은 factor 없음).
  - 위치는 도메인 안(예: `app/domains/news_insights/interpretation.py`).
- **골격 해석기** `RuleBasedTopicInterpreter`(이름 재량) — `TopicInterpreter` 구현체.
  - `topic_insights`:
    - `key_evidence` = 근거 이벤트 id 목록 `[{"event_id": int}]`(실측). 근거가 비면 `None` 반환.
    - `executive_summary`·`why_it_matters`·`risk_points`·`counter_arguments` = 골격 placeholder 텍스트(토픽 제목·집계에서 파생한 사실 진술에 그친다, 없는 사실을 지어내지 않는다).
    - `impact_score`·`confidence_score` = 토픽 집계값을 잇거나 중립 placeholder(`0.5`).
    - `model_name` = `"rule-based-skeleton"`, `prompt_version` = `"v0-skeleton"`.
    - `version` = `1`(고정).
  - `topic_explanations`:
    - `data_coverage`·`confidence` = 중립 placeholder(`0.5`).
    - `missing_data`·`limitations` = 골격 한계를 담는다(예: `"실 해석기 미도입"`).
    - `already_priced_in` = `False`, `already_priced_in_note` = `None`.
    - `analysis_version` = 골격 표식.
  - `explanation_factors` = **비운다**(행 0건). `contribution_ratio`는 정량이며 골격은 근거 있는 산출식이 없으므로 만들지 않는다.
  - 시각은 `app/domains/news_insights/clock.py`의 `utcnow`.
- **근거 연결** — 토픽 slug에서 `event_type`을 역산해 같은 `event_type`의 `extracted_events`를 근거로 조회한다. `key_evidence`의 `event_id`는 조회된 이벤트의 부분집합이어야 한다. 검증 규약은 `app/domains/news_insights/briefing.py`의 `validate_evidence_event_ids`와 일관되게 둔다(재사용 가능하면 재사용).
- **파이프라인 배관** `interpret_topics(db, interpreter: TopicInterpreter) -> InterpretationResult`.
  - `topic_clusters` 조회 → 각 토픽의 근거 이벤트 조회 → 해석 → `topic_insights`·`topic_explanations` upsert → 그 설명의 `explanation_factors` 재파생(이번 골격은 항상 0건).
  - `InterpretationResult`(projection) — 생성·갱신 인사이트·설명·요인·근거 없어 스킵한 토픽 건수 집계.

## Out of Scope

- 실 LLM 해석(`LLMGateway` 호출), 분석 변경 기반 버전 증가(#409).
- 정량 기여도 산출(`explanation_factors.contribution_ratio`) — #409/정량 집계.
- 성과 검증·과거 유사 토픽·버전 비교(#373).
- 스키마·모델·마이그레이션 변경, event↔topic membership 저장.
- `topic_clusters`·`extracted_events`·군집/추출/수집 로직 수정.

## Protected Files

없음.

## Requirements

- **스키마를 변경하지 않는다.**
- 근거 이벤트가 없는 토픽은 인사이트·설명을 만들지 않고 스킵 건수에 잡는다.
- `key_evidence`의 모든 `event_id`가 실제 근거 이벤트여야 한다(부분집합).
- `topic_insights`는 `(topic_id, version=1)` upsert, `topic_explanations`는 `topic_id`당 1개 upsert. 재실행 시 행 수가 늘지 않는다.
- 설명 갱신 시 `explanation_factors`는 재파생으로 대체한다(골격은 항상 0건).
- placeholder 점수와 실측 연결(key_evidence)을 뒤섞지 않는다. 없는 사실·요인을 지어내지 않는다.
- projection·경계 타입 이름에 `DTO`를 쓰지 않는다.

## Test Requirements

- 근거 이벤트가 있는 토픽 → `topic_insights`(v1)·`topic_explanations` 생성, `key_evidence`가 실제 이벤트 id를 담는지, `model_name`·`version`·placeholder 값이 규칙대로인지 값으로 단언한다(존재만 확인하지 않는다).
- 근거 이벤트가 없는 토픽 → 인사이트·설명 미생성, 스킵 건수에 잡힌다.
- **버전 멱등** — 같은 해석을 두 번 실행해도 `topic_insights`·`topic_explanations` 행 수가 늘지 않고 v1이 갱신된다. 회귀 자리를 반드시 둔다.
- `explanation_factors`가 0건인지 단언한다.
- 토픽이 없으면 0건으로 끝난다.
- 해석기는 테스트에서 결정론적 골격/스텁으로 검증한다. 실제 DB·LLM은 필요 없다.
- 기존 `tests/test_news_insights.py`의 인메모리 세션 픽스처 패턴을 따른다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

`docs/designs/400-interpretation-insights-explanations.md`는 이미 작성돼 있다. **고치지 않는다.** 다른 문서 변경은 없다.

## ADR Need

불요. 스키마를 변경하지 않고 기존 고정 모델에 데이터를 채운다. 해석기 Port는 기존 경계 패턴의 연장이고, LLM 산출 성격과 사실·추론 분리는 ADR-009의 연장이다.

## Failure Record Need

불요. 부재하던 해석 경로를 만드는 작업이다.

## Risk Level

Medium — 신규 Port·배관이나 스키마 변경이 없고, 근거 연결·버전 upsert 멱등이 설계에 확정돼 있다.

## Expected Output

- 현재 브랜치(`feat/400-interpretation-insights-explanations`) 위에 쌓는 커밋(한국어 메시지). push·PR은 하지 않는다.
- 검증 3종 결과 보고.
- 테스트 픽스처 기준으로 생성·갱신 인사이트·설명·스킵 건수와 `key_evidence`가 규칙대로 나오는지 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치(`feat/400-interpretation-insights-explanations`)를 유지한다. 자체 브랜치 생성·push·PR을 하지 않는다.
