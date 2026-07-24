# Codex Handoff Task

## Source Issue

#398 — 뉴스 인텔리전스 파이프라인 2: 추출(extracted_events·event_evidence). 트래킹 #391의 2단계.

## Task Summary

`source_documents`(1단계에서 `PENDING`으로 적재됨)에서 사건을 뽑아 `extracted_events`로, 근거를 `event_evidence`로 생성하는 **추출 배관과 계약**을 신규 구현한다. 실제 LLM 추출은 후속 #405이며 이 작업의 범위가 아니다. 이번 단계는 추출기 Port·파이프라인 배관·골격 규칙 추출기·근거 연결·멱등·상태 전이를 세운다.

## Goal

- `PENDING` 문서에서 규칙에 걸리는 이벤트가 `extracted_events`로, 그 근거가 `event_evidence`로 생성된다.
- 모든 이벤트가 최소 1건의 근거를 가진다.
- 같은 문서를 다시 추출해도 이벤트가 중복 생성되지 않는다(멱등).
- 스키마·모델·마이그레이션 변경이 없다.

## Background

**착수 전 `docs/designs/398-extraction-events-evidence.md`를 읽어라.** 방침(배관·계약 우선)·Port·골격 추출기·근거 연결·멱등·상태 전이가 모두 확정돼 있다. 요지는 다음과 같다.

- 이번 단계는 **배관+계약 우선**이다. 실 LLM 추출기는 후속 #405이며 만들지 않는다.
- 골격 추출기는 규칙 기반이다. **값을 지어내지 않는다.** `event_type`을 키워드 규칙으로 판별하지 못하는 문서는 이벤트를 만들지 않는다.
- 점수(`sentiment_score`·`importance_score`·`confidence_score`)는 중립 placeholder다. 실측은 #405가 채운다.

## Implementation Scope

- **추출기 Port** — 기존 `app/adapters/news/base.py`의 `NewsAdapter(ABC)` 패턴을 따른다(`ABC` + `@abstractmethod` + frozen dataclass 결과).
  - `EventExtractor(ABC)` — `extract(document: SourceDocument) -> list[ExtractedEventDraft]`.
  - `ExtractedEventDraft`(frozen dataclass) — 이벤트 필드 + 근거 초안 리스트.
  - `EvidenceDraft`(frozen dataclass) — `evidence_role`·`relevance_score`·`extracted_quote`.
  - 경계 타입 위치는 도메인 안(예: `app/domains/news_insights/extraction.py`)이면 된다.
- **골격 추출기** `RuleBasedEventExtractor`(이름 재량) — `EventExtractor` 구현체.
  - `event_type` — `title`·`raw_content`의 **최소한의 대표 키워드**로 `EventType`을 판별한다. 걸리지 않으면 빈 리스트(이벤트 없음). 과한 키워드 사전을 지어내지 말고 유형별 대표 키워드 소수로 둔다.
  - `title`·`summary` — 문서 `title`·`raw_content`에서 파생(원문 기반).
  - `sentiment_direction` — 긍/부정 키워드 규칙, 없으면 `NEUTRAL`. `sentiment_score`·`importance_score`·`confidence_score` — 중립 placeholder(예: `0.5`).
  - `primary_symbol`·`sector_code`·`occurred_at` — `null`. `source_documents`에는 종목·섹터·발생시각 필드가 없다.
  - `detected_at` — 처리 시각. `app/domains/news_insights/clock.py`의 `utcnow`를 쓴다.
  - `status` — `EventStatus.ACTIVE`(모델 기본).
- **파이프라인 배관** `extract_events(db, extractor: EventExtractor) -> ExtractionResult`.
  - `processing_status == PENDING`인 `source_documents`를 조회한다.
  - 각 문서를 추출기에 넘겨 `ExtractedEvent` + `EventEvidence`(그 문서를 `PRIMARY` 근거로)를 생성한다.
  - 처리한 문서는 `processing_status`를 `EXTRACTED`로 전이한다(이벤트 0건이어도 전이). 추출 중 예외가 나면 `FAILED`.
  - `ExtractionResult`(projection) — 처리 문서·생성 이벤트·근거·멱등 스킵·실패 건수 집계.

## Out of Scope

- 실 LLM 추출기(#405). `LLMGateway` 호출을 이번에 붙이지 않는다.
- 여러 문서를 하나의 토픽으로 묶는 군집(#399).
- 스키마·모델·마이그레이션 변경.
- `source_documents` 적재 로직(#397) 수정.
- `raw_news_events`·`news_items` 수정.

## Protected Files

없음.

## Requirements

- 모든 `extracted_event`는 최소 1건의 `event_evidence`를 가진다. 이벤트와 근거는 같은 트랜잭션에서 함께 쓴다.
- `event_type` 규칙에 걸리지 않는 문서는 이벤트를 만들지 않는다(빈 리스트).
- `event_fingerprint`(NOT NULL)가 멱등 키다. 추출기가 결정론적으로 만든다(예: `event_type` + `primary_symbol` + 근거 문서 `content_hash` 조합의 해시, 조합은 재량이되 결정론적일 것). 이미 존재하는 fingerprint는 재생성하지 않는다.
- 이미 `EXTRACTED`인 문서는 재추출하지 않는다(문서 단위 멱등).
- 점수는 중립 placeholder다. 규칙으로 근거 있게 만들 수 없는 값을 지어내지 않는다.
- 문서 단위 처리는 원자적이어야 한다.
- projection·경계 타입 이름에 `DTO`를 쓰지 않는다.

## Test Requirements

- 키워드에 걸리는 문서 → 이벤트 1건 이상 + `PRIMARY` 근거가 생성되고, 각 필드가 규칙대로 채워지는지 값으로 단언한다(존재만 확인하지 않는다).
- 키워드에 걸리지 않는 문서 → 이벤트 0건이지만 문서는 `EXTRACTED`로 전이된다.
- **멱등** — 같은 문서로 추출을 두 번 실행해도 `extracted_events` 행 수가 늘지 않는다. 회귀 자리를 반드시 둔다.
- 이미 `EXTRACTED`인 문서는 재추출 대상에서 제외된다.
- `PENDING` 문서가 없으면 0건으로 끝난다.
- 추출기는 테스트에서 결정론적 스텁/골격으로 주입한다. 실제 DB·LLM 기동은 필요 없다.
- 기존 `tests/test_news_insights.py`의 인메모리 세션 픽스처 패턴을 따른다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

`docs/designs/398-extraction-events-evidence.md`는 이미 작성돼 있다. **고치지 않는다.** 다른 문서 변경은 없다.

## ADR Need

불요. 기존 고정 모델에 데이터를 채우는 작업이고 스키마·와이어 컨벤션 변경이 없다. 추출기 Port는 기존 어댑터 경계 패턴의 연장이다.

## Failure Record Need

불요. 부재하던 추출 경로를 만드는 작업이다.

## Risk Level

Medium — 신규 Port·배관이나 스키마 변경이 없고, 근거 연결·멱등·상태 전이가 설계에 확정돼 있다.

## Expected Output

- 현재 브랜치(`feat/398-extraction-events-evidence`) 위에 쌓는 커밋(한국어 메시지). push·PR은 하지 않는다.
- 검증 3종 결과 보고.
- 테스트 픽스처 기준으로 처리 문서·생성 이벤트·근거·멱등 스킵 건수가 규칙대로 나오는지 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치(`feat/398-extraction-events-evidence`)를 유지한다. 자체 브랜치 생성·push·PR을 하지 않는다.
