# Codex Handoff Task

## Source Issue

#479 — [BE] 에이전트2-3: 보고서 분석 Obsidian 노트와 일일 브리프 연결 (트래킹 #464, 에픽 #459)

## Task Summary

연간보고서 비교 분석(#478) 결과를 Obsidian 노트로 남기고, 다음 일일 브리프(에이전트 1)에 "새 연간보고서
분석" 항목으로 연결한다. 브리프 연결은 저장된 분석을 옮기기만 하며 LLM 입력은 바꾸지 않는다.

## Goal

- 분석마다 `stock-agent/filings/{SYMBOL}/FY{new_fiscal_year}-10-K.md` 노트가 생긴다.
- 일일 브리프의 `content.filing_analyses`에 직전 브리프 이후 생긴 분석이 담기고, 일일 노트에 섹션과
  wikilink가 나온다. 새 소식이 없는 날에도 나온다.
- 노트 쓰기 실패는 리포트·신호·알림에 영향을 주지 않는다.

## Background

- 설계 정본: `docs/designs/464-filing-analysis-agent.md` §6. **반드시 먼저 읽는다.**
- Writer: `app/adapters/obsidian/writer.py` — `DailyBriefNote`·`render_daily_brief_note`·`write_daily_brief_note`,
  공용 배타적 생성 `_write_new`(새 파일만, 이름 충돌 시 `-2`, vault 밖 차단), frontmatter 직렬화, 각주 형식,
  링크 텍스트 이스케이프. factory `get_obsidian_writer()`
- 에이전트 2: `app/domains/agents/filing_analysis/service.py`(`FilingAnalysisAgent`, 리포트 commit 뒤 신호 단계),
  `schema.py`(`FilingAnalysisContent`, `FilingAnalysisResult`), job `app/worker/jobs/agents.py`
  (`run_filing_analysis_job`), 스크립트 `scripts/run_filing_analysis.py`
- 에이전트 1: `app/domains/agents/daily_research/service.py`(`_run_asset`의 기간 `start` = 직전 브리프
  `created_at` 또는 48시간 전, 노트 쓰기), `schema.py`(`DailyBriefContent`)
- 리포트 repository: `list_filing_analyses_created_between(asset_id, start, end)`(#477)
- 에이전트 1이 노트를 다는 방식(#462, `notes_written`·`note_failures`)을 그대로 따른다.
- 의존성 추가는 없다. `uv add`, `uv sync`, 네트워크, `git fetch`, docker 명령을 하지 않는다.

## Implementation Scope

1. **분석 노트**(설계 §6.1)
   - 값 객체 `FilingAnalysisNote`(`symbol`, `asset_name`, `generated_at`, `content: FilingAnalysisContent`)
   - `render_filing_analysis_note(note) -> str`
     - frontmatter: `symbol`, `asset_name`, `form`(`10-K`), `old_fiscal_year`, `new_fiscal_year`, `filed_date`,
       `max_importance`, `tags: [stock-agent, filing-analysis]`
     - 본문: `# {asset_name}({symbol}) 10-K FY{new} 비교 분석`, `[[{SYMBOL}]]`, 헤드라인, 섹션별(`## 위험요인 변화`,
       `## 사업 변화`) 변화 목록(중요도 `HIGH`→`MEDIUM`→`LOW` 순, 종류 라벨, 각주 인용), 섹션 실패 사유, `## 통계`
       (같음·숫자만 변경·변경·신규·삭제 수, 잘린 수), `## 근거`(인용 번호별 각주 정의: 섹션별로 번호가 겹치므로
       각주 이름에 섹션 접두사를 붙인다. 예: `[^RF-A1]`, `[^BIZ-M3]`. 발췌는 새 문단 우선, 없으면 옛 문단, 각
       500자 상한(가정), 원문 링크), 끝에 생성 안내 한 줄("이 노트는 stock-agent가 생성했습니다. 매수·매도 권유가
       아닙니다.")
   - `ObsidianWriter.write_filing_analysis_note(note) -> Path` — `_write_new` 재사용, 경로 설계 §6.1
   - `FilingAnalysisAgent(db, gateway, obsidian_writer=None)`: 리포트 저장·신호 단계 뒤에 노트를 쓴다(신호 실패해도
     씀). `OSError`·`ValueError`는 `note_failures`에 기록. `FilingAnalysisResult`에 `notes_written`, `note_failures`
     추가. job과 스크립트가 `get_obsidian_writer()`를 넘긴다.
2. **일일 브리프 연결**(설계 §6.2)
   - `BriefFilingAnalysis`(`report_id`, `symbol`, `form`, `fiscal_year`, `headline`, `max_importance`, `note_path`)와
     `DailyBriefContent.filing_analyses: list[BriefFilingAnalysis] = []`(기존 저장 JSON과 호환되게 기본값)
   - `_run_asset`에서 `list_filing_analyses_created_between(asset_id, start, generated_at)`로 조회해 담는다. LLM
     입력(`DailyBriefSnapshot`)은 바꾸지 않는다. 새 소식이 없는 경로에도 담는다.
   - `note_path`는 vault 상대 경로 `{export_dir}/filings/{SYMBOL}/FY{year}-10-K`(확장자 제외)로 계산한다. 이름 충돌
     접미사는 반영하지 않는다(가정, 보고).
   - 일일 노트: `## 새 연간보고서 분석` 섹션을 `## 가격·신호` 앞에 둔다. 항목마다 `- [[{note_path}|{form} FY{year}]]
     {headline} (중요도 {max_importance})`. 비어 있으면 섹션을 생략한다. `no_news` 노트에도 나온다.
3. 설계 문서는 구현과 다르게 정한 것이 있을 때만 고친다.

## Out of Scope

- 분석 로직·프롬프트·알림 기준 변경
- 일일 인덱스 노트 변경
- FE 표시

## Protected Files

없음.

## Test Requirements

- 분석 노트 렌더링: frontmatter 한글·따옴표, 섹션 순서, 중요도 정렬, 섹션 실패 표시, 각주 섹션 접두사, 발췌
  상한, 링크 이스케이프
- writer(`tmp_path`): 경로, 이름 충돌 `-2`와 기존 파일 불변, vault 밖 차단
- 에이전트 2: 노트 작성 수, 쓰기 실패가 `note_failures`에 기록되고 리포트·신호 정상, writer 없음이면 0·0, 건너뛴
  종목은 노트 없음
- 브리프 연결: 기간 안 분석만(경계 포함), 새 소식 없는 날에도 담김, LLM 스냅샷 불변, 기존 브리프 JSON(필드 없음)
  역직렬화, 일일 노트 섹션 위치·생략
- 기존 Q&A·일일 노트 테스트 그대로 통과

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
uv run alembic heads
```

## ADR Need

불필요.

## Failure Record Need

불필요.

## Risk Level

Low — 파일 쓰기(기존 안전 원칙 재사용)와 브리프 콘텐츠 필드 추가.

## Expected Output

- 현재 브랜치 `feat/479-filing-note-brief-link`에서 작업한다. 새 브랜치를 만들지 않는다.
- 커밋이 샌드박스에서 막히면 미커밋 상태로 두고 보고한다. push와 PR 생성은 하지 않는다.
- 최종 보고: 변경 파일 목록, 가정, 검증 결과

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
