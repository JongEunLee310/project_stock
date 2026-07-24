# Codex Handoff Task

## Source Issue

#399 — 뉴스 인텔리전스 파이프라인 3: 군집(topic_clusters·keywords). 트래킹 #391의 3단계.

## Task Summary

`extracted_events`(2단계에서 생성됨)를 토픽으로 묶어 `topic_clusters`(집계 스냅샷)로, 어휘를 `topic_keywords`로, 공출현을 `keyword_relations`로 파생하는 **군집 배관과 계약**을 신규 구현한다. 실 클러스터링·키워드 추출·membership 저장은 후속 #407이며 이 작업의 범위가 아니다. 이번 단계는 군집기 Port·배관·골격 군집기·`slug` upsert·실측 집계를 세운다.

## Goal

- `extracted_events`에서 `event_type` 기준으로 토픽이 `topic_clusters`로 생성/갱신된다.
- `mention_count`·`sentiment_score`가 소속 이벤트에서 실측 집계된다.
- 같은 군집을 다시 실행해도 토픽이 중복 생성되지 않고 집계가 누적되지 않는다(멱등).
- 스키마·모델·마이그레이션 변경이 없다.

## Background

**착수 전 `docs/designs/399-clustering-topics-keywords.md`를 읽어라.** 방침(배관·계약 우선, 스키마 유지)·Port·골격 군집기·키워드 한계·멱등·배관이 모두 확정돼 있다. 요지는 다음과 같다.

- 이번 단계는 **배관+계약 우선, 스키마 유지**다. 실 클러스터링·키워드 추출·event↔topic membership 저장은 후속 #407이며 만들지 않는다.
- `topic_clusters`에는 event membership 저장 자리가 없다. **스키마를 변경하지 않고**, 매 실행 `extracted_events` 전체에서 토픽을 결정론적으로 재파생한다.
- 골격 군집기는 `event_type` 기준 그룹핑이다. 신호가 빈약하므로 키워드·관계는 최소이거나 빈다. **값을 지어내지 않는다.**

## Implementation Scope

- **군집기 Port** — `ABC` + `@abstractmethod` + frozen dataclass 결과(기존 어댑터 경계 패턴).
  - `EventClusterer(ABC)` — `cluster(events: list[ExtractedEvent]) -> list[TopicClusterDraft]`.
  - `TopicClusterDraft`(frozen) — 토픽 필드 + 키워드 초안·관계 초안.
  - `TopicKeywordDraft`·`KeywordRelationDraft`(frozen).
  - 위치는 도메인 안(예: `app/domains/news_insights/clustering.py`).
- **골격 군집기** `EventTypeClusterer`(이름 재량) — `EventClusterer` 구현체.
  - 이벤트를 `event_type`으로 묶는다. `slug`는 `event_type`에서 결정론적 파생(예: `EARNINGS_GUIDANCE` → `earnings-guidance`).
  - `mention_count` = 소속 이벤트 수(실측). `sentiment_score` = 소속 이벤트 `sentiment_score` 평균(실측 집계).
  - `momentum_score`·`impact_score`·`confidence_score` = 중립 placeholder(예: `0.5`).
  - `category` = `EventType` → `TopicCategory` 결정론적 매핑(예: SUPPLY_CONTRACT→SUPPLY_CHAIN, EARNINGS_GUIDANCE→EARNINGS, REGULATION→REGULATION, BUYBACK→CAPITAL_POLICY, MANAGEMENT_CHANGE→적정 값). 매핑은 구현에서 확정한다.
  - `title` = `event_type` 대표 명칭. `summary`는 nullable이므로 비워도 된다.
  - `lifecycle_status` = 신규 토픽 `EMERGING`, 기존 토픽 `ACTIVE`. `first_seen_at`(신규 시 처리 시각)·`last_activity_at`(갱신)은 `app/domains/news_insights/clock.py`의 `utcnow`.
