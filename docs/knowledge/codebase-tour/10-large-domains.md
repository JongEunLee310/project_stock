# 10. 대형 도메인 — news_insights, decision_logs, research_*

대상 파일: `app/domains/news_insights/*`(약 3,700줄), `app/domains/decision_logs/*`,
`app/domains/research_queue/*`, `app/domains/research_summary/*`, `app/domains/research_coverage/*`

앞 단계까지 본 골격(`model`/`schema`/`repository`/`service`)이 **한계에 부딪혔을 때 어떻게
확장되는가**를 보는 단계입니다. 세 도메인이 각각 다른 방향으로 늘어났습니다.

| 도메인 | 늘어난 방향 | 결과 |
| --- | --- | --- |
| `news_insights` | **파이프라인 단계** | 15개 테이블, 단계별 파일 6개 |
| `decision_logs` | **상태 전이와 이력** | 6개 테이블, 상태 머신 |
| `research_*` | **도메인 자체 분할** | 3개 도메인으로 쪼갬 |

## news_insights — 3층 파이프라인

### 개념 구조

```text
SourceDocument  (원문)      뉴스·공시 원문 1건
      ↓ extraction
ExtractedEvent  (사건)      "삼성전자 3분기 실적 발표" 같은 사건 1건
      ↓ clustering
TopicCluster    (주제)      여러 사건을 묶은 이야기 흐름
      ↓ interpretation
TopicInsight    (해석)      주제에 대한 분석 결과
```

