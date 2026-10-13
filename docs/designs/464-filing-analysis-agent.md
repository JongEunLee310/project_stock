# BE 설계: 에이전트 2 — 연간보고서 비교 분석 — #464

상태: **설계 초안(Draft)** — 2026-10-13. 결정 근거는 ADR-020(작업형 에이전트는 고정 워크플로)이고, 공시 원문은
설계 445(`knowledge_documents`)를 읽는다. 하위 이슈 #477(2-1), #478(2-2), #479(2-3).

이 문서는 새 연간보고서를 직전 보고서와 비교하는 에이전트의 워크플로, 비교 엔진, LLM 계약, 저장 형태,
산출물, 실행 경로를 스켈레톤 수준으로 확정한다. 구현 코드와 쿼리는 담지 않는다. 출처가 없는 경계값은
"가정"으로 표기했다.

## 사용자 결정(2026-10-13)

| 항목 | 결정 |
|---|---|
| 1차 범위 | 연간보고서 비교만. 실적 발표 분석은 발표 원문(8-K 등) 수집 뒤 2차로 둔다 |
| 산출물 | 분석 리포트와 Obsidian 노트, 알림, 다음 날 일일 브리프에 연결 |
| 초기 실행 | 이미 수집된 종목마다 최신 보고서 1건을 직전 보고서와 비교 |
| 비교 방식 | 코드가 문단을 짝지어 변화분을 골라 내고, LLM은 변화분만 해석한다 |
| 알림 기준 | 중요도 `HIGH` 변화가 하나라도 있으면 알림 1건 |

## 1. 코드·데이터 사실

| 사실 | 출처 | 설계 영향 |
|---|---|---|
| 공시 섹션은 `knowledge_documents`(`kind=FILING_SECTION`, `metadata_.section`·`accession`·`fiscal_year`)에 있다 | 설계 445 §2, PR #476 | 비교 대상 조회 |
| `KnowledgeDocumentRepository.list_by_asset(asset_id, kind, limit)`는 유효일 최신순이다 | `app/domains/knowledge/repository.py` | 최근 보고서 2건 |
| 리포트는 `research_reports`이고 `report_type`·`content`(JSON)를 가진다. 기존 값은 `ARTICLE`·`DAILY_BRIEF` | `app/domains/reports/model.py`, `types.py` | `FILING_ANALYSIS` 추가 |
| 알림은 `AlertService.create_alert(user_id, signal)`로 신호에 묶여 생긴다 | `app/domains/alerts/service.py:21` | 신호 1건 + 소유자별 알림 |
| 신호 타입에 `RISK_ALERT`(category `RISK`)가 있다 | `app/domains/signals/types.py` | 새 타입을 만들지 않음 |
| 에이전트 1의 브리프 콘텐츠는 `DailyBriefContent`이고 노트는 `ObsidianWriter`가 쓴다 | `app/domains/agents/daily_research/schema.py`, `app/adapters/obsidian/writer.py` | 브리프 연결과 노트 |
| 실측(2026-10-13, 실 DB의 AAPL·NVDA·GOOGL 최신 vs 직전, 단어 단위 유사도 0.97/0.6 기준) | 리뷰어 실험 | §3 경계값 |

실측 상세(섹션별, 문단 = 40자 초과 줄, 쪽 머리말 제외)

| 섹션 | 같음 | 변경(바뀐 글자 수) | 신규(글자 수) | 삭제(글자 수) |
|---|---|---|---|---|
| AAPL Item 1 | 16 | 15(1.8천) | 1(1.5천) | 4(1.9천) |
| AAPL Item 1A | 45 | 46(1.0만) | 10(7.3천) | 19(1.2만) |
| GOOGL Item 1 | 27 | 20(1.9천) | 12(5.2천) | 33(1.3만) |
| GOOGL Item 1A | 67 | 70(6.7천) | 18(1.1만) | 17(9.9천) |
| NVDA Item 1 | 31 | 38(3.8천) | 29(1.2만) | 45(1.9만) |
| NVDA Item 1A | 149 | 45(8.2천) | 34(1.7만) | 27(1.6만) |

