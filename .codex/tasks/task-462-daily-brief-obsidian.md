# Codex Handoff Task

## Source Issue

#462 — [BE] 에이전트1: 일일 브리프 Obsidian 노트·인덱스 (에픽 #459)

## Task Summary

일일 리서치 에이전트가 종목별 일일 노트와 일일 인덱스 노트를 Obsidian vault에 남기게 한다. 기존
`ObsidianWriter`의 안전 원칙(새 파일만 생성, 이름 충돌 시 접미사, vault 밖 경로 차단)을 그대로 쓴다.
노트 쓰기 실패는 브리프 저장과 신호 생성에 영향을 주지 않는다.

## Goal

- 종목마다 `stock-agent/daily/{SYMBOL}/{YYYY-MM-DD}.md`가 생긴다.
- 전 종목 실행(`asset_ids=None`)이 끝나면 `stock-agent/daily/{YYYY-MM-DD}.md` 인덱스가 생긴다. 종목 단위
  실행(`asset_ids` 지정)은 인덱스를 쓰지 않는다.
- vault가 설정되지 않았거나 쓰기에 실패해도 에이전트 실행 결과는 그대로이고, 실패만 결과에 기록된다.

## Background

- 설계 정본: `docs/designs/459-daily-research-agent.md` §5. **반드시 먼저 읽는다.**
- 설계와 달라진 점: 인덱스는 전 종목 실행에서만 쓴다. 종목 단위 실행(관심종목 추가 트리거)마다 인덱스를
  쓰면 같은 날 `-2`, `-3` 인덱스가 쌓이기 때문이다. 같은 날 전 종목 실행을 다시 하면 `-2` 인덱스가 생기는
  것은 허용한다(재실행은 드묾).
- 기존 writer: `app/adapters/obsidian/writer.py`(`ObsidianWriter.write_research_note`, `render_research_note`,
  `_validate_path`, 배타적 생성 루프, `Asia/Seoul` 날짜, frontmatter JSON 스칼라 직렬화(`ensure_ascii=False`),
  각주 인용 형식). factory `get_obsidian_writer()`(`app/adapters/factory.py:246`)
- 에이전트: `app/domains/agents/daily_research/service.py`(`DailyResearchAgent`), 저장 형태
  `DailyBriefContent`(`schema.py`)
