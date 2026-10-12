# Codex Handoff Task

## Source Issue

#442 — [BE] RAG 1차: 종목 리서치 Q&A API(검색·생성·인용 검증) (에픽 #438)

## Task Summary

`POST /api/v1/assets/{asset_id}/research-qa`를 만든다. 질문을 임베딩해 해당 종목의 뉴스 청크를
검색하고, 근거가 있으면 `LLMGateway`로 답을 생성하고, 인용 번호를 검증해 돌려준다. 근거가 없으면
LLM을 호출하지 않는다. Obsidian 저장은 #443에서 필드를 추가하는 방식으로 붙이므로 이번 범위가
아니다.

## Goal

완료 시 다음이 참이어야 한다.

- 엔드포인트가 인증된 요청에 `ApiResponse[ResearchAnswer]`를 돌려준다.
- 검색 후처리 결과 근거가 0건이면 LLM 호출이 0회다.
- 응답의 모든 `answer_points[].citations`는 `evidence[].id` 안의 값이다. 유효 인용이 없는 point는
  응답에 없다.
- 질문 임베딩이 실패하면 503 `RAG_EMBEDDING_UNAVAILABLE`, LLM 호출이 실패하면 200과
  `insufficient_evidence=true`(근거 목록은 채움)를 돌려준다.

## Background

- 설계 정본: `docs/designs/438-rag-research-qa.md` §5(API, 서비스, LLM 배선, 인용 검증, 실패 처리),
  §6(모듈 경계). 반드시 먼저 읽는다. 이 핸드오프가 설계와 다른 부분은 이 핸드오프를 따른다.
- 설계와 달라진 점
  - `save_to_obsidian`(request)과 `obsidian_note_path`(response)는 이번에 넣지 않는다. #443에서
    추가 필드로 붙인다.
  - `EvidenceItem.source_name`은 `raw_news_events.source`가 아니라 제목의 ` - 매체명` 꼬리에서
    가져온다. `source` 값은 실매체가 아니라 Google News 피드 제목이다(예:
    `"NVIDIA Corporation" - Google News`, 설계 397 §4.6에도 기록됨). 꼬리가 없으면 `source`를 쓴다.
