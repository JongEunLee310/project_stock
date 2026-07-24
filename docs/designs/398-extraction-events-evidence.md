# BE 설계: 뉴스 인텔리전스 파이프라인 2 — 추출(extracted_events·event_evidence) — 이슈 #398

상태: **설계 확정** — 2026-07-24. 트래킹 #391의 2단계, 에픽 #307 후속. 선행은 1단계 수집
(#397, `docs/designs/397-collection-source-documents.md`).

이 문서는 `source_documents`에서 `extracted_events`·`event_evidence`를 생성하는 추출 경로의
범위와 계약을 스켈레톤 수준으로 확정한다. 실제 추출 로직·프롬프트는 담지 않는다.

## 배경

1단계(#397)로 `source_documents`에 실데이터가 `PENDING` 상태로 적재된다. 추출 단계는 이
문서에서 사건(event)을 뽑아 `extracted_events`로, 그 근거를 `event_evidence`로 남긴다.

`extracted_events`는 `event_type`·`title`·`summary`·`sentiment_direction`·`sentiment_score`·
`importance_score`·`confidence_score`·`primary_symbol` 등 **본문에서 의미를 뽑아야 하는
추론값**을 요구한다. 이는 본질적으로 LLM 작업이며, 붙일 인프라(`LLMGateway`·router·
`PrivacyGate`·output validation)는 ADR-007~012로 이미 갖춰져 있다.

## 1. 이번 단계 방침 — 배관·계약 우선, 골격 추출기

**실제 LLM 추출은 후속 #405로 분리한다.** 이번 단계는 추출기 인터페이스(Port)와 파이프라인
배관을 세우고, 계약을 골격 규칙 추출기로 안정화하는 데 집중한다. #397이 수집을 방향 A(단순
적재)로 먼저 세운 것과 같은 순서다.

이렇게 나누는 이유는 두 가지다.

- 추출 파이프라인의 배관(조회 → 추출 → 생성 → 상태 전이 → 멱등)과 근거 연결 계약은 추출기의
  품질과 독립적으로 검증할 수 있다.
- 실 LLM 호출은 프롬프트·라우팅·비용·검증이 얽힌 별도 작업이고, codex 샌드박스는 네트워크가
  차단돼 실호출 테스트가 불가능하다(#405에서 다룬다).

## 2. 추출기 Port

기존 `NewsAdapter(ABC)` 패턴을 따른다 — `ABC` + `@abstractmethod` + frozen dataclass 결과.

| 요소 | 시그니처(개략) | 책임 |
|---|---|---|
| `EventExtractor`(ABC) | `extract(document: SourceDocument) -> list[ExtractedEventDraft]` | 문서 1건에서 0건 이상의 이벤트 초안 추출 |
| `ExtractedEventDraft`(frozen) | — | 이벤트 필드 + 근거 초안(`EvidenceDraft`)을 담는 경계 타입 |
| `EvidenceDraft`(frozen) | — | `evidence_role`·`relevance_score`·`extracted_quote` |

- 경계 타입 이름에 `DTO`를 쓰지 않는다(도메인 관례).
- Port는 문서 단위로 동작한다. 여러 문서를 하나로 묶는 것은 군집(#399)의 책임이며 이 단계가
  아니다.

## 3. 골격 추출기 — 규칙 기반

이번 단계의 구현체는 `RuleBasedEventExtractor`(이름은 재량)로 둔다. **값을 지어내지 않는다.**

- `event_type` — 본문·제목의 키워드 규칙으로 `EventType`(EARNINGS_GUIDANCE·BUYBACK·
  REGULATION·SUPPLY_CONTRACT·MANAGEMENT_CHANGE)을 판별한다. **규칙에 걸리지 않는 문서는
  이벤트를 만들지 않는다**(빈 리스트 반환). `event_type`은 NOT NULL이고 "미분류" 값이 없으므로,
  근거 없이 유형을 지어내느니 이벤트를 만들지 않는 편이 옳다.
- `title`·`summary` — 문서의 `title`·`raw_content`에서 파생한다(요약 생성은 LLM 몫이므로 골격은
  원문 기반으로 채운다).
- 점수(`sentiment_score`·`importance_score`·`confidence_score`) — 중립 placeholder로 둔다.
  `sentiment_direction`은 규칙으로 방향 정도만(긍/부정 키워드 없으면 `NEUTRAL`). 이 점수들은
  #397의 `source_reliability 0.5`와 같은 "미평가" 성격이며, 실측 점수는 #405가 채운다.
- `primary_symbol` — 원천 매핑에 종목 정보가 있으면 잇고, 없으면 `null`.
- `event_fingerprint` — 아래 §5.

## 4. 근거 연결 — `event_evidence`

- **모든 `extracted_event`는 최소 1건의 `event_evidence`를 가진다**(#398 원칙). 골격 추출기는
  그 이벤트를 만든 문서를 `PRIMARY` 근거로 연결한다.
- `evidence_role`·`relevance_score`·`extracted_quote`는 `EvidenceDraft`에서 온다. 골격은 원문
  문서를 `PRIMARY`·중립 `relevance_score`로 잇고, `extracted_quote`는 채울 근거가 없으면
  `null`로 둔다.
- 근거 없는 이벤트를 만들지 않는다. 이벤트와 근거는 같은 트랜잭션에서 함께 쓴다.

## 5. 멱등 — `event_fingerprint`

- `event_fingerprint`(NOT NULL, index)가 이벤트 재생성을 막는 멱등 키다. 같은 문서를 다시
  추출해도 같은 fingerprint의 이벤트가 중복 생성되지 않아야 한다.
- fingerprint 산식은 추출기가 결정론적으로 만든다 — 예: `event_type` + `primary_symbol` +
  근거 문서의 `content_hash` 조합의 해시(정확한 조합은 구현 재량, 결정론적일 것).
- 이미 존재하는 fingerprint는 재적재하지 않는다. 재실행이 안전해야 한다.

## 6. 처리 상태 전이

- 추출을 마친 `source_documents`는 `processing_status`를 `PENDING` → `EXTRACTED`로 전이한다.
- 규칙에 걸리는 이벤트가 없어 이벤트 0건인 문서도 **처리 자체는 끝난 것**이므로 `EXTRACTED`로
  전이한다(다시 추출 대상으로 잡히지 않게). 추출 실패(예외)는 `FAILED`로 둔다.
- 재실행 시 이미 `EXTRACTED`인 문서는 다시 추출하지 않는다(멱등의 문서 단위 방어).

## 7. 파이프라인 배관 — 함수 골격

신규 모듈 `app/domains/news_insights/extraction.py`(파일명 재량).

| 함수 | 시그니처(개략) | 책임 |
|---|---|---|
| `extract_events` | `(db, extractor: EventExtractor) -> ExtractionResult` | `PENDING` 문서 조회 → 추출 → 생성 → 상태 전이 조율 |
| `ExtractionResult`(projection) | — | 처리 문서·생성 이벤트·근거·스킵(멱등 중복)·실패 건수 집계 |

- 추출기는 인자로 주입한다(테스트는 골격/스텁 추출기, #405는 LLM 추출기).
- 이벤트·근거·문서 상태 전이는 문서 단위로 원자적이어야 한다.

## 8. 결정 현황 — 확정(2026-07-24)

- **배관+계약 우선(사용자 선택).** 실 LLM 추출기는 후속 **#405**. 이번 단계는 Port·배관·골격
  규칙 추출기·근거 연결·멱등·상태 전이를 세운다.
- **점수의 성격.** `sentiment`·`importance`·`confidence`는 LLM 분석 출력으로 허용되는 값이며
  (307 phase2 "별도 필드로 유지"), 자금 금액·기여 비율 같은 정량 금융 지표의 "LLM 숫자 생성
  금지"와는 범주가 다르다. 이번 골격은 이 점수를 중립 placeholder로 두고, #405가 실측한다.

## 9. ADR·실패 기록 판단

- ADR: 기존 고정 모델에 데이터를 채우는 작업이고 스키마·와이어 컨벤션 변경이 없으므로 **불요**.
  추출기 Port 도입은 기존 어댑터 경계 패턴(ADR-007 계열)의 연장이다.
- 실패 기록: 해당 없음. 부재하던 추출 경로를 만드는 작업이다.