- 신호는 브리프 저장 뒤에 만들어진다(#461 단계 순서). 노트의 "가격·신호" 섹션에 이번 실행에서 그 종목에
  생긴 신호를 넣으려면 노트 쓰기를 신호 단계 뒤에 둔다.
- 의존성 추가는 없다. `uv add`, `uv sync`, 네트워크, `git fetch`, docker 명령을 하지 않는다.

## Implementation Scope

1. **writer 확장**(`app/adapters/obsidian/writer.py`). 기존 Q&A 노트 함수는 바꾸지 않는다.
   - 값 객체 `DailyBriefNote`: `symbol`, `asset_name`, `brief_date`, `generated_at`, `content: DailyBriefContent`,
     `signals: list[DailySignalLine]`(`signal_type`, `score`, `reason`)
   - `render_daily_brief_note(note) -> str`
     - frontmatter: `symbol`, `asset_name`, `brief_date`, `generated_at`, `new_item_count`, `no_news`,
       `price_stale`, `tags: [stock-agent, daily-brief]`
     - 본문 순서: `# {asset_name}({symbol}) 일일 브리프 {brief_date}`, `[[{SYMBOL}]]`, `## 핵심 요약`,
       `## 새 소식`(항목과 각주), `## 이전 대비 달라진 점`(새 이슈 / 계속되는 이슈 / 잠잠해진 이슈 소제목),
       `## 가격·신호`(DB 값 표: 기준일, 종가, 등락률, 거래량 변화. `stale`이면 "오래된 데이터" 표시. 이번 실행
       신호 목록), `## 다가오는 일정`, `## 리스크 점검 후보`, `## 한계`, `## 근거`(각주 정의 — 새 소식과 과거
       맥락 모두), 끝에 생성 안내 한 줄("이 노트는 stock-agent가 생성했습니다. 매수·매도 권유가 아닙니다.")
     - 비어 있는 섹션은 생략한다. `no_news`면 "새 소식 없음"과 가격·일정만 쓴다.
     - 인용 번호(`N1`, `P1`)는 각주 `[^N1]`, `[^P1]`로 쓴다. 링크 텍스트의 `[`·`]`는 이스케이프한다(Q&A 노트와 같음).
   - 값 객체 `DailyIndexEntry`: `symbol`, `asset_name`, `headline`, `new_item_count`, `note_path`(vault 상대),
     `failed_reason: str | None`
   - `render_daily_index(brief_date, entries) -> str` — frontmatter(`brief_date`, `asset_count`, `failed_count`,
     `tags: [stock-agent, daily-index]`), 종목마다 한 줄(`- [[{note_path 확장자 제외}|{SYMBOL}]] {headline} (새 소식 N건)`),
     실패 종목은 실패 사유 한 줄
   - `ObsidianWriter.write_daily_brief_note(note) -> Path`,
     `ObsidianWriter.write_daily_index(brief_date, entries) -> Path` — 기존 배타적 생성·경로 검증 루프를 공용
     내부 함수로 뽑아 재사용한다(동작 변경 없음). 경로의 날짜는 `brief_date`를 그대로 쓴다.
2. **에이전트 연결**(`service.py`)
   - `DailyResearchAgent`에 `obsidian_writer: ObsidianWriter | None = None` 인자를 추가한다.
   - 종목 처리 마지막(신호 단계 뒤)에 종목 노트를 쓴다. 신호 단계가 실패해도 노트는 쓴다.
   - `asset_ids is None`인 실행이 끝나면 인덱스를 쓴다. 처리 성공·실패 종목을 모두 담는다.
   - `OSError`·`ValueError`는 잡아서 `DailyResearchResult.note_failures`(종목 id 또는 `"index"` → 사유)에
     기록하고 계속한다. 성공한 노트 경로는 `notes_written`(수)로 집계한다.
   - writer가 `None`이면 노트를 쓰지 않고 실패로 기록하지도 않는다.
3. 수동 실행 스크립트(`scripts/run_daily_research.py`)가 `get_obsidian_writer()`를 넘기도록 한다.
4. 설계 459 §5에 "인덱스는 전 종목 실행에서만 쓴다"를 반영한다. 또 §3에 PR #468 리뷰 S2(새 소식은 수집
   시각 `news_items.created_at` 기준, 과거 맥락은 발행 시각 `published_at` 기준이라는 차이와 그 이유)를 한 줄
   추가한다.

## Out of Scope

- 스케줄·트리거·기존 흐름 제거(#463)
- Q&A 노트 형식 변경
- 노트 수정·덮어쓰기

## Protected Files

없음.

## Test Requirements

- 렌더링: 섹션 순서, 빈 섹션 생략, `no_news`, `stale` 표시, 각주(`N`·`P`), 링크 이스케이프, frontmatter 한글·따옴표
- 인덱스 렌더링: 성공·실패 종목, wikilink 경로
- writer(`tmp_path`): 경로 규칙, 이름 충돌 `-2`와 기존 파일 불변, vault 밖 경로 차단
- 에이전트: 전 종목 실행 시 종목 노트 N개와 인덱스 1개, 종목 단위 실행 시 인덱스 없음, 쓰기 실패가
  `note_failures`에 기록되고 브리프·신호는 정상, writer 없음이면 노트 0개·실패 0개, 신호가 노트에 나옴
- 기존 Q&A 노트 테스트가 그대로 통과

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

## ADR Need

불필요.

## Failure Record Need

불필요.

## Risk Level

Medium — 파일 시스템 쓰기 경로 추가. 기존 안전 원칙을 공용 함수로 재사용한다.

## Expected Output

- 현재 브랜치 `feat/462-daily-brief-obsidian`에서 작업한다. 새 브랜치를 만들지 않는다.
- 커밋이 샌드박스에서 막히면 미커밋 상태로 두고 보고한다. push와 PR 생성은 하지 않는다.
- 최종 보고: 변경 파일 목록, 가정, 검증 결과

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