- 1차 근거 수준: 뉴스 본문은 정제 후 대부분 헤드라인 수준이다(`TITLE_ONLY` 2,652/2,703건,
  #441 실측). 근거가 짧다는 전제로 프롬프트를 쓴다.
- 기존 자산
  - `get_embedder()`, `get_vector_store(db)`, `get_llm_gateway()`(`app/adapters/factory.py`)
  - `VectorStore.search(query_vector, ChunkFilter, k) -> list[ChunkHit]`, `ChunkHit.score`는 코사인
    유사도
  - `LLMGateway.complete_json(task_type, payload, schema, system_prompt)`(`gateway.py:59-66`)
  - 안전 실패 관례: `app/domains/decision_logs/assist_service.py`의 `assist`(LLM 예외 시 경고 로그 후
    빈 결과)
  - 프롬프트 관례: `app/adapters/llm/prompts/decision_assist.py`(`PROMPT_VERSION`, 결과 모델 JSON
    Schema 포함, `KOREAN_NATURAL_LANGUAGE_OUTPUT_INSTRUCTION`)
  - projection 관례: `app/adapters/llm/privacy.py`의 `DecisionAssistSnapshot(CloudSafePayload)`
  - Mock LLM은 결과 모델 이름(`schema.__name__`)으로 응답을 찾는다
    (`app/adapters/llm/mock.py`의 `DEFAULT_MOCK_RESPONSES`). `ResearchQAResult` 항목을 추가한다.
  - 엔드포인트 관례: `app/api/v1/endpoints/assets.py`의 `/{asset_id}/research-coverage`
  - asset 404 관례: `research_coverage/service.py`의 `AppException(404, ..., ErrorCode.ASSET_NOT_FOUND)`
  - 현재 시각: `app/domains/signals/time.py`의 `utc_now`(다른 도메인 유틸이므로 rag 안에 같은 한 줄
    함수를 두거나 `datetime.now(UTC)`를 쓰고, 테스트에서 고정할 수 있게 주입 가능한 형태로 둔다)
- 경계 규칙(ADR-018 R1·R2·R5): rag는 다른 도메인 테이블을 직접 쿼리하지 않는다. 원문 메타데이터는
  `RawNewsEventRepository`에 `list_by_ids(ids) -> list[RawNewsEvent]`를 추가해 읽는다. asset은
  `AssetRepository.get_by_id`를 쓴다. LLM은 `LLMGateway`로만 호출한다.
- PR #452 리뷰 S1: `OpenAIEmbedder`의 실패 메시지가 공급자를 OpenAI로 단정한다
  (`app/adapters/embedding/openai.py:45`). 모델명과 base URL을 담은 메시지로 바꾼다(API 키는 넣지
  않는다).
- 의존성 추가는 없다. `uv add`, `uv sync`, 네트워크, `git fetch`, docker 명령을 하지 않는다.

## Implementation Scope

1. **스키마**(`app/domains/rag/schema.py`)
   - `ResearchQARequest`: `question: str`(앞뒤 공백 제거 후 1~500자, 가정), `lookback_days: int = 90`
     (1~365, 가정)
   - `AnswerPoint`: `text: str`, `citations: list[int]`
   - `EvidenceItem`: `id`, `source_type`, `source_id`, `title`, `source_name`, `source_url`,
     `published_at`, `excerpt`, `score`, `content_quality`
   - `ResearchAnswer`: `answer_points`, `limitations: str | None`, `insufficient_evidence: bool`,
     `evidence: list[EvidenceItem]`, `generated_at`
   - LLM 결과 모델 `ResearchQAResult`: `answer_points: list[AnswerPoint]`, `limitations: str | None`,
     `insufficient_evidence: bool`
2. **검색 후처리**(`app/domains/rag/retrieval.py`, 순수 함수 위주)
   - 상수(모두 가정): `CANDIDATE_K=20`, `MIN_SCORE=0.3`, `MAX_CHUNKS_PER_SOURCE=2`,
     `TITLE_ONLY_WEIGHT=0.8`, `FINAL_EVIDENCE_K=8`
   - 순서: 하한 미만 제거 → `TITLE_ONLY`에 가중치 적용한 점수로 재정렬 → 원문당 최대 2청크 →
     상위 8개. 동점은 `chunk_id` 오름차순. 응답 `score`에는 가중치를 적용한 값을 쓴다.
3. **LLM 배선**
   - `LLMTaskType.RESEARCH_QA` 추가, `LLM_TASK_ROUTES`에 `TaskRoute(launch="cloud", future_primary="cloud")`
   - `ResearchQASnapshot(CloudSafePayload)`: `symbol`, `asset_name`, `question`,
     `evidence: list[ResearchQAEvidenceProjection]`(`id`, `title`, `source_name`, `published_at`,
     `excerpt`). 내부 식별자(`user_id`, `asset_id`, `chunk_id`, `source_id`)를 싣지 않는다.
     sensitivity는 기존 snapshot들의 기준을 따른다.
   - `app/adapters/llm/prompts/research_qa.py`: `PROMPT_VERSION = "v1"`,
     `build_research_qa_system_prompt()`. 지시 내용
     - 제공된 근거로만 답한다. 근거에 없는 사실, 수치, 날짜를 만들지 않는다.
     - 모든 point에 근거 번호(`citations`)를 붙인다.
     - 근거가 헤드라인 수준이면 그 한계를 `limitations`에 밝힌다.
     - 근거가 질문에 답하기에 부족하면 `insufficient_evidence=true`로 답한다.
     - 매수·매도 권유, 목표가 제시, 수익 보장 표현을 하지 않는다.
     - 결과 모델의 JSON Schema만 반환한다. 한국어 지시 상수를 붙인다.
   - `DEFAULT_MOCK_RESPONSES`에 `ResearchQAResult` 항목 추가(인용 `[1]`을 가진 point 한 개)
4. **서비스**(`app/domains/rag/service.py`)
   - `ResearchQAService(db, embedder, vector_store, gateway, now: Callable[[], datetime] = ...)`
   - `ask(asset_id, request) -> ResearchAnswer`
     1. asset 조회, 없으면 404 `ASSET_NOT_FOUND`
     2. 질문 임베딩. `EmbeddingError`이면 `AppException(503, ..., ErrorCode.RAG_EMBEDDING_UNAVAILABLE)`
     3. `ChunkFilter(embedding_model=embedder.model_name, asset_id=..., source_types=(NEWS,),
        published_after=now - lookback_days)`로 `CANDIDATE_K` 검색
     4. 후처리 후 원문 메타데이터를 `list_by_ids`로 한 번에 읽어 `EvidenceItem`을 만든다(번호 1부터).
        `excerpt`는 청크 `content` 앞 300자(가정).
     5. 근거 0건이면 LLM 없이 `insufficient_evidence=true`, 빈 `answer_points`,
        `limitations="최근 {lookback_days}일 안에 이 종목과 관련된 근거를 찾지 못했습니다."`(문구는
        자연스러운 한국어로 다듬어도 됨)
     6. 근거가 있으면 `gateway.complete_json(RESEARCH_QA, snapshot, ResearchQAResult, prompt)`.
        예외가 나면 경고 로그 후 `insufficient_evidence=true`, `answer_points=[]`, 근거 목록은 그대로,
        `limitations`에 답변 생성 실패를 밝힌다.
     7. 인용 검증 후 응답을 만든다.
   - `validate_citations(result, evidence_ids) -> tuple[ResearchQAResult, int]`(순수 함수): 없는 번호
     제거, 중복 번호 제거(순서 유지), 유효 인용이 없는 point 제거, 모두 제거되면
     `insufficient_evidence=true`. 제거한 point 수를 함께 돌려주고 서비스가 info 로그로 남긴다.
5. **에러 코드**: `ErrorCode.RAG_EMBEDDING_UNAVAILABLE` 추가
6. **엔드포인트**: `app/api/v1/endpoints/assets.py`에
   `POST /{asset_id}/research-qa`(`response_model=ApiResponse[ResearchAnswer]`, summary·description
   기존 형식). 의존성은 factory 함수로 만든다. 인증 필수.
7. **repository 읽기 함수**: `RawNewsEventRepository.list_by_ids(ids: list[int]) -> list[RawNewsEvent]`
8. **PR #452 S1**: `OpenAIEmbedder` 실패 메시지에 모델명과 base URL을 담는다.
9. **문서**
   - 설계 438 §5에 위 "설계와 달라진 점" 두 가지를 반영한다.
   - `docs/api/frontend-api-spec.md`에 새 엔드포인트와 에러 코드를 기존 형식대로 추가한다.

## Out of Scope

- Obsidian 저장(#443), 평가 세트(#444)
- 캐시, 대화 이력, 질문 재작성, 하이브리드 검색
- FE(`project_stock_frontend#308`)
- 마이그레이션

## Protected Files

없음.

## Requirements

- rag 코드에서 다른 도메인 모델을 직접 `select`하지 않는다(타입 주석용 import는 허용).
- 클라우드로 나가는 payload는 `ResearchQASnapshot`뿐이다(ADR-009).
- 모든 공개 함수에 타입 주석을 단다.
- 주석은 이유가 분명하지 않은 곳에만 최소한으로 쓴다.

## Test Requirements

- 단위
  - 검색 후처리: 하한, 가중치 재정렬, 원문당 2청크, 최종 k, 동점 처리
  - `validate_citations`: 없는 번호, 중복, 인용 없는 point, 전부 제거
  - `source_name` 추출: 꼬리 있음, 꼬리 없음(fallback `source`), 제목에 ` - `가 여러 번
  - 프롬프트에 금지 지시와 JSON Schema가 포함됨
  - `ResearchQASnapshot` 직렬화에 내부 식별자가 없음
- 서비스·API(SQLite + `InMemoryVectorStore` + `MockEmbedder` + Mock 게이트웨이)
  - 정상: 근거가 있고 Mock 응답의 인용이 유효
  - 근거 0건: LLM 호출 0회를 호출 횟수로 검증
  - 기간 필터: `lookback_days` 밖의 근거 제외(`now` 주입으로 고정)
  - 다른 종목 근거 제외
  - LLM 예외: 200, `insufficient_evidence=true`, 근거 목록 유지
  - 임베딩 예외: 503 `RAG_EMBEDDING_UNAVAILABLE`
  - asset 없음 404, 질문 빈 문자열·501자 422, 인증 없음 401
- 실제 경로 관통(Real-Contract Fixtures): 한 테스트는 `raw_news_events`·`news_items`를 만들고
  `EmbeddingIndexer`로 적재한 뒤 API를 호출해 응답 근거의 `title`·`source_name`이 원문에서 온 값인지
  확인한다. 원문 제목은 실데이터 형태(`... - Cybernews`)를 쓴다.
- 실패 메시지 테스트: `EmbeddingError` 메시지에 모델명이 들어가고 API 키는 들어가지 않는다.

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

설계 438 §5와 `docs/api/frontend-api-spec.md`를 위 범위대로 갱신한다.

## ADR Need

불필요. ADR-018과 ADR-009의 적용이다.

## Failure Record Need

불필요.

## Risk Level

Medium — 기존 패턴(LLM 게이트웨이, CloudSafe projection, 엔드포인트)을 따르는 신규 API다. 사용자
자유 텍스트(질문)가 클라우드 LLM으로 나가는 경로이므로 ADR-009 경계는 사람 리뷰가 필요하다.

## Expected Output

- 현재 브랜치 `feat/442-research-qa-api`에서 작업한다. 새 브랜치를 만들지 않는다.
- 커밋이 샌드박스에서 막히면 미커밋 상태로 두고 보고한다. push와 PR 생성은 하지 않는다.
- 최종 보고: 변경 파일 목록, 가정, 검증 명령별 결과, 실행하지 못한 검증

## Stop Conditions

- 설계·이 핸드오프와 다르게 구현해야 하는 상황
- 의존성 추가나 마이그레이션이 필요한 상황
- 기존 테스트가 이 변경과 무관한 이유로 실패하는 상황
- 샌드박스 권한 부족

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
