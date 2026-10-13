# Codex Handoff Task

## Source Issue

#478 — [BE] 에이전트2-2: 보고서 비교 LLM 해석·리포트·알림·실행 경로 (트래킹 #464, 에픽 #459)

## Task Summary

#477의 비교 엔진 결과를 섹션마다 LLM으로 해석하고, 인용을 검증해 `FILING_ANALYSIS` 리포트로 저장한다.
중요도 `HIGH` 변화가 있으면 `RISK_ALERT` 신호와 관심종목 소유자별 알림을 만든다. job, 주간 스케줄, 수동
스크립트를 연결한다. Obsidian 노트와 일일 브리프 연결은 #479다.

## Goal

- `FilingAnalysisAgent.run(asset_ids=None)`이 종목마다 최신·직전 연간보고서를 비교해 리포트 1건을 저장한다.
- 같은 최신 보고서(`source_ref=edgar:{접수번호}`)는 다시 분석하지 않는다.
- 종목 실패와 섹션 실패가 격리된다.
- `filing_analysis_agent` 스케줄(토 01:30 UTC)과 `scripts/run_filing_analysis.py`로 실행할 수 있다.

## Background

- 설계 정본: `docs/designs/464-filing-analysis-agent.md` §4·§5·§7. **반드시 먼저 읽는다.**
- 비교 엔진: `app/domains/agents/filing_analysis/diff.py`(`diff_sections`), `schema.py`(`SectionDiff` 등)
- 저장: `ResearchReportRepository.get_by_source_ref`·`create_filing_analysis`(commit하지 않음), `ReportType.FILING_ANALYSIS`
- 공시: `KnowledgeDocumentRepository.list_by_asset(asset_id, KnowledgeKind.FILING_SECTION, limit)`(유효일 최신순),
  문서 `metadata_`의 `accession`·`fiscal_year`·`section`·`report_date`, `source_url`, `effective_date`
- 에이전트 1 참고 구현(구조·실패 격리·commit 순서·신호/알림):
  `app/domains/agents/daily_research/service.py`, `schema.py`(`DailyBriefSnapshot` CloudSafe projection, 인용 패턴
  타입), `citations.py`(인용 검증), 프롬프트 `app/adapters/llm/prompts/daily_brief.py`, 라우트
  `app/adapters/llm/router.py`, job `app/worker/jobs/agents.py`, timeout 상수 `app/worker/jobs/timeouts.py`,
  스크립트 `scripts/run_daily_research.py`
- 신호: `SignalCreate`, `SignalRepository`, `SignalType.RISK_ALERT`(`HighImpactNewsRule`의 필드 구성을 참고),
  알림 `AlertService.create_alert(user_id, signal)`, 소유자 `WatchlistItemRepository.list_owner_ids_by_asset`
- CloudSafe projection은 `app/adapters/llm/privacy.py`의 `CloudSafePayload`를 상속하고, 사용자 작성 텍스트가
  없으므로 `free_text_fields = ()`를 명시한다(로컬 리뷰 정책상 선언 누락은 Blocking).
- 의존성 추가는 없다. `uv add`, `uv sync`, 네트워크, `git fetch`, docker 명령을 하지 않는다.

## Implementation Scope

1. **LLM 계약**(설계 §4)
   - `LLMTaskType.FILING_ANALYSIS`, 라우트 `TaskRoute(launch="cloud", future_primary="local")`. 작업 유형을 열거하는
     다른 곳(예산·캐시·테스트 등)이 있으면 함께 맞춘다.
   - `FilingDiffSnapshot(CloudSafePayload)`, sensitivity `PUBLIC`: 설계 §4.1 필드. `modified`의 새 문단에는 바뀐
     구간을 표시한다(표시 방식은 정하고 프롬프트에 설명). 입력 상한 8만 자, 넘으면 `modified`를 바뀐 글자 수가
     적은 순으로 빼고 `truncated_count` 기록.
   - 출력 `FilingSectionAnalysis`: 설계 §4.2. `citations` 원소에 `^[ARM]\d+$` 패턴.
   - 인용 검증 함수(`citations.py`): 없는 번호·형식 오류 제거, `NEW_RISK`는 `A`/`M`, `REMOVED_RISK`는 `R`/`M`만 허용,
     남은 인용이 없는 변화 제거, 제거 수를 `citation_corrections`로 반환.
   - 프롬프트 `app/adapters/llm/prompts/filing_analysis.py`(`PROMPT_VERSION="v1"`): 설계 §4.4 원칙과 `HIGH` 정의(투자
     판단에 영향을 줄 수 있는 새 위험·사업 변화에만), 문구 수정·재배치·숫자 갱신은 `LOW`, 한국어 출력 지시
     (`KOREAN_NATURAL_LANGUAGE_OUTPUT_INSTRUCTION`)
