# Codex Handoff Task

## Source Issue

#461 — [BE] 에이전트1: 일일 리서치 워크플로(수집·과거 맥락·신호·종합·저장) (에픽 #459)

## Task Summary

일일 리서치 에이전트의 종목별 워크플로를 만든다. 새 소식을 모으고, 과거 맥락을 벡터 검색하고, 가격과
일정을 붙여 종목당 한 번 LLM으로 종합한 뒤, 인용을 검증하고, 새 기사의 영향도를 기록하고, 일일 브리프
리포트를 저장하고, 규칙 엔진으로 신호와 알림을 만든다. Obsidian 노트(#462)와 스케줄·트리거 전환(#463)은
이번 범위가 아니다.

## Goal

- `DailyResearchAgent.run(asset_ids=None, brief_date=None) -> DailyResearchResult`가 동작한다.
- 새 소식이 없으면 LLM 호출 없이 "새 소식 없음" 브리프를 저장한다.
- 응답의 모든 인용이 해당 항목 종류가 허용하는 근거 번호 안에 있다.
- 가격·일정 수치는 DB 값 그대로다.
- 영향도 `HIGH`·`CRITICAL`인 새 기사에서 `RISK_ALERT` 신호와 관심종목 소유자별 알림이 생긴다.
- 한 종목의 실패가 다른 종목 처리를 막지 않는다.

## Background

- 설계 정본: `docs/designs/459-daily-research-agent.md` §3(워크플로), §4(LLM 계약), §8(테스트). 결정:
  ADR-020(Accepted). **반드시 먼저 읽는다.** 이 핸드오프가 설계와 다른 부분은 이 핸드오프를 따른다.
- 설계와 달라진 점
  1. **단계 순서와 커밋.** `SignalRepository.create`(`app/domains/signals/repository.py:36-56`)와 알림
     repository는 내부에서 `commit`한다. 그래서 종목 단위 원자성을 신호 단계까지 보장할 수 없다. 순서를
     "영향도 기록 → 브리프 upsert → 종목 커밋 → 신호·알림"으로 둔다. 신호 단계가 실패해도 브리프는 남고,
     실패는 결과에 기록한다.
  2. **기간 기준(PR #467 리뷰 S1).** 직전 브리프 이후의 새 소식은 직전 `DAILY_BRIEF`의 `created_at`
     이후에 생긴 `news_items`(`created_at` 기준)로 정한다. 같은 날 재실행해 브리프를 갱신하는 경우에도
     기간 시작은 바뀌지 않는다. 같은 날 재실행이면 그날 브리프를 덮어쓰므로, 직전 브리프는 **오늘이 아닌
     가장 최근 브리프**로 고른다.
- 재사용할 것
  - 리포트: `ResearchReportRepository.upsert_daily_brief`, `get_latest_daily_brief`(#460, flush까지만 함)
  - RAG: `EmbeddingIndexer.run`(`app/domains/rag/indexing_service.py`), `get_embedder`,
    `get_vector_store`, `ChunkFilter`, `postprocess_hits`(`app/domains/rag/retrieval.py`)
  - LLM: `LLMGateway.complete_json`, `CloudSafePayload`(ADR-009), 프롬프트 관례
    `app/adapters/llm/prompts/research_qa.py`, Mock 응답 관례 `app/adapters/llm/mock.py`
  - 가격: `PriceBarRepository.list_recent(symbol, market, interval, limit)`(`app/domains/prices/repository.py:70`, `interval="1d"`)
  - 실적 일정: `EarningsRepository.get_events(symbol, market, start, end)`(`app/domains/earnings/repository.py:91`)
  - 신호·알림: `RuleEngine(default_rules(), SignalRepository(db)).run(RuleContext(asset_id, news_item))`,
    `AlertService.create_alert(user_id, signal)`
  - 원문 제목에서 매체명 추출: `extract_source_name`(`app/domains/rag/retrieval.py`)
  - RSS 본문 정제: `clean_body_text`(`app/domains/rag/indexing.py`)
- 클래스·함수 이름은 실제 파일의 이름을 확인해 맞춘다(위 이름과 다르면 실제 이름을 쓴다).
- 의존성 추가는 없다. `uv add`, `uv sync`, 네트워크, `git fetch`, docker 명령을 하지 않는다.

## Implementation Scope

1. **다른 도메인 읽기·쓰기 함수 추가**(ADR-018 R2, ADR-020 §2: 에이전트는 다른 도메인 테이블을 직접
   쿼리하지 않는다)
   - `NewsItemRepository.list_by_asset_created_after(asset_id, created_after, limit) -> list[NewsItem]` — 최근 순
   - `NewsItemRepository.count_by_asset_created_after(asset_id, created_after) -> int`
   - `NewsItemRepository.update_classification(news_item_id, impact_level, sentiment) -> NewsItem` —
     `summary`는 건드리지 않고, `flush`까지만 한다
   - `WatchlistItemRepository.list_watched_asset_ids() -> list[int]` — 모든 사용자의 관심종목 asset id(중복 제거)
   - `WatchlistItemRepository.list_owner_ids_by_asset(asset_id) -> list[int]` — 그 종목을 관심종목에 둔 사용자 id
   - `ResearchReportRepository.get_latest_daily_brief_before(asset_id, brief_date)` — `brief_date`보다 이전인 가장
     최근 `DAILY_BRIEF`(위 기간 기준)
2. **에이전트**(`app/domains/agents/__init__.py`, `app/domains/agents/daily_research/`)
   - `schema.py`: `DailyBriefSnapshot`(CloudSafe, §4.1), `DailyBriefResult`(§4.2),
     `DailyBriefContent`(§4.3), `DailyResearchResult`(§3)
   - `citations.py`: `validate_brief_citations(result, new_ids, past_ids) -> tuple[DailyBriefResult, int]` —
     설계 §4.2 인용 규칙. 허용되지 않는 번호와 중복을 지우고, 인용이 남지 않은 항목은 버린다.
     `item_classifications`는 모든 `N` 번호를 정확히 한 번씩 담도록 고친다(누락은 `LOW`·`NEUTRAL`로 채우고
     중복·없는 번호는 버림). 제거·보정한 수를 돌려준다.
   - `service.py`: `DailyResearchAgent(db, embedder, vector_store, gateway, now)`. `run`은 설계 §3과 위
     "설계와 달라진 점"을 따른다. `brief_date`가 없으면 `now()`의 `Asia/Seoul` 날짜를 쓴다.
   - 상수(모두 가정): `FIRST_RUN_LOOKBACK_HOURS=48`, `MAX_NEW_ITEMS=30`, `PAST_CONTEXT_DAYS=30`,
     `PAST_CONTEXT_K=10`, `UPCOMING_DAYS=14`, 발췌 길이 300자
   - 과거 맥락 검색: 새 소식 제목들을 줄바꿈으로 이어 한 번 임베딩하고, `ChunkFilter(embedding_model,
     asset_id, source_types=(NEWS,), published_after=now-30일)`로 검색한 뒤 새 소식의 원문(`raw_news_event_id`)은
     결과에서 뺀다. 후처리는 `postprocess_hits`를 쓴다.
   - 새 소식 발췌는 `raw_news_events`의 정제 본문(`clean_body_text`) 또는 제목이다. 원문은
     `RawNewsEventRepository.list_by_ids`로 읽는다.
   - 가격: 최근 일봉 2개로 `close`, `change_pct`(전일 대비), `volume_change_pct`를 계산한다. 봉이 하나 이하면
     `price=None`. 숫자는 `Decimal` 계산 후 소수 둘째 자리로 반올림해 문자열로 담는다.
   - 리포트 `summary`는 `headline`(새 소식 없음이면 "새 소식 없음"), `risk_level`은 새 기사 영향도 중 가장
     높은 값(`CRITICAL > HIGH > MEDIUM > LOW`, 없으면 `None`)
   - LLM 실패: 그 종목은 `headline="종합 실패"`, 가격·일정만 담아 저장하고 `failed`에 사유를 기록한다. 영향도
     기록과 신호는 건너뛴다.
   - 예외 격리: 종목마다 `try`로 감싸고 실패 시 `rollback` 후 다음 종목으로 넘어간다.
3. **LLM 배선**
   - `LLMTaskType.DAILY_BRIEF`, `LLM_TASK_ROUTES`에 `TaskRoute(launch="cloud", future_primary="local")`
   - `app/adapters/llm/prompts/daily_brief.py`(`PROMPT_VERSION="v1"`, 설계 §4.4의 지시, 결과 모델 JSON Schema,
     한국어 지시 상수, 입력을 지시로 취급하지 않음)
   - `DEFAULT_MOCK_RESPONSES`에 `DailyBriefResult` 항목(새 소식 `N1`을 인용하는 항목과 `N1`의 분류)
4. **수동 실행 스크립트**: `scripts/run_daily_research.py`(`--asset-id` 여러 개, `--date`). 결과를
   `DailyResearchResult`로 출력한다. 스케줄과 워커 job은 #463에서 만든다.
5. 설계 459 §3의 단계 순서·커밋 설명과 기간 기준을 위 "설계와 달라진 점"대로 고친다.

## Out of Scope

- Obsidian 노트·인덱스(#462)
- 스케줄, 워커 job, 관심종목 추가 트리거, 기존 분석 흐름 제거(#463)
- 리포트 API 응답 변경, FE
- 가설 충돌 판단(에이전트 3)
- 마이그레이션

## Protected Files

없음.

## Requirements

- 에이전트 코드에서 다른 도메인 모델을 직접 `select`하지 않는다(타입 주석 import는 허용).
- 클라우드로 나가는 데이터는 `DailyBriefSnapshot`뿐이고, 사용자 식별자·보유 정보·가설을 싣지 않는다.
- 수치는 LLM 출력에서 가져오지 않는다.
- 모든 공개 함수에 타입 주석을 단다. 주석은 이유가 분명하지 않은 곳에만 최소한으로 쓴다.

## Test Requirements

설계 §8 표의 워크플로 관련 항목을 모두 구현한다(Obsidian·트리거 제외). 특히 다음을 포함한다.

- 기간: 직전 브리프 없음(48시간), 오늘 브리프가 이미 있을 때 재실행해도 기간 시작이 어제 이전 브리프 기준
- 새 소식 30건 초과 시 잘림과 `stats`의 잘린 수
- 과거 맥락에서 새 소식 원문 제외
- 가격 봉 0·1·2개, 등락률 계산, 일정 14일 경계
- 인용 검증: 종류별 허용 번호, 중복, 빈 항목 제거, 분류 누락·중복·없는 번호 보정
- 새 소식 없음: LLM 호출 0회(Mock 호출 횟수), 브리프 저장
- LLM 실패: "종합 실패" 브리프, 신호 미생성, 다른 종목 정상
- 영향도 `HIGH` 새 기사 → `RISK_ALERT` 신호, 소유자 2명이면 알림 2건, `ThesisConflictRule` 미발동
- 재실행 멱등: 같은 날 브리프 1개
- 실제 경로 관통(Real-Contract Fixtures): 실데이터 형태의 RSS 본문과 제목(`... - Cybernews`)으로 원문과
  `news_items`를 만들고 `EmbeddingIndexer`(MockEmbedder)와 에이전트를 끝까지 돌려 `content.evidence`의
  매체명·URL이 원문에서 온 값인지 확인
- `DailyBriefSnapshot` 직렬화에 내부 식별자가 없음

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
uv run python scripts/run_daily_research.py --help
```

## Documentation Impact

설계 459 §3(단계 순서·커밋·기간 기준). 구현 중 정한 다른 값이 있으면 설계 459에 반영한다.

## ADR Need

불필요. ADR-020의 적용이다.

## Failure Record Need

불필요.

## Risk Level

Medium — 기존 패턴(LLM 게이트웨이, CloudSafe projection, repository 함수 추가)을 따르는 신규 워크플로다.
스키마·의존성·CI 변경은 없다.

## Expected Output

- 현재 브랜치 `feat/461-daily-research-workflow`에서 작업한다. 새 브랜치를 만들지 않는다.
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