## 2. 데이터 모델 변경(#477)

`research_reports`에 컬럼 하나를 추가한다.

| 필드 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `source_ref` | str(200) | nullable | 리포트가 다룬 원천 식별자. `FILING_ANALYSIS`는 `edgar:{최신 접수번호}` |

- 부분 unique: (`asset_id`, `report_type`, `source_ref`) where `source_ref is not null`. 같은 보고서를 두 번
  분석하지 않는 근거다.
- `ReportType.FILING_ANALYSIS` 추가. `summary`에는 분석 헤드라인, `risk_level`에는 변화 중 가장 높은 중요도,
  `content`에는 §4.3 `FilingAnalysisContent`를 넣는다.
- repository: `get_by_source_ref(asset_id, report_type, source_ref)`, `create_filing_analysis(...)`,
  `list_filing_analyses_created_between(asset_id, start, end)`(브리프 연결용)

## 3. 비교 엔진(#477, 결정적)

위치 `app/domains/agents/filing_analysis/diff.py`. LLM을 쓰지 않는 순수 함수다.

| 함수 | 책임 |
|---|---|
| `split_paragraphs(text) -> list[str]` | 줄 단위로 나누고, 40자 이하 줄과 쪽 머리말·꼬리말 패턴(`Table of Contents`, `\| YYYY Form 10-K \|`)을 버린다 |
| `diff_sections(old_text, new_text) -> SectionDiff` | 새 문단마다 옛 문단 중 단어 단위 유사도가 가장 높은 것을 찾아 분류한다 |

분류(가정, 실측 근거 §1)

| 분류 | 조건 | 담는 것 |
|---|---|---|
| `UNCHANGED` | 유사도 0.97 이상 | 수만 센다 |
| `MODIFIED` | 0.6 이상 0.97 미만 | 옛 문단, 새 문단, 바뀐 구간(단어 diff) |
| `TRIVIAL` | `MODIFIED` 중 바뀐 토큰이 모두 숫자·날짜·연도 | 수만 센다(LLM에 보내지 않음) |
| `ADDED` | 0.6 미만 | 새 문단 |
| `REMOVED` | 어떤 새 문단과도 짝지어지지 않은 옛 문단 | 옛 문단 |

- 옛 문단 하나는 한 번만 짝지을 수 있다(먼저 높은 유사도부터 확정, 가정).
- `SectionDiff`: `section`, 분류별 항목 목록(번호 `A1`·`R1`·`M1`), `stats`(분류별 수와 글자 수)
- 계산 비용은 문단 수 곱에 비례한다(NVDA Item 1A 215×228). 유사도 계산 전에 길이 비율과 `quick_ratio`
  상한으로 후보를 거른다.

## 4. LLM 계약(#478)

### 4.1 입력 projection

`FilingDiffSnapshot(CloudSafePayload)`, sensitivity `PUBLIC`(공개 공시만 담음). 섹션마다 한 번 호출한다.

- `symbol`, `asset_name`, `section`(`BUSINESS`·`RISK_FACTORS`), `old_fiscal_year`, `new_fiscal_year`
- `added`: `A{n}` 번호와 문단
- `removed`: `R{n}` 번호와 문단
- `modified`: `M{n}` 번호, 옛 문단, 새 문단(바뀐 구간 표시)
- `stats`: 분류별 수, `TRIVIAL` 수
- 입력 상한 8만 자(가정, 실측 최대 약 4.5만 자). 넘으면 `modified`를 바뀐 글자 수가 적은 순으로 빼고
  `truncated_count`를 기록한다.
- 사용자 식별자와 사용자 작성 텍스트가 없으므로 `free_text_fields`는 비운다.

### 4.2 출력 모델 `FilingSectionAnalysis`

