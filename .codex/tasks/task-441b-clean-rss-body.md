# Codex Handoff Task

## Source Issue

#441 보정 — RSS HTML 본문 정제 (에픽 #438). `task-441-embed-documents-job.md`의 후속이다.

## Task Summary

`raw_news_events.body`는 기사 본문이 아니라 Google News RSS의 HTML 조각이다. 지금 구현은 이 HTML을
그대로 임베딩 입력에 넣어 URL 토큰이 벡터를 오염시키고, 거의 모든 문서가 `FULL`로 잘못 분류된다.
임베딩 입력을 만들기 전에 본문을 텍스트로 정제한다.

## Background

orchestrator가 2026-10-12 실데이터(로컬 볼륨 복제본, `raw_news_events` 2,703건)로 확인했다.

- 원본 길이 중앙값은 436자지만 대부분이 URL이다. 태그와 엔티티를 지운 텍스트의 중앙값은 85자이고,
  200자 이상은 9건뿐이다.
- 2,668건은 정제한 본문 안에 제목이 그대로 들어 있다(제목 + 매체명 형태).
- 형태 1(단일 헤드라인, `raw_news_events.id=60007` 원문 그대로):

  ```
  <a href="https://news.google.com/rss/articles/CBMiX0FVX3lxTE9ScWVYNngzeTJqV2s3eWRTbVI1Z2Q4aTQ5anBFc1dEZ0Z3RURZelNZWlNWaVduRGE0VnlacFhGOXJvY1NlNEVBMlRfejJrU3lHOVBpVnpCZE9RY3lyMks4?oc=5" target="_blank">US has nothing to worry about Chinese AI models, Jensen Huang says</a>&nbsp;&nbsp;<font color="#6f6f6f">Cybernews</font>
  ```

  같은 행의 `title`은 `US has nothing to worry about Chinese AI models, Jensen Huang says - Cybernews`다.
- 형태 2(관련 헤드라인 목록, `id=88`): `<ol><li><a ...>헤드라인</a>&nbsp;&nbsp;<font ...>매체</font></li><li>...</li></ol>`
  구조다. 예: `Apple says it will spend $30 billion to design US-made Broadcom chips` / `CNN`,
  `Apple’s Chip Deal With Broadcom Expected to Exceed $30 Billion` / `Bloomberg.com`.
- `lxml`은 이미 의존성에 있다(`pyproject.toml`). 의존성을 추가하지 않는다.

## Implementation Scope

1. `app/domains/rag/indexing.py`에 `clean_body_text(body: str | None) -> str`를 추가한다.
   - HTML이면 태그를 지우고 텍스트만 남긴다. `<li>`는 항목마다 한 줄로 나눈다. `<a>`의 `href` 같은
     속성값은 남기지 않는다.
   - HTML 엔티티(`&nbsp;`, `&amp;` 등)를 풀고, 줄 안의 연속 공백은 하나로 줄이고, 빈 줄을 지운다.
   - HTML이 아닌 일반 텍스트는 공백 정리만 한다.
   - 파싱이 실패하면 태그 제거 정규식으로 대체한다(외부 입력 경계).
2. `compose_embedding_text`가 `body` 대신 `clean_body_text(body)`를 쓰도록 바꾼다.
   - 정제한 본문이 제목과 같은 내용만 담은 경우(형태 1)는 본문이 없는 것으로 본다. 판정 기준은
     "정제 본문에서 제목의 앞부분(제목의 ` - 매체명` 꼬리를 뗀 부분)을 지우고 남은 텍스트가 30자
     미만(가정)"이다. 이렇게 해서 제목이 입력에 두 번 들어가지 않게 한다.
   - quality 판정(200자 기준)은 정제한 본문 길이로 한다.
3. 청크 `content`도 정제된 텍스트로 만들어진다(인용 발췌에 HTML이 보이지 않게 하기 위함). 별도
   처리가 필요하지 않으면 그대로 둔다.
4. 설계 438 §3의 본문 결정 규칙에 정제 단계와 위 판정 기준, 실측 수치(중앙값 85자, 200자 이상 9건)를
   반영한다.

## Out of Scope

- 원문 기사 본문 수집(링크 따라가기, 크롤링)
- `raw_news`·`news` 도메인의 저장 데이터 변경
- 인덱서·job 구조 변경

## Protected Files

없음.

## Test Requirements

- 위 두 형태의 원문을 **그대로** 테스트 픽스처로 쓴다(Real-Contract Fixtures). 픽스처 위에 출처를
  주석 한 줄로 남긴다(`raw_news_events` 실데이터 형태, 2026-10-12 확인).
  - 형태 1: 정제 결과에 URL·`href`·`&nbsp;`가 없고, 제목과 같은 내용만 남아 `TITLE_ONLY`가 되며,
    입력 텍스트에 제목이 한 번만 들어간다.
  - 형태 2: 각 헤드라인이 줄 단위로 남고 URL이 없다.
- 일반 텍스트 본문, `None`, 빈 문자열, 잘못된 HTML(닫히지 않은 태그)
- 기존 `compose_embedding_text`·인덱서 테스트는 새 규칙에 맞게 고치되, 검증 강도를 낮추지 않는다.

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

## ADR Need

불필요.

## Failure Record Need

불필요. 머지 전에 발견해 보정한다.

## Risk Level

Low — 순수 함수 보정과 테스트.

## Expected Output

- 현재 브랜치 `feat/441-embed-documents-job`에서 작업한다. 새 브랜치를 만들지 않는다.
- 이전 #441 작업은 orchestrator가 이미 커밋했다. 커밋이 샌드박스에서 막히면 미커밋으로 두고
  보고한다. push와 PR 생성은 하지 않는다.
- 최종 보고: 변경 파일 목록, 가정, 검증 결과

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