- **키워드·관계 파생** — 신호가 빈약하다. `event_type`을 대표 키워드로 최소 파생하거나(weight·mention_count는 집계) 신호가 없으면 비운다. 대표 키워드가 단수라 공출현이 없으면 `keyword_relations`는 비운다. **없는 키워드·관계를 지어내지 않는다.**
- **파이프라인 배관** `cluster_topics(db, clusterer: EventClusterer) -> ClusteringResult`.
  - `extracted_events` 조회 → 군집 → `slug` upsert(기존 갱신·신규 생성) → 그 토픽의 `topic_keywords`·`keyword_relations` 재파생(오래된 파생 대체).
  - `ClusteringResult`(projection) — 생성·갱신 토픽·키워드·관계 건수 집계.

## Out of Scope

- 실 클러스터링(임베딩·유사도), 본문 기반 키워드 추출, 공출현 관계망(#407).
- event↔topic membership 스키마 확장(#407).
- momentum·lifecycle 추이 정교화(#407).
- 해석(`topic_insights`·`topic_explanations`) — #400.
- 스키마·모델·마이그레이션 변경.
- `extracted_events`·`source_documents`·추출/수집 로직 수정.

## Protected Files

없음.

## Requirements

- **스키마를 변경하지 않는다.** membership을 저장하지 않고 매 실행 재파생한다.
- `slug`(unique)가 멱등 키다. 재실행 시 토픽이 중복 생성되지 않고, `mention_count` 등 집계가 **누적이 아니라 재계산**되어 실행마다 늘지 않아야 한다.
- 토픽 갱신 시 그 토픽의 `topic_keywords`·`keyword_relations`는 재파생으로 대체한다(오래된 파생을 남기지 않는다).
- `mention_count`·`sentiment_score`는 소속 이벤트에서 실측 집계한다. placeholder 점수와 실측 집계를 뒤섞지 않는다.
- 존재하지 않는 토픽·키워드·관계를 만들지 않는다.
- projection·경계 타입 이름에 `DTO`를 쓰지 않는다.

## Test Requirements

- 여러 `event_type`의 이벤트 → `event_type`별 토픽이 생성되고, `mention_count`·`sentiment_score`가 실측대로인지 값으로 단언한다(존재만 확인하지 않는다).
- `sentiment_score` 평균 집계가 정확한지(서로 다른 sentiment 이벤트 여러 건) 단언한다.
- **멱등** — 같은 이벤트로 군집을 두 번 실행해도 토픽 행 수와 `mention_count`가 늘지 않는다. 회귀 자리를 반드시 둔다.
- 새 이벤트가 추가된 뒤 재실행하면 기존 토픽의 `mention_count`가 재계산되고 `last_activity_at`이 갱신된다.
- 이벤트가 없으면 토픽 0건으로 끝난다.
- 군집기는 테스트에서 결정론적 골격/스텁으로 검증한다. 실제 DB·임베딩은 필요 없다.
- 기존 `tests/test_news_insights.py`의 인메모리 세션 픽스처 패턴을 따른다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

`docs/designs/399-clustering-topics-keywords.md`는 이미 작성돼 있다. **고치지 않는다.** 다른 문서 변경은 없다.

## ADR Need

불요. 스키마를 변경하지 않고 기존 고정 모델에 데이터를 채운다. 군집기 Port는 기존 경계 패턴의 연장이다. (스키마 확장이 필요한 membership은 #407에서 별도 ADR로 다룬다.)

## Failure Record Need

불요. 부재하던 군집 경로를 만드는 작업이다.

## Risk Level

Medium — 신규 Port·배관이나 스키마 변경이 없고, slug upsert 멱등·실측 집계가 설계에 확정돼 있다.

## Expected Output

- 현재 브랜치(`feat/399-clustering-topics-keywords`) 위에 쌓는 커밋(한국어 메시지). push·PR은 하지 않는다.
- 검증 3종 결과 보고.
- 테스트 픽스처 기준으로 생성·갱신 토픽·키워드·관계 건수와 집계값이 규칙대로 나오는지 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치(`feat/399-clustering-topics-keywords`)를 유지한다. 자체 브랜치 생성·push·PR을 하지 않는다.
