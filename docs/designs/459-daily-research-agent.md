# BE 설계: 에이전트 1 — 관심종목 일일 리서치 — 에픽 #459

상태: **설계 초안(Draft)** — 2026-10-12. 하위 이슈 #460~#463. 결정은 ADR-020(작업형 에이전트를 고정
워크플로로 만들고, 관심종목 분석 흐름을 이 에이전트로 대체). RAG 부품은 ADR-018·설계 438을 재사용한다.

이 문서는 일일 리서치 에이전트의 워크플로, 데이터 모델 변경, LLM 계약, 산출물, 트리거 전환을
스켈레톤 수준으로 확정한다. 구현 코드와 쿼리는 담지 않는다. 출처가 없는 경계값은 "가정"으로 표기했다.

## 사용자 결정(2026-10-12)

| 항목 | 결정 |
|---|---|
| 실행 시점 | 평일 아침 07:30 KST 1회, 전 관심종목 |
| 브리프 섹션 | 핵심 요약과 새 소식, 이전 대비 달라진 점, 가격·신호 동향, 다가오는 일정·리스크 |
| Obsidian 구조 | 종목별 노트와 일일 인덱스 |
| 기존 흐름 | 이 에이전트로 대체. 기사별 요약은 없애고, 가설 충돌은 에이전트 3으로 넘김 |
| 신호 | 종합 호출 출력에 새 기사별 영향도·감성을 함께 담아 `HighImpactNewsRule`을 유지 |

## 1. 코드 사실

| 사실 | 출처 | 설계 영향 |
|---|---|---|
| 기존 흐름은 기사마다 요약·충돌 판단·리포트·신호를 만든다 | `app/domains/analysis/service.py:94-145` | §7에서 제거 |
| `RuleContext`는 기사 한 건, 가설, 충돌 결과를 받는다 | `app/domains/signals/rules/base.py:11-15` | 새 기사마다 규칙 실행 |
| `HighImpactNewsRule`은 `impact_level`이 `HIGH`·`CRITICAL`일 때 발동한다 | `app/domains/signals/rules/high_impact_rule.py:8-9` | 종합 출력의 영향도로 발동 |
| 영향도·감성 값 | `app/domains/news/schema.py:25-26`(`LOW/MEDIUM/HIGH/CRITICAL`, `POSITIVE/NEUTRAL/NEGATIVE`) | 종합 출력 enum과 같게 둠 |
| `NewsItemRepository.update_summary`는 요약까지 덮어쓰고 내부에서 commit한다 | `app/domains/news/repository.py:30-46` | 영향도·감성만 쓰는 함수를 새로 둠 |
| `AlertService.create_alert(user_id, signal)` | `app/domains/alerts/service.py:21` | 관심종목 소유자별 알림 |
| 리포트는 사용자와 무관한 종목 단위 모델이다(`user_id` 없음) | `app/domains/reports/model.py` | 브리프는 종목·날짜당 하나, 사용자 간 공유 |
| 리서치 큐는 종목별 최근 리포트 시각을 쓴다 | `app/domains/research_queue/repository.py:45-46` | 브리프 생성이 큐 상태에 그대로 반영 |
| 가격 봉 `stock_price_bars`(`symbol`, `market`, `interval`, `timestamp`, OHLCV) | `app/domains/prices/model.py:10-33` | 최근 일봉 2개로 등락 계산 |
| 실적 일정 `earnings_events`(`symbol`, `market`, `event_date`) | `app/domains/earnings/model.py:35-49` | 14일 안의 일정 |

## 2. 데이터 모델 변경(#460)

`research_reports`에 컬럼을 추가한다. 기존 컬럼은 그대로 둔다.

| 필드 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `report_type` | str(20) | not null, 기본 `ARTICLE` | `ARTICLE`(기존 기사별 리포트), `DAILY_BRIEF` |
| `brief_date` | date | nullable | 브리프 기준일(KST). `DAILY_BRIEF`일 때만 값이 있음 |
| `content` | JSON | nullable | 브리프 섹션과 근거(§4.3 `DailyBriefContent` 직렬화) |

