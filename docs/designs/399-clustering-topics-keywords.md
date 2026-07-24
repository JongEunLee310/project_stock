# BE 설계: 뉴스 인텔리전스 파이프라인 3 — 군집(topic_clusters·keywords) — 이슈 #399

상태: **설계 확정** — 2026-07-24. 트래킹 #391의 3단계, 에픽 #307 후속. 선행은 2단계 추출
(#398, `docs/designs/398-extraction-events-evidence.md`).

이 문서는 `extracted_events`를 `topic_clusters`로 묶고 `topic_keywords`·`keyword_relations`를
파생하는 군집 경로의 범위와 계약을 스켈레톤 수준으로 확정한다. 실제 군집 로직은 담지 않는다.

## 배경

2단계(#398)로 `extracted_events`가 생성된다. 군집 단계는 이 이벤트를 토픽으로 묶어
`topic_clusters`(집계 스냅샷)로, 토픽의 어휘를 `topic_keywords`로, 어휘 공출현을
`keyword_relations`로 남긴다.

두 가지 구조적 제약이 이 단계를 규정한다.

- **event↔topic membership을 저장할 자리가 스키마에 없다.** `topic_clusters`는 `slug` 기준
  집계 스냅샷이고 이벤트로의 FK가 없다. `extracted_events`에도 topic 참조가 없다. 1차 계약은
  이벤트↔토픽 연결을 해석 단계의 `TopicInsight.key_evidence`로만 표현한다.
- **골격 단계의 그룹핑 신호가 빈약하다.** 골격 추출기(#398)는 `primary_symbol`을 `null`로 두고
  `extracted_events`에 키워드 필드가 없다. 결정론적으로 쓸 수 있는 신호는 `event_type`
  정도다.

## 1. 이번 단계 방침 — 배관·계약 우선, 스키마 유지

**실 클러스터링·키워드 추출·membership 저장은 후속 #407로 분리한다(사용자 선택).** 이번
단계는 군집기 인터페이스(Port)와 배관을 세우고, `slug` 기준 upsert로 계약을 안정화한다.
#398이 추출을 배관·계약 우선으로 세운 것과 같은 순서다.

**스키마를 변경하지 않는다.** membership을 저장하지 않으므로, 매 실행 `extracted_events`
전체에서 토픽을 결정론적으로 재파생한다. 스키마 확장(event↔topic 연결)과 그에 기반한 추이
정교화는 #407에서 ADR·마이그레이션과 함께 다룬다.

## 2. 군집기 Port

기존 어댑터 경계 패턴을 따른다 — `ABC` + `@abstractmethod` + frozen dataclass 결과.

| 요소 | 시그니처(개략) | 책임 |
|---|---|---|
| `EventClusterer`(ABC) | `cluster(events: list[ExtractedEvent]) -> list[TopicClusterDraft]` | 이벤트 목록을 토픽 초안으로 묶음 |
| `TopicClusterDraft`(frozen) | — | 토픽 필드 + 키워드 초안·관계 초안 |
| `TopicKeywordDraft`·`KeywordRelationDraft`(frozen) | — | 어휘·관계 초안 |

- 경계 타입 이름에 `DTO`를 쓰지 않는다.
- Port는 이벤트 목록 전체를 받아 토픽 집합을 만든다(문서 단위인 추출과 다르다).

## 3. 골격 군집기 — event_type 결정론적 그룹핑

이번 단계의 구현체는 `EventTypeClusterer`(이름 재량)로 둔다. **존재하지 않는 토픽을 만들지
않는다.**

- **그룹핑** — 이벤트를 `event_type`으로 묶는다. `slug`는 `event_type`에서 결정론적으로
  파생한다(예: `EARNINGS_GUIDANCE` → `earnings-guidance`). 토픽당 `slug`가 unique다.
- **집계(실측)** — `mention_count`는 그 `event_type`에 속한 이벤트 수. `sentiment_score`는 속한
  이벤트 `sentiment_score`의 평균. 이들은 정량 집계이므로 실제 값으로 채운다.
- **placeholder** — `momentum_score`·`impact_score`·`confidence_score`는 추이·영향 판정 신호가
  없어 중립 placeholder(예: `0.5`)로 둔다. 실측·추이 산출은 #407.
- **category** — `EventType` → `TopicCategory` 매핑(예: `SUPPLY_CONTRACT` → `SUPPLY_CHAIN`,
  `EARNINGS_GUIDANCE` → `EARNINGS`, `REGULATION` → `REGULATION`, `BUYBACK` → `CAPITAL_POLICY`,
  `MANAGEMENT_CHANGE` → 적정 값). 매핑은 결정론적 규칙으로 두고 구현에서 확정한다.
- **title** — `event_type`의 대표 명칭.
- **lifecycle_status** — 골격은 단순 규칙: 신규 토픽은 `EMERGING`, 기존 토픽은 `ACTIVE`. 추이
  기반 정교한 판정(RISING·COOLING·ARCHIVED)은 #407.
- **first_seen_at·last_activity_at** — 신규는 `first_seen_at` = 처리 시각. 기존은
  `last_activity_at` 갱신. 처리 시각은 `clock.utcnow`.

## 4. 키워드·관계망 — 신호 한계 명시

골격 단계는 키워드 추출 신호가 없다(`extracted_events`에 키워드 필드 없음). 따라서:

- `topic_keywords` — `event_type`을 대표 키워드로 최소 파생하거나(weight·mention_count는 집계),
  신호가 없으면 비운다. 본문 기반 키워드 추출은 #407.
- `keyword_relations` — 대표 키워드가 단수라 공출현 관계가 성립하지 않으면 비운다. 관계망은
  #407.

이 한계를 응답에 정직하게 반영한다. 화면 문구에 맞추려고 없는 키워드·관계를 지어내지 않는다.

## 5. 멱등 — `slug` upsert

- `slug`(unique)가 멱등 키다. 같은 군집을 다시 실행해도 토픽이 중복 생성되지 않는다.
- 기존 `slug`는 갱신(집계 재계산·`last_activity_at` 갱신), 없으면 생성(`first_seen_at` 설정).
- 집계는 누적이 아니라 **재계산**이어야 한다 — 같은 입력에 대해 `mention_count`가 실행마다
  늘지 않아야 멱등이 성립한다.
- 토픽 갱신 시 그 토픽의 `topic_keywords`·`keyword_relations`는 재파생으로 대체한다(오래된
  파생을 남기지 않는다).

## 6. 파이프라인 배관 — 함수 골격

신규 모듈 `app/domains/news_insights/clustering.py`(파일명 재량).

| 함수 | 시그니처(개략) | 책임 |
|---|---|---|
| `cluster_topics` | `(db, clusterer: EventClusterer) -> ClusteringResult` | 이벤트 조회 → 군집 → slug upsert → 키워드·관계 재파생 조율 |
| `ClusteringResult`(projection) | — | 생성·갱신 토픽·키워드·관계 건수 집계 |

- 군집기는 인자로 주입한다(테스트는 골격/스텁, #407은 실 군집기).
- 대상 이벤트 범위(전체 vs 최근)는 구현 재량이되 재실행 멱등을 지킨다.

## 7. 결정 현황 — 확정(2026-07-24)

- **배관+계약 우선, 스키마 유지(사용자 선택).** 실 클러스터링·키워드 추출·membership 저장·추이
  정교화는 후속 **#407**. 이번 단계는 Port·배관·골격 군집기·slug upsert·실측 집계를 세운다.
- **골격의 한계를 계약에 정직하게 반영.** `event_type` 조악 그룹핑, placeholder 점수, 빈약한
  키워드·관계는 골격의 한계이며 #407이 해소한다. 값을 지어내지 않는다.

## 8. ADR·실패 기록 판단

- ADR: **불요**. 스키마를 변경하지 않고 기존 고정 모델에 데이터를 채운다. 군집기 Port는 기존
  경계 패턴의 연장이다. (스키마 확장이 필요한 membership은 #407에서 별도 ADR로 다룬다.)
- 실패 기록: 해당 없음. 부재하던 군집 경로를 만드는 작업이다.