2. **저장 형태** `FilingAnalysisContent`(설계 §4.3): `old_filing`·`new_filing`(접수번호, 회계연도, 제출일, URL,
   섹션별 `knowledge_document_id`), `headline`, `sections`(섹션별 결과·`diff_stats`·`citation_corrections`·
   `truncated_count`·`failed` 사유), `evidence`(인용된 번호별 옛·새 문단 원문), `max_importance`
3. **워크플로**(`app/domains/agents/filing_analysis/service.py`, 설계 §5 단계 1~7)
   - 보고서 쌍: 문서를 `accession`으로 묶어 `effective_date` 최신 두 보고서. 2건 미만이면 `skipped_no_pair`.
     섹션이 한쪽에만 있으면 그 섹션은 `failed`("섹션 없음")로 남긴다.
   - `headline`은 `max_importance`가 가장 높은 섹션의 헤드라인을 기본으로 한다(가정, 보고).
   - 두 섹션 모두 LLM 실패면 리포트를 저장하지 않고 `failed`에 기록한다(다음 실행에서 재시도).
   - 리포트 저장 → 종목 commit → `HIGH`가 있으면 신호 1건과 소유자별 알림(실패해도 리포트는 남김).
   - 결과 `FilingAnalysisResult`: `analyzed`, `skipped_existing`, `skipped_no_pair`, `failed`, `llm_calls`,
     `signals_created`, `alerts_created`(노트 필드는 #479에서 추가)
   - 리포트 `summary`=헤드라인, `risk_level`=`max_importance`
4. **실행 경로**(설계 §7): `run_filing_analysis_job(asset_ids=None)`(`app/worker/jobs/agents.py`, 실행 기록
   `filing_analysis_agent`, 부분 실패 metadata), timeout 상수 `FILING_ANALYSIS_JOB_TIMEOUT = 1800`, 스케줄
   `filing_analysis_agent` cron `30 1 * * 6`, `scripts/run_filing_analysis.py --asset-id N`(결과 JSON 출력)
5. 설계 문서는 구현과 다르게 정한 것이 있을 때만 고친다.

## Out of Scope

- Obsidian 노트, 일일 브리프 연결(#479)
- 비교 엔진 변경(#477에서 완료). 필요한 버그가 보이면 보고만 한다.
- DART, 실적 분석

## Protected Files

없음.

## Test Requirements

- projection: `free_text_fields == ()`, sensitivity, 입력 상한과 잘림 순서
- 인용 검증: 없는 번호, 형식 오류, 종류별 허용 접두사, 인용이 모두 사라진 변화 제거, 보정 수
- 워크플로(LLM은 fake gateway): 정상 분석 저장 필드, 쌍 없음, 중복 건너뜀(LLM 미호출), 섹션 하나 실패, 두 섹션
  모두 실패 시 미저장, `HIGH`일 때만 신호·알림(소유자 수만큼), 신호 단계 실패해도 리포트 유지, 종목 실패 격리
- job: 성공·부분 실패·예외 기록, 스케줄 cron·timeout
- 프롬프트 스키마가 `FilingSectionAnalysis` JSON Schema를 담음

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
uv run alembic heads
```

## ADR Need

불필요(ADR-020 범위).

## Failure Record Need

불필요.

## Risk Level

Medium — 클라우드 LLM 호출 추가(공개 공시만 전송), 신호·알림 생성.

## Expected Output

- 현재 브랜치 `feat/478-filing-analysis-agent`에서 작업한다. 새 브랜치를 만들지 않는다.
- 커밋이 샌드박스에서 막히면 미커밋 상태로 두고 보고한다. push와 PR 생성은 하지 않는다.
- 최종 보고: 변경 파일 목록, 가정(헤드라인 선택, 바뀐 구간 표시 방식 등), 검증 결과

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