**뉴스 기사 1건 = 사건 1건이 아니라는 것**이 이 설계의 출발점입니다. 같은 사건을 10개 언론사가
보도하면 문서는 10건이지만 사건은 1건이어야 합니다. 그리고 여러 사건이 하나의 흐름(예: "반도체
업황 회복")을 이룹니다.

15개 테이블이 이 3층을 중심으로 배치됩니다.

```text
[1층 문서]  source_documents
[연결]      event_evidence           사건 ↔ 문서 (근거)
[2층 사건]  extracted_events
[연결]      market_event_topics      사건 ↔ 주제
[3층 주제]  topic_clusters, topic_keywords, keyword_relations
[해석]      topic_insights, topic_explanations, explanation_factors
[파생]      investor_flows, fund_flow_outlooks, fund_flow_scenarios,
            topic_symbol_sensitivity, market_events
[실행기록]  agent_runs, agent_run_stages
```

### 근거 연결이 별도 테이블

```python
class EventEvidence(Base):
    __tablename__ = "event_evidence"
    event_id: Mapped[int] = mapped_column(ForeignKey("extracted_events.id"))
    document_id: Mapped[int] = mapped_column(ForeignKey("source_documents.id"))
    relevance_score: Mapped[float] = mapped_column(Float)
    evidence_role: Mapped[str] = mapped_column(String(20))
    extracted_quote: Mapped[str | None] = mapped_column(Text)
```

09단계에서 본 "판정에는 근거가 따라야 한다"가 여기서는 **테이블 하나로 승격**됐습니다. 단순
N:M 연결 테이블이 아니라 `relevance_score`(얼마나 관련 있는가), `evidence_role`(어떤 역할의
근거인가), `extracted_quote`(원문의 어느 문장인가)를 함께 담습니다.

`extracted_quote`가 있으면 화면에서 **"이 사건은 이 기사의 이 문장 때문에 추출됐습니다"** 를
보여줄 수 있습니다. LLM이 만든 결과를 사용자가 검증할 수 있게 하는 장치입니다.

### CheckConstraint로 점수 범위를 DB에서 강제

```python
def _score_constraint(table_name: str, column_name: str) -> CheckConstraint:
    return CheckConstraint(
        f"{column_name} >= 0.0 AND {column_name} <= 1.0",
        name=f"ck_{table_name}_{column_name}_range",
    )

class ExtractedEvent(Base):
    __table_args__ = (
        _score_constraint("extracted_events", "importance_score"),
        _score_constraint("extracted_events", "sentiment_score"),
        _score_constraint("extracted_events", "confidence_score"),
    )
```

**이 프로젝트에서 `CheckConstraint`를 쓰는 거의 유일한 곳**입니다. 다른 도메인은 검증을 Pydantic에
맡기는데 여기서는 DB까지 내려갔습니다.

이유는 값의 출처에 있습니다. 이 점수들은 **LLM이 만듭니다.** 07단계에서 본 대로 LLM 응답은
신뢰할 수 없는 입력이고, 코드 경로가 여러 개(파이프라인, 시드, 재처리)이므로 애플리케이션
검증만으로는 새는 곳이 생깁니다. **값의 출처가 불확실할수록 DB 제약이 가치 있다**는 판단입니다.

제약 생성을 함수로 뽑아 이름 규칙(`ck_{table}_{column}_range`)을 통일한 것도 03단계에서 지적한
"제약 이름을 직접 붙여야 한다"에 대한 대응입니다.

### 복합 인덱스

```python
        Index("ix_source_documents_document_type_published_at", "document_type", "published_at"),
        Index("ix_event_evidence_event_id_evidence_role", "event_id", "evidence_role"),
```

앞 단계 도메인들이 `index=True`로 단일 컬럼 인덱스만 쓴 것과 달리 **복합 인덱스**를 명시합니다.
"공시 문서를 최신순으로" 같은 쿼리가 실제로 있다는 뜻이며, 컬럼 순서가 중요합니다 —
`(document_type, published_at)` 인덱스는 `document_type`만으로 필터링할 때도 쓰이지만
`published_at`만으로는 쓰이지 않습니다.

### 파일이 파이프라인 단계로 나뉜다

```text
ingestion.py       원문 수집 → SourceDocument 저장
extraction.py      문서 → 사건 추출 (LLM)
clustering.py      사건 → 주제 군집
interpretation.py  주제 → 해석 (LLM)
pipeline.py        위 넷을 순서대로 실행
briefing.py        결과를 브리핑으로 조립
seed.py            개발용 시드 데이터
clock.py           시각 주입
```

04단계 `watchlists`가 **응답 단위로** service를 나눈 것과 대비됩니다. 여기는 **처리 단계 단위로**
나뉩니다. 데이터가 한 방향으로 흐르는 파이프라인이므로 자연스러운 분할입니다.

`clock.py`가 따로 있는 것이 눈에 띕니다.

```python
def utcnow() -> datetime: ...
```

`datetime.now(UTC)`를 직접 부르지 않고 한 함수를 거치게 하면, 테스트에서 이 함수만 교체해 시간을
고정할 수 있습니다. 06단계 mock이 고정 상수를 쓴 것과 같은 목적입니다.

### pipeline.py — 단계별 실행 기록

```python
def run_pipeline(db, extractor, clusterer, interpreter) -> PipelineRunResult:
    run = AgentRun(started_at=utcnow(), status=AgentRunStatus.RUNNING.value, ...)
    db.add(run)
    db.commit()
    run_id = run.id
    current_stage = AgentStage.COLLECT
    extraction_result = ExtractionResult()

    try:
        ingestion_result = ingest_source_documents(db)
        _record_stage(db, run_id, current_stage, AgentRunStatus.COMPLETED)

        current_stage = AgentStage.EXTRACT
        extraction_result = extract_events(db, extractor)
        _record_stage(db, run_id, current_stage, AgentRunStatus.COMPLETED)

        current_stage = AgentStage.CLUSTER
        ...
    except Exception:
        db.rollback()
        _record_stage(db, run_id, current_stage, AgentRunStatus.FAILED)
        failed_run = db.get(AgentRun, run_id)
        failed_run.status = AgentRunStatus.FAILED.value
        ...
        db.commit()
        raise
```

08단계 `JobRun`이 잡 전체를 기록했다면, 여기는 **단계별로 기록**합니다. `AgentRun`(실행 1회) +
`AgentRunStage`(단계별 상태)의 2단 구조입니다.

`current_stage` 변수를 단계마다 갱신하는 것이 핵심 기법입니다. 예외가 나면 `except` 블록에서 이
변수를 읽어 **어느 단계에서 실패했는지 정확히 기록**합니다. 이것이 없으면 "파이프라인 실패"만
남고 원인 추적이 어렵습니다.

```python
    extraction_result = ExtractionResult()   # try 진입 전 빈 결과로 초기화
    ...
    except Exception:
        ...
        failed_run.processed_documents = extraction_result.processed_document_count
```

08단계에서 `job_run_id: int | None = None`으로 초기화했던 것과 같은 방어입니다. 추출 단계 전에
실패하면 `extraction_result`가 없으므로, 빈 객체로 초기화해 두어 `except`에서 안전하게 참조합니다.
**부분 진행 상황도 기록**하려는 의도입니다.

```python
        db.rollback()
        _record_stage(db, run_id, current_stage, AgentRunStatus.FAILED)
```

`rollback()`이 **실패 기록보다 먼저**입니다. 03단계에서 본 대로 PostgreSQL은 에러 후 트랜잭션을
거부하므로, 롤백하지 않으면 실패 기록 자체가 실패합니다. 08·09단계에 이어 세 번째로 등장하는
패턴입니다.

단, `run` 생성 시 이미 `commit()`했기 때문에 롤백해도 `AgentRun` 행은 남습니다. **의도적으로
실행 기록을 먼저 확정**한 것입니다.

### repository — Record 타입으로 조립 결과를 실어 나른다

`repository.py`가 1,016줄인데, 그 앞부분이 **20개 이상의 frozen dataclass 정의**입니다.

```python
@dataclass(frozen=True)
class EventRecord:
    event: ExtractedEvent
    document: SourceDocument | None
    evidence_count: int
    topic_ids: tuple[int, ...]

@dataclass(frozen=True)
class EventPage:
    records: tuple[EventRecord, ...]
    has_more: bool
```

앞 단계 repository들은 ORM 객체나 그 리스트를 돌려줬습니다. 여기서는 **여러 테이블에서 모은 결과를
묶은 Record 타입**을 돌려줍니다.

```python
    def list_events(self, query: EventsQuery, cursor: DateTimeCursor | None) -> EventPage:
        stmt = (select(ExtractedEvent)
                .where(*self._event_conditions(query, cursor))
                .order_by(ExtractedEvent.detected_at.desc(), ExtractedEvent.id.desc())
                .limit(query.limit + 1))
        fetched_events = list(self.db.scalars(stmt).all())
        has_more = len(fetched_events) > query.limit
        events = fetched_events[: query.limit]
        event_ids = [event.id for event in events]
        documents, evidence_counts = self._documents_by_event(event_ids)   # 배치 조회
        topic_ids = self._topic_ids_by_event(event_ids)                    # 배치 조회
        return EventPage(records=tuple(EventRecord(...) for event in events), has_more=has_more)
```

두 가지가 눈에 띕니다.

**① `limit + 1` 기법** — 요청보다 하나 더 가져와서 실제로 더 있는지 확인하고, 응답에서는 잘라
냅니다. `COUNT(*)` 쿼리 없이 `has_more`를 알아내는 커서 페이지네이션의 표준 기법입니다. 02단계
`CursorPageMeta.has_more`가 여기서 채워집니다.

**② 배치 조회를 repository가 책임진다** — `_documents_by_event(event_ids)`가 ID 목록을 한 번에
받습니다. 04단계에서 service가 루프로 단건 조회하던 것과 정반대이며, **service는 조립된 Record만
받으면 되므로 N+1을 만들 기회 자체가 없습니다.**

`tuple`을 쓰는 것도 일관됩니다. `frozen=True` dataclass에 `list`를 넣으면 불변성이 깨지므로
`tuple`이 맞습니다.

### 이 도메인이 다른 곳과 다른 점

| 항목 | 다른 도메인 | news_insights |
| --- | --- | --- |
| repository 반환 | ORM 객체 | Record dataclass |
| 배치 조회 책임 | service (또는 누락) | repository |
| 점수 검증 | Pydantic만 | Pydantic + DB CheckConstraint |
| 인덱스 | 단일 컬럼 | 복합 인덱스 명시 |
| 실행 기록 | JobRun 1건 | AgentRun + AgentRunStage |
| 시각 | `datetime.now(UTC)` 직접 | `clock.utcnow()` 경유 |

**가장 나중에 만들어진 도메인이 가장 정제되어 있습니다.** 앞 단계에서 발견한 문제들(N+1, 검증
누락, 시간 고정 어려움)이 여기서는 대부분 해결되어 있습니다. 코드베이스의 품질이 시간순으로
올라갔다는 증거이며, 새 도메인을 만들 때는 이쪽을 본보기로 삼는 것이 맞습니다.

## decision_logs — 상태 머신과 이력

### 6개 테이블

```text
decision_logs             판단 본체
decision_evidence         근거
decision_risks            식별한 위험
decision_review_triggers  재검토 조건
decision_snapshots        판단 시점의 상태 저장
decision_reviews          복기 기록
```

**"왜 그렇게 판단했는가"를 구조화**한 것이 이 도메인입니다. 09단계 `Signal`이 `reason`·`evidence`를
텍스트 컬럼으로 가졌다면, 여기서는 각각 테이블입니다.

`decision_snapshots`가 특히 중요합니다. **판단 당시의 가격·시그널·포트폴리오 상태를 함께
저장**해야 나중에 "그때 그 정보로 그 판단이 타당했는가"를 검증할 수 있습니다. 09단계
`AssetSignalSnapshot`이 그랬듯 정규화를 일부러 깨고 복사해 둡니다.

### 상태 머신

```python
class DecisionStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    REVIEW_DUE = "REVIEW_DUE"
    REVIEWED = "REVIEWED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
```

```python
    decided_at / activated_at / reviewed_at / closed_at
```

**상태마다 대응하는 타임스탬프 컬럼**이 있습니다. `status` 하나만 두면 "언제 활성화됐는가"를 알 수
없으므로, 상태 전이 시각을 각각 남깁니다. 상태 머신을 다루는 흔한 방식입니다.

```python
    def revise(self, decision_log_id: int, user_id: int) -> DecisionLogDetailResponse:
        source = self._get_owned_decision_log(decision_log_id, user_id)
        if source.status in {DecisionStatus.DRAFT.value, DecisionStatus.CANCELLED.value} \
                or source.superseded_by_id is not None:
            raise AppException(409, "대체 가능한 의사결정 기록 상태가 아닙니다.",
                               ErrorCode.DECISION_LOG_INVALID_STATE)
        revised = self.repo.revise(source)
```

**상태 전이가 가능한지 service가 검사**합니다. 이 프로젝트에서 **409 Conflict를 쓰는 거의 유일한
곳**인데, 정확한 선택입니다 — 요청 자체는 올바르고(400 아님) 권한도 있지만(403 아님) 리소스의
현재 상태가 그 동작을 허용하지 않는 경우입니다.

```python
    superseded_by_id: Mapped[int | None] = mapped_column(ForeignKey("decision_logs.id"), nullable=True)
```

**자기 참조 외래키**입니다. 판단을 수정하면 원본을 UPDATE하지 않고 **새 행을 만들어 원본이 그것을
가리키게** 합니다. 09단계 `Signal`이 "생성 후 수정하지 않는다"였던 것과 같은 철학이며, 여기서는
버전 체인까지 만듭니다. `superseded_by_id is not None`이면 이미 대체된 것이므로 다시 수정할 수
없습니다.

**판단 기록을 나중에 고칠 수 있으면 기록의 의미가 없다**는 도메인 요구가 스키마로 표현된
형태입니다.

```python
    created_by: Mapped[str] = mapped_column(String(20), default=CreatedBy.USER.value, ...)
```

사람이 만든 판단과 시스템이 제안한 판단을 구분합니다. `assist_service.py`(LLM 보조)와
`review_trigger_service.py`(자동 재검토 트리거)가 시스템 쪽을 담당합니다.

### 서비스가 3개로 나뉜 이유

```text
service.py                CRUD + 상태 전이 (478줄)
assist_service.py         LLM 판단 보조
review_trigger_service.py 재검토 조건 평가 (스케줄러가 5분마다 호출)
```

04단계와 같은 응답 단위 분할이 아니라 **호출 주체별 분할**입니다. `service.py`는 사용자 요청,
`assist_service.py`는 사용자 요청 + LLM, `review_trigger_service.py`는 08단계
`evaluate_decision_review_triggers_job`이 부릅니다.

### repository가 827줄인 이유

6개 테이블을 다루면서 목록·상세·통계·유사 판단 검색까지 담당합니다.
`get_overview`·`get_analytics` 같은 집계 응답이 있어 쿼리 종류가 많습니다.

`_get_owned_decision_log`를 모든 public 메서드가 첫 줄에서 호출하는 것은 04단계와 동일합니다.
**도메인이 커져도 이 규칙은 변하지 않습니다.**

## research_* — 도메인을 셋으로 쪼개다

```text
research_queue    무엇을 리서치해야 하는가 (목록·우선순위)
research_summary  리서치 결과 요약 (LLM)
research_coverage 커버리지 점검 (데이터가 충분한가)
```

`reports` 도메인까지 포함하면 넷입니다. 하나의 "리서치" 도메인으로 묶을 수도 있었지만 나눴습니다.

이유는 **수명주기가 다르기** 때문입니다. `research_queue`는 매번 계산되는 뷰이고,
`research_summary`는 저장되는 산출물이며, `research_coverage`는 판정 로직입니다.

```python
class ResearchQueueService:
    def __init__(self, db: Session) -> None:
        self.repository = ResearchQueueRepository(db)
        self.summary_service = ResearchSummaryService(db, get_llm_gateway())
```

`research_queue`가 `research_summary`를 부릅니다. **단방향 의존**이므로 순환이 생기지 않습니다.
04단계 `WatchlistService → PortfolioService`와 같은 형태입니다.

```python
_RISK_SIGNAL_TYPES = {"RISK_ALERT", "THESIS_BROKEN"}
_NEEDS_RESEARCH_STATUSES = {
    ResearchStatus.NEEDS_ATTENTION, ResearchStatus.INSUFFICIENT,
    ResearchStatus.COLLECTING, ResearchStatus.PENDING_ANALYSIS,
}
```

```python
from app.domains.signals.types import WATCHLIST_STATUS_PRIORITY
```

09단계에서 정의한 우선순위 튜플을 **가져다 씁니다.** 04단계에서 본 `CASH_FLOOR_HIGH` 재사용과
같은 규칙 — 판정 기준은 정의한 도메인에서 import합니다.

`_RISK_SIGNAL_TYPES`가 enum이 아니라 **문자열 집합**인 점은 아쉽습니다. `SignalType.RISK_ALERT.value`를
쓰면 오타를 타입 체커가 잡아줍니다.

`ResearchQueueService`에 model이 없는 것도 특징입니다. **다른 도메인의 데이터를 읽어 계산으로
만들어내는 뷰**이므로 자체 테이블이 필요 없습니다. 09단계 `alert_engine`과 같은 성격입니다.

## 대형 도메인을 읽는 순서

이런 도메인을 처음 볼 때는 다음 순서가 효율적입니다.

1. **`types.py`** — 어휘와 상태값. 도메인의 개념 지도.
2. **`model.py`의 클래스 목록** — 테이블 관계. `grep -n "^class"`로 충분.
3. **`pipeline.py` 또는 `service.py`의 public 메서드 목록** — 무엇을 할 수 있는가.
4. 관심 있는 흐름 하나만 끝까지 추적.

`repository.py` 1,000줄을 처음부터 읽는 것은 비효율적입니다. 필요한 메서드만 찾아 읽으면 됩니다.

## 이 단계에서 확인한 프로젝트 규칙

1. 파이프라인형 도메인은 **처리 단계별로 파일을 나눈다**(`ingestion`/`extraction`/`clustering`/
   `interpretation`/`pipeline`). 응답별 분할(04단계)과 구분한다.
2. 다단계 실행은 `AgentRun` + `AgentRunStage`처럼 단계별로 기록하고, `current_stage` 변수로 실패
   지점을 남긴다.
3. LLM이 만든 수치처럼 출처가 불확실한 값은 DB `CheckConstraint`까지 건다.
4. 복합 조회가 많은 repository는 **Record dataclass를 정의해 조립까지 책임진다.** service가 루프
   조회를 하지 않게 만든다.
5. 커서 페이지네이션은 `limit + 1`로 조회해 `has_more`를 판정한다.
6. 기록성 데이터(판단·시그널)는 UPDATE하지 않고 새 행 + `superseded_by_id` 체인으로 관리한다.
7. 상태 전이 위반은 409(`DECISION_LOG_INVALID_STATE`)로 응답한다.
8. 판단 시점의 맥락은 스냅샷 테이블에 복사해 둔다. 정규화보다 검증 가능성을 우선한다.
9. 시각은 `clock.utcnow()` 같은 단일 함수를 경유해 테스트에서 고정 가능하게 한다.
10. 도메인이 커지면 수명주기가 다른 부분을 별도 도메인으로 분리한다. 판정 기준 상수는 정의한
    도메인에서 import한다.

## 알아둘 만한 개선 지점

- `research_queue`의 `_RISK_SIGNAL_TYPES`가 문자열 집합이다. `SignalType` enum을 쓰는 편이 안전하다.
- `news_insights.repository`(1,016줄)는 테이블 그룹별로 분할 여지가 있다.
- 같은 문제(N+1, 시간 고정, 점수 검증)의 해법이 도메인마다 다르다. `news_insights` 방식이 가장
  정제되어 있으므로 신규 도메인의 본보기로 삼을 만하다.

## 다음 단계로 이어지는 질문

- 테스트는 어느 계층을 어떻게 검증하는가? (11단계)
- 외부 의존(Redis·yfinance·OpenAI)은 테스트에서 어떻게 대체되는가? (11단계)
- 픽스처는 어떤 계층 구조인가? (11단계)