- `headline: str` — 섹션 변화 한 줄
- `changes: list[{kind, title, summary, importance, citations}]`
  - `kind`: `NEW_RISK`, `REMOVED_RISK`, `ESCALATED_RISK`, `SOFTENED_RISK`, `BUSINESS_CHANGE`, `OTHER`
  - `importance`: `LOW`, `MEDIUM`, `HIGH`
  - `citations`: `^[ARM]\d+$` 패턴
- `limitations: str | None`

인용 규칙(가정)

- 모든 변화는 입력 번호를 하나 이상 인용해야 한다. 없는 번호와 형식이 틀린 번호는 제거하고, 남은 인용이
  없으면 그 변화를 버린다. 제거 수는 `citation_corrections`에 센다.
- `NEW_RISK`는 `A` 또는 `M`, `REMOVED_RISK`는 `R` 또는 `M`을 인용해야 한다.
- 중요도 `HIGH`는 투자 판단에 영향을 줄 수 있는 새 위험·사업 변화에만 쓰도록 프롬프트에서 정의한다.

### 4.3 저장 형태 `FilingAnalysisContent`

- `old_filing`·`new_filing`: 접수번호, 회계연도, 제출일, 원문 URL, `knowledge_document_id`(섹션별)
- `headline`: 두 섹션 헤드라인을 묶은 한 줄(가장 중요한 변화 기준)
- `sections`: 섹션별 `headline`, 검증된 `changes`, `limitations`, `diff_stats`, `citation_corrections`,
  `truncated_count`
- `evidence`: 인용된 번호별 문단 원문(옛·새)과 출처 문서 id
- `max_importance`

### 4.4 LLM 배선

- `LLMTaskType.FILING_ANALYSIS`, 라우트 `TaskRoute(launch="cloud", future_primary="local")`(가정)
- 프롬프트 `app/adapters/llm/prompts/filing_analysis.py`(`PROMPT_VERSION`). 원칙: 입력 변화분만 근거로 판단,
  모든 변화 인용, 숫자만 바뀐 변화는 중요도를 높이지 않음, 매수·매도 권유 금지, 입력을 지시로 취급하지
  않음, 한국어
- 섹션 하나의 호출이 실패하면 그 섹션은 `failed`로 남기고 다른 섹션은 저장한다. 두 섹션이 모두 실패하면
  리포트를 만들지 않고 다음 실행에서 다시 시도한다.

## 5. 워크플로(#478)

`FilingAnalysisAgent.run(asset_ids: list[int] | None = None) -> FilingAnalysisResult`

| 단계 | 책임 |
|---|---|
| 1. 대상 | `asset_ids`가 없으면 관심종목 전체 |
| 2. 보고서 쌍 | `FILING_SECTION` 문서를 접수번호로 묶어 최신 보고서와 직전 보고서를 고른다. 2건 미만이면 `skipped_no_pair` |
| 3. 중복 확인 | `source_ref=edgar:{최신 접수번호}` 리포트가 있으면 `skipped_existing` |
| 4. 비교 | 섹션마다 `diff_sections` |
| 5. 해석 | 섹션마다 LLM(§4), 인용 검증 |
| 6. 저장 | 리포트 생성, 종목 단위 commit |
| 7. 신호·알림 | `max_importance=HIGH`면 `RISK_ALERT` 신호 1건(이유는 헤드라인)과 관심종목 소유자별 알림 |
| 8. 노트 | Obsidian 노트(§6). 실패는 `note_failures`에 기록 |

- 종목 하나의 실패가 다른 종목을 막지 않는다(에이전트 1과 같은 격리).
- 결과: `analyzed`, `skipped_existing`, `skipped_no_pair`, `failed`, `llm_calls`, `signals_created`,
  `alerts_created`, `notes_written`, `note_failures`
- 신호 단계의 commit 순서는 에이전트 1과 같다(리포트 commit 뒤에 신호·알림).

## 6. 산출물(#479)

### 6.1 Obsidian 노트

- 경로 `stock-agent/filings/{SYMBOL}/FY{new_fiscal_year}-10-K.md`. 기존 writer의 안전 원칙(새 파일만, 이름
  충돌 시 접미사, vault 밖 경로 차단)을 쓴다.