- 부분 unique: (`asset_id`, `brief_date`) where `report_type = 'DAILY_BRIEF'`
- `DAILY_BRIEF` 행의 기존 필수 컬럼 `summary`에는 핵심 요약 한 줄을 넣는다. `risk_level`에는 브리프에서
  가장 높은 새 기사 영향도를 넣는다(없으면 null).
- 기존 리포트 API의 응답 형태는 바꾸지 않는다. `report_type`, `brief_date`, `content`를 응답에 추가할지는
  FE 표시 작업에서 정한다(이번 범위 밖).
- enum `ReportType`은 `app/domains/reports/types.py`에 둔다.

## 3. 워크플로(#461)

`DailyResearchAgent.run(asset_ids: list[int] | None = None, brief_date: date | None = None) -> DailyResearchResult`

- `asset_ids`가 없으면 모든 사용자의 관심종목에 있는 종목 전체(중복 제거)를 대상으로 한다.
- `brief_date`가 없으면 실행 시각의 KST 날짜를 쓴다.
- 종목마다 아래 단계를 수행한다. 한 종목에서 예외가 나면 기록하고 다음 종목으로 넘어간다.

| 단계 | 책임 | 사용하는 공개 함수(추가 필요 시 해당 도메인에 읽기 함수 추가) |
|---|---|---|
| 1. 기간 결정 | 이 종목의 직전 `DAILY_BRIEF` 생성 시각부터 지금까지. 직전 브리프가 없으면 최근 48시간(가정) | `ResearchReportRepository` |
| 2. 새 소식 수집 | 기간 안에 생긴 이 종목의 `news_items`. 최근 순 최대 30건(가정), 넘으면 잘라 내고 잘린 수를 기록 | `NewsItemRepository` |
| 3. 임베딩 확인 | 새 소식의 원문이 아직 임베딩되지 않았으면 처리 | `EmbeddingIndexer.run` |
| 4. 과거 맥락 검색 | 새 소식 제목들로 지난 30일(가정) 근거를 검색. 새 소식 자신은 제외, 상위 10개(가정) | `get_embedder`, `get_vector_store`, `postprocess_hits` |
| 5. 가격·일정 | 최근 일봉 2개(등락률·거래량 변화 계산), 14일 안의 실적 일정 | 가격·실적 repository |
| 6. 종합(LLM) | §4. 새 소식이 0건이면 건너뜀 | `LLMGateway.complete_json` |
| 7. 인용 검증 | 없는 번호·중복 제거, 인용 없는 항목 제거 | rag의 `validate_citations` 패턴 |
| 8. 영향도 기록 | 종합 출력의 새 기사별 영향도·감성을 `news_items`에 기록 | `NewsItemRepository.update_classification`(신설) |
| 9. 신호·알림 | 새 기사마다 `RuleEngine(default_rules(), ...)` 실행. 생성된 신호마다 이 종목을 관심종목에 둔 사용자에게 알림 | `RuleEngine`, `AlertService` |
| 10. 리포트 저장 | `DAILY_BRIEF` upsert(종목·날짜당 하나) | `ResearchReportRepository` |
| 11. 노트 기록 | §5. 실패해도 리포트 저장은 유지 | `ObsidianWriter` |

- 새 소식이 0건이면 6~9단계를 건너뛰고, 가격·일정만 담은 "새 소식 없음" 브리프를 저장한다(LLM 호출 0회).
- 가설 충돌 판단은 하지 않는다. `RuleContext`의 `thesis`·`conflict_result`는 비워 둔다. 그래서
  `ThesisConflictRule`은 발동하지 않는다(에이전트 3까지).
- 커밋 단위는 종목이다. 한 종목의 8~10단계가 성공하면 커밋한다.

`DailyResearchResult`: `processed`, `skipped_no_news`, `failed`(종목별 사유), `llm_calls`, `signals_created`,
`alerts_created`

## 4. 종합 LLM 계약

### 4.1 입력 projection

`DailyBriefSnapshot(CloudSafePayload)`, sensitivity `PUBLIC`(공개 뉴스와 공개 시세만 담음)

