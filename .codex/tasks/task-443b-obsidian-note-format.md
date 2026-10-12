# Codex Handoff Task

## Source Issue

#443 보정 — Obsidian 노트 표시 형식 (에픽 #438). `task-443-obsidian-writer.md`의 후속이다.

## Task Summary

orchestrator가 실제 노트를 만들어 확인한 결과, Obsidian 표시 품질 문제가 세 가지 있었다.
`render_research_note`(`app/adapters/obsidian/writer.py`)만 고친다.

## Background

실제 생성 결과(2026-10-12 orchestrator 확인)는 다음과 같았다.

- frontmatter: `question: "애플이 ..."`. `json.dumps`의 기본 `ensure_ascii=True` 때문에
  한글이 이스케이프된다. YAML로는 해석되지만, 사용자가 노트 원문을 읽거나 편집할 수 없다.
- 답변: `- 애플과 브로드컴의 ... 보도되었습니다. [1][2]`. `[1][2]`는 Markdown 참조 링크 문법과 겹친다.
- 근거: `[1] [제목](url) — 매체, 날짜`가 목록 기호 없이 줄만 바뀌어 있어, 설정에 따라 한 문단으로
  합쳐진다.

## Implementation Scope

1. frontmatter 문자열 직렬화에 `ensure_ascii=False`를 쓴다. 따옴표, 역슬래시, 줄바꿈, 제어 문자는
   계속 이스케이프되어야 한다.
2. 답변 인용을 Obsidian 각주로 바꾼다. 항목은 `- {text}[^1][^2]` 형식이다(본문 끝과 각주 사이에
   공백을 두지 않는다).
3. `## 근거` 섹션은 각주 정의로 쓴다. 형식은 `[^{id}]: [{title}]({source_url}) — {source_name}, {날짜}`이고,
   정의 사이에 빈 줄을 둔다. 답변에서 인용하지 않은 근거도 정의로 남긴다(검색된 근거 전체를 기록으로
   보존). 제목에 `[`나 `]`가 있으면 링크 텍스트가 깨지지 않게 역슬래시로 이스케이프한다.
4. `insufficient_evidence` 안내 문구를 "근거가 부족합니다."로 마침표까지 쓴다.
5. 설계 438 §4.3의 노트 구성 설명을 위 형식에 맞게 고친다.

## Out of Scope

- 경로 규칙, 파일 생성 방식, 서비스·API, compose

## Protected Files

없음.

## Test Requirements

- 한글 질문이 frontmatter에 그대로 보이고, 따옴표와 줄바꿈이 있는 질문은 YAML double-quoted 문자열로
  올바르게 이스케이프된다.
- 답변 항목에 `[^n]` 각주가 붙고, `## 근거`에 모든 근거의 각주 정의가 있다.
- 제목에 `[`·`]`가 있는 근거의 링크 텍스트가 이스케이프된다.
- 기존 writer 테스트를 새 형식에 맞게 고치되 검증 강도를 낮추지 않는다.

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

Low — 순수 렌더링 함수 보정.

## Expected Output

- 현재 브랜치 `feat/443-obsidian-writer`에서 작업한다. 새 브랜치를 만들지 않는다.
- 이전 #443 작업은 orchestrator가 이미 커밋했다. 커밋이 샌드박스에서 막히면 미커밋으로 두고
  보고한다. push와 PR 생성은 하지 않는다.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
