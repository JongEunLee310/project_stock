# Design Record Policy

Claude Code must write a skeleton-level design document in `docs/designs/` before creating a Codex handoff when any of the following apply:

- A new domain or subdomain is introduced.
- A new database table is created.
- A new external dependency or adapter boundary is defined.
- An architectural decision with future impact is made.

## Document Location

`docs/designs/<issue-number>-<short-slug>.md`

## Document Level

Skeleton only. No implementation code.

- Models: table name, field names, types, constraints.
- APIs: HTTP method, path, request schema name, response schema name.
- Services: function signatures and one-line responsibility.
- Repositories: function signatures and one-line responsibility.
- Dependencies: explicit list of other domains this design depends on.

No SQL queries, no business logic code, no full class bodies.

## Document Language

설계 문서(`docs/designs/`)와 ADR(`docs/decisions/`)의 본문 산문은 한국어로 작성한다.
섹션 헤더와 Status 라벨 등 고정 라벨, 그리고 코드 기호(클래스·함수·enum 값·파일 경로·
설정 키·식별자)는 영어로 유지한다 — 산문만 한국어로 쓰고 정보 밀도는 보존한다. 이는
`local-review-policy.md`의 리뷰 기록 한국어 규칙과 전역 선호(응답은 한국어)를 ADR·설계
문서로 확장한 것이다.

한국어로 자연스럽게 읽히는 문장 구조를 쓴다. 영어 직역체, 동사를 명사형으로 끝맺는
과도한 압축(예: "~ 정리.", "~ 일관."), 절을 화살표(`→`)로 잇는 표기, 여러 수식을 한
명사에 욱여넣어 한 번에 읽기 어려운 구조를 피한다. 주어와 서술어가 분명한 문장으로
풀어 쓰되, 기술 식별자와 정보 밀도는 그대로 둔다 — 구조만 자연스럽게 한다. 이 원칙은
설계·ADR·리뷰·PR·핸드오프 등 한국어 산문을 쓰는 모든 문서에 적용한다.

## When to Skip

- Pure test additions.
- Style or documentation changes.
- Bug fixes that do not alter schema or domain boundaries.

## Related

- `docs/decisions/` — for ADRs when an approach is chosen over alternatives.
- `docs/knowledge/workflow.md` — step 2a of the default workflow.