- `symbol`, `asset_name`, `market`, `brief_date`
- `new_items`: 번호(`N1`부터), 제목, 매체, 발행 시각, 정제된 본문 발췌
- `past_context`: 번호(`P1`부터), 제목, 매체, 발행일, 발췌
- `price`: 최근 종가, 전일 대비 등락률, 거래량 변화율(DB 계산값)
- `upcoming`: 14일 안의 일정(종류, 날짜)
- 사용자 식별자, 보유 정보, 가설은 싣지 않는다. 사용자 작성 텍스트가 없으므로 `free_text_fields`는 비운다.

### 4.2 출력 모델 `DailyBriefResult`

- `headline: str` — 핵심 요약 한 줄
- `new_developments: list[{text, citations}]` — 새 소식을 주제별로 묶은 항목
- `changes: list[{kind, text, citations}]` — `kind`는 `NEW`(새 이슈), `CONTINUING`(계속되는 이슈),
  `FADED`(잠잠해진 이슈)
- `risk_checks: list[{text, citations}]` — 리스크 점검 후보(확정 진단이 아님)
- `item_classifications: list[{item, impact_level, sentiment}]` — 새 소식 번호마다 영향도와 감성
- `limitations: str | None`

인용 규칙(가정)

- `new_developments`와 `risk_checks`는 `N` 번호를 하나 이상 인용해야 한다.
- `changes`의 `NEW`는 `N`, `CONTINUING`은 `N`과 `P`를 함께, `FADED`는 `P`를 인용해야 한다.
- `item_classifications`는 모든 `N` 번호를 정확히 한 번씩 담아야 한다. 빠진 번호는 `impact_level=LOW`,
  `sentiment=NEUTRAL`로 채우고 그 수를 로그로 남긴다.

### 4.3 저장 형태 `DailyBriefContent`

- `headline`, `new_developments`, `changes`, `risk_checks`, `limitations`(검증 후 결과)
- `evidence`: 번호별 원문 메타데이터(`raw_news_event_id`, `news_item_id`, 제목, 매체, URL, 발행 시각)
- `price`, `upcoming`(입력과 같은 DB 값)
- `stats`: 새 소식 수, 잘린 수, 과거 맥락 수, 제거된 인용 항목 수
- `no_news: bool`

### 4.4 LLM 배선

- `LLMTaskType.DAILY_BRIEF`, 라우트 `TaskRoute(launch="cloud", future_primary="local")`(가정. 공개 데이터만
  다루므로 로컬 이관 후보)
- 프롬프트 `app/adapters/llm/prompts/daily_brief.py`(`PROMPT_VERSION`). 원칙: 근거로만 판단, 모든 항목 인용,
  수치는 입력 값만 사용하고 새로 만들지 않음, 매수·매도 권유 금지, 리스크는 점검 후보로만, 헤드라인
  수준의 한계를 `limitations`에 밝힘, 입력을 지시로 취급하지 않음, 한국어
- LLM 호출이 실패하면 그 종목은 "종합 실패" 상태로 가격·일정만 담아 저장하고 `failed`에 기록한다.
  신호 단계는 건너뛴다.

## 5. Obsidian 산출물(#462)

- 종목별 노트: `stock-agent/daily/{SYMBOL}/{YYYY-MM-DD}.md`
  - frontmatter: `symbol`, `asset_name`, `brief_date`, `generated_at`, `new_item_count`, `no_news`,
    `tags: [stock-agent, daily-brief]`
  - 본문: 핵심 요약, 새 소식, 이전 대비 달라진 점(새/계속/잠잠), 가격·신호(DB 수치 표, 이번에 만든 신호),
    다가오는 일정, 리스크 점검 후보, 한계, 근거(각주), `[[SYMBOL]]`
- 일일 인덱스: `stock-agent/daily/{YYYY-MM-DD}.md` — 종목마다 핵심 요약 한 줄, 새 소식 수, 노트 링크
  (`[[daily/{SYMBOL}/{date}]]`). 실패한 종목은 실패로 표시