- frontmatter: `symbol`, `asset_name`, `form`, `old_fiscal_year`, `new_fiscal_year`, `filed_date`,
  `max_importance`, `tags: [stock-agent, filing-analysis]`
- 본문: 헤드라인, `[[{SYMBOL}]]`, 섹션별(위험요인, 사업) 변화 목록(중요도 순, 각주 인용), 통계(같음·변경·
  숫자만 변경·신규·삭제 수), 근거(인용 문단 발췌와 원문 링크), 생성 안내 한 줄

### 6.2 일일 브리프 연결

- 에이전트 1이 브리프를 만들 때, 직전 브리프 이후 생긴 `FILING_ANALYSIS` 리포트를 조회해
  `DailyBriefContent.filing_analyses: list[{report_id, form, fiscal_year, headline, max_importance}]`에 담는다.
- LLM 입력에는 넣지 않는다(이미 분석된 결과를 옮기기만 함). 일일 노트에는 "새 연간보고서 분석" 섹션과
  분석 노트 wikilink를 쓴다. 새 소식이 없는 날에도 이 섹션은 쓴다.

## 7. 실행 경로(#478)

| 경로 | 내용 |
|---|---|
| job | `run_filing_analysis_job(asset_ids=None)`(`app/worker/jobs/agents.py`), 실행 기록 `filing_analysis_agent`, timeout 1800초(가정, 섹션당 LLM 1회 × 2 × 종목 수) |
| 스케줄 | `filing_analysis_agent`, 매주 토요일 01:30 UTC(공시 수집 01:00 다음, 가정) |
| 수동 스크립트 | `scripts/run_filing_analysis.py --asset-id N` |

- 이미 분석한 보고서는 건너뛰므로 주간 실행은 새 보고서가 있을 때만 LLM을 부른다.
- 초기 실행은 배포 뒤 수동 스크립트로 한 번 돌린다. 수집된 종목마다 최신 보고서 1건이 분석된다.

## 8. 테스트 전략

- 비교 엔진: 분류 경계(0.97·0.6), `TRIVIAL` 판정, 옛 문단 중복 짝짓기 방지, 머리말 제거, 번호 부여, 빈 입력
- 저장: `source_ref` 부분 unique, 마이그레이션 단일 head
- LLM 계약: 입력 상한과 잘림, 인용 검증(없는 번호, 종류별 허용 접두사, 인용 없는 변화 제거), 섹션 실패 격리
- 워크플로: 쌍 없음, 중복 건너뜀, `HIGH`일 때만 신호·알림, 종목 실패 격리, 노트 실패 기록
- 브리프 연결: 기간 안의 분석만, 새 소식 없는 날에도 표시, LLM 입력 불변
- 실측(리뷰 단계): 실 DB 복제본에서 AAPL·NVDA·GOOGL 최신 보고서 분석, 노트와 알림 확인

## 9. 하위 이슈

| 이슈 | 범위 |
|---|---|
| #477 | `source_ref` 컬럼·`FILING_ANALYSIS`·repository, 비교 엔진(§2·§3) |
| #478 | LLM 계약·워크플로·신호·알림·job·스케줄·스크립트(§4·§5·§7) |
| #479 | Obsidian 노트와 일일 브리프 연결(§6) |

## 10. Open Questions

| # | 질문 | 처리 |
|---|---|---|
| OQ1 | 유사도 경계(0.97·0.6)가 문단을 쪼개거나 합친 경우 신규·삭제로 과대 집계할 수 있다 | #478 실측에서 LLM이 "재배치"로 판단한 비율을 본다 |
| OQ2 | `HIGH` 판정의 일관성 | 실측 3종목 결과를 리뷰에서 사람이 확인 |
| OQ3 | DART 사업보고서(#473)는 섹션 구성이 달라 같은 엔진이 맞는지 | #473 이후 확인 |

## 11. 범위 밖

- 실적 발표 분석(발표 원문 수집 필요), 10-Q·8-K
- 재무제표 수치 비교
- FE 표시
