# Codex Handoff Task

## Source Issue

#461 보정 — 실데이터 종단 검증에서 드러난 브리프 품질 문제 3건 (에픽 #459)

## Task Summary

orchestrator가 2026-10-12 실제 DB 복제본(관심종목 4개, 임베딩 2,803청크), 실제 Ollama, 실제 LLM으로
`DailyResearchAgent`를 돌려 세 가지 문제를 확인했다. 모두 `app/domains/agents/daily_research/`와 관련
어댑터 안에서 고친다.

## Background — 실측 결과

1. **오래된 가격을 현재 시세처럼 서술한다.** 마지막 일봉이 2026-07-22인데(로컬 스택이 그 뒤로 꺼져
   있었음), 10-12 브리프 헤드라인이 "종가 342.09, 등락률 -1.46%"처럼 최근 시세로 서술했다.
   `BriefPrice`에 기준일이 없기 때문이다.
2. **LLM 출력의 번호 형식이 실행마다 흔들린다.** 첫 실행의 NVDA는 `citation_corrections=60`이었다(새 기사
   30건의 분류가 전부 누락·무효로 처리돼 `LOW`·`NEUTRAL`로 채워지고 신호가 생기지 않음). 같은 입력으로
   다시 돌린 실행에서는 `item`이 `N1`~`N30` 형식으로 정상이었다. 출력 스키마가 번호 형식을 강제하지 않는다.
3. **"과거 맥락"에 이번 기간의 새 기사가 섞인다.** 48시간 창 안의 새 기사가 약 100건인데 최근 30건만 새
   소식으로 쓰고, 잘린 나머지 70여 건이 과거 맥락 검색에 그대로 걸렸다(`published_after`만 걸고, 제외는
   상위 30건의 원문 id만 함). 과거 맥락은 기간 시작 이전 근거여야 한다.

## Implementation Scope

1. **가격 기준일과 신선도**
   - `BriefPrice`에 `as_of: date`(최근 일봉 날짜)와 `stale: bool`을 추가한다. `stale`은 `as_of`가 `brief_date`보다
     4일(가정, 주말·휴장 고려) 넘게 이전이면 참이다.
   - 스냅샷에도 같은 필드를 싣는다. 프롬프트에 "가격은 `as_of` 기준이며, `stale`이면 최근 시세로 서술하지
     말고 오래된 데이터임을 밝힌다"를 추가한다(`PROMPT_VERSION`을 `v2`로).
2. **번호 형식 강제**
   - `DailyBriefResult`의 `item_classifications[].item`은 `^N\d+$`, `new_developments`·`risk_checks`의
     `citations` 원소는 `^N\d+$`, `changes`의 `citations` 원소는 `^[NP]\d+$` 패턴을 JSON Schema에 드러내도록
     pydantic 제약을 건다(구조화 출력이 형식을 지키도록 유도).
   - 형식이 맞지 않는 값이 오면 검증에서 제거하는 기존 동작은 유지한다. 단, 보정 수가 새 기사 수 이상이면
     warning 로그로 남긴다.
3. **과거 맥락은 기간 시작 이전으로 한정**
   - `ChunkFilter`에 `published_before: datetime | None = None`을 추가하고 `PgVectorStore`·
     `InMemoryVectorStore`에 구현한다(저장소 중립 값, ADR-018 R4). 공용 시나리오 테스트에 추가한다.
   - 과거 맥락 검색은 `published_after = 기간 시작 - 30일`, `published_before = 기간 시작`으로 건다. 기간 시작은
     설계 459 §3의 시작 시각(직전 브리프 `created_at` 또는 48시간 전)이다.
   - 새 소식 원문 id를 결과에서 빼는 처리는 그대로 둔다(발행 시각이 없는 원문 대비).
4. 설계 459 §4.1·§4.2·§3(과거 맥락 기간)을 위 내용으로 고친다.

## Out of Scope

- 가격 수집 job 자체, 새 소식 상한(30건) 변경, Obsidian·트리거

## Protected Files

없음.

## Test Requirements

- 가격: `as_of` 값, `stale` 경계(4일), 봉 0·1개일 때 `price=None` 유지, 프롬프트에 신선도 지시가 있음
- 스키마: 생성된 JSON Schema에 패턴이 있음, 잘못된 형식이 오면 제거되고 보정 수가 기록됨
- 과거 맥락: 기간 시작 이후에 발행된 근거(잘린 새 기사 포함)가 과거 맥락에 들어가지 않음, 기간 시작 이전
  30일 안의 근거는 들어감(pgvector `postgres` 마커 테스트 포함)
- 기존 테스트의 검증 강도를 낮추지 않는다.

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

## ADR Need

불필요.

## Failure Record Need

불필요. 머지 전 검증에서 발견해 같은 PR에서 고친다.

## Risk Level

Medium — 저장소 필터 인터페이스 확장(두 구현체)과 LLM 계약 변경.

## Expected Output

- 현재 브랜치 `feat/461-daily-research-workflow`에서 작업한다. 새 브랜치를 만들지 않는다.
- 이전 작업은 orchestrator가 커밋했다. 커밋이 샌드박스에서 막히면 미커밋으로 두고 보고한다. push와 PR 생성은 하지 않는다.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