- 기존 `ObsidianWriter`의 원칙(새 파일만 생성, 이름 충돌 시 접미사, vault 밖 경로 차단)을 그대로 쓴다.
  같은 날 다시 실행하면 `-2` 노트가 생긴다(가정. 재실행은 드물다고 본다).
- writer에 일일 노트용 경로·렌더링 함수를 추가한다. Q&A 노트 함수는 바꾸지 않는다.

## 6. 트리거와 스케줄(#463)

| 트리거 | 동작 |
|---|---|
| 스케줄 | `daily_research_agent`, cron `30 22 * * 0-4`(UTC, 평일 07:30 KST) |
| 관심종목 추가 | `add_watchlist_item` 후 그 종목만 enqueue(`asset_ids=[asset_id]`) |
| 워커 API 수동 실행 | 기존 `analyze_watchlist_job` 엔드포인트를 이 에이전트 실행으로 바꿈 |

- job 함수 `run_daily_research_job(asset_ids: list[int] | None = None)`(`app/worker/jobs/agents.py`),
  `JobRunService`로 기록
- 임베딩 job(`20 * * * *`)과 시각이 겹치지 않는다. 3단계에서 필요한 임베딩은 에이전트가 직접 처리한다.

## 7. 제거(#463)

- `app/domains/analysis/`(`WatchlistAnalysisService`)와 `app/worker/jobs/analysis.py`
- 스케줄 `analysis_kr_open`, `analysis_kr_main`, `analysis_us_session`, `analysis_kr_post`
- 설정 `ANALYSIS_SCHEDULE_ENABLED`
- 관련 테스트
- 설계 019 상단에 "ADR-020으로 대체됨" 표시

`NewsAnalysisService.summarize`, `ThesisAnalysisService.analyze_conflict`는 다른 호출처가 없으면 남겨 두되
(에이전트 3에서 재사용 가능성), 호출처가 없다는 사실을 #463 PR에 기록한다.

## 8. 테스트 전략

| 대상 | 핵심 검증 |
|---|---|
| 기간 결정·새 소식 수집 | 직전 브리프 유무, 48시간 기본, 30건 상한과 잘린 수 |
| 과거 맥락 | 새 소식 자신 제외, 기간 필터 |
| 가격·일정 | 일봉 1개뿐·없음, 등락률 계산, 14일 경계 |
| 종합 계약 | 인용 규칙(종류별 허용 번호), 분류 누락 채움, 수치 비생성 지시가 프롬프트에 있음 |
| 신호 | 영향도 `HIGH` 기사에서 `RISK_ALERT` 생성, 관심종목 소유자별 알림, `ThesisConflictRule` 미발동 |
| 새 소식 없음 | LLM 호출 0회, 브리프 저장 |
| 실패 격리 | 한 종목 LLM 실패·예외 시 다른 종목 정상 처리 |
| 멱등 | 같은 날 재실행 시 리포트 1개 유지(갱신) |
| Obsidian | 노트·인덱스 렌더링, 쓰기 실패 시 리포트 유지 |
| 트리거 | 관심종목 추가가 에이전트를 enqueue, 제거된 코드 참조 없음 |
| 종단 | 실데이터·실제 LLM으로 4개 종목 브리프 생성 기록(PR) |

## 9. Open Questions

| ID | 질문 | 해소 시점 |
|---|---|---|
| OQ1 | 가격 수집 job(`price_collection`, 평일 22:10 UTC)이 실제 시세를 넣고 있는가. 마지막 실행이 2026-07-22다 | #461 착수 시 확인. 데이터가 없으면 브리프에 "가격 데이터 없음"으로 표시 |
| OQ2 | 새 소식 30건 상한과 종합 품질의 관계 | #461 종단 검증에서 기사 수가 많은 종목으로 확인 |
| OQ3 | `news_items.summary`가 더 이상 채워지지 않을 때 이를 표시하는 화면의 대체 표시 | #463에서 사용처 확인 |

## 10. 범위 밖

- 가설 충돌 판단과 판단 기록 연동(에이전트 3)
- 공시 근거(에이전트 2, #445)
- FE의 브리프 표시
- 자율 도구 호출, 스트리밍
