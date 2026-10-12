# Codex Handoff Task

## Source Issue

#443 — [BE] RAG 1차: Obsidian 노트 쓰기(ObsidianWriter) (에픽 #438)

## Task Summary

리서치 Q&A 결과를 Obsidian vault에 Markdown 노트로 저장한다. 요청에 `save_to_obsidian`을 추가하고,
응답에 저장 경로 `obsidian_note_path`를 추가한다. agent는 새 파일만 만들고 기존 파일은 열거나
수정하지 않는다. 저장 실패는 Q&A 응답을 실패시키지 않는다.

## Goal

완료 시 다음이 참이어야 한다.

- `POST /api/v1/assets/{asset_id}/research-qa`에 `save_to_obsidian: true`를 보내면 vault에 노트가
  생기고 응답 `obsidian_note_path`에 vault 기준 상대 경로가 온다.
- vault가 설정되지 않았거나 쓰기에 실패하면 응답은 200이고 `obsidian_note_path=null`이며 경고 로그가
  남는다.
- 같은 이름의 파일이 있으면 `-2`, `-3` 접미사로 새 파일을 만들고 기존 파일 내용은 바뀌지 않는다.
- 기존 요청·응답 필드는 그대로이고 새 필드는 추가만 된다.

## Background

- 설계 정본: `docs/designs/438-rag-research-qa.md` §4.3(ObsidianWriter), §5.1(API). 반드시 먼저 읽는다.
- 결정(ADR-018): 1차 vault는 쓰기 전용이고 로컬 compose 전용이다. 배포 compose에는 마운트하지 않는다
  (이 repo에는 로컬 compose만 있다). ABC는 두지 않는다(3차 읽기 #446에서 필요하면 분리).
- 사용자는 아직 vault가 없다. 그래서 기본 마운트 위치는 repo 안의 gitignore된 폴더로 두고, 실제 vault
  경로는 `.env`로 바꾸게 한다.
- #442(머지됨)의 `ResearchQAService.ask`(`app/domains/rag/service.py`)와 스키마
  (`app/domains/rag/schema.py`)를 확장한다.
- PR #453 리뷰 S3: 실제 LLM은 `insufficient_evidence=true`이면서도 부족한 이유를 인용과 함께
  `answer_points`로 설명한다. 이 해석을 문서에 한 줄 남기고, 노트 렌더링도 이 경우 답변 항목을
  보여 준다.
- 의존성 추가는 없다(`zoneinfo`는 표준 라이브러리). `uv add`, `uv sync`, 네트워크, `git fetch`,
  docker 명령을 하지 않는다.

## Implementation Scope

1. **설정**(`app/core/config.py`)
   - `OBSIDIAN_VAULT_PATH: str | None = None` — 빈 문자열은 `None`(기존 validator 대상에 추가)
   - `OBSIDIAN_EXPORT_DIR: str = "stock-agent"`
2. **`ObsidianWriter`**(`app/adapters/obsidian/writer.py`)
   - 값 객체 `ResearchNote`: `symbol`, `asset_name`, `question`, `answer: ResearchAnswer`,
     `embedding_model`
   - `ObsidianWriter(vault_path: Path, export_dir: str)`
   - `write_research_note(note: ResearchNote) -> Path` — 새 파일을 만들고 vault 기준 상대 경로를
     돌려준다.
     - 경로: `{vault}/{export_dir}/research/{SYMBOL}/{YYYY-MM-DD}-{slug}.md`
     - 날짜는 `answer.generated_at`을 `Asia/Seoul`로 바꾼 날짜다(가정).
     - slug는 질문 앞 40자(가정)에서 파일명에 쓸 수 없는 문자(`/ \ : * ? " < > | # ^ [ ]`)와 공백을
       `-`로 바꾸고, 연속 `-`를 하나로 줄이고, 앞뒤 `-`를 지운다. 한글은 그대로 둔다. 비면 `question`.
     - 파일은 배타적 생성 모드(`open(..., "x")`)로 만든다. 이미 있으면 `-2`, `-3`… 접미사를 붙여
       다시 시도한다(최대 100회, 가정). 기존 파일은 읽지도 수정하지도 않는다.
     - 디렉터리가 없으면 만든다. vault 경로 자체가 없으면 만들지 않고 `FileNotFoundError`를 낸다
       (잘못된 설정을 조용히 새 폴더로 덮지 않기 위해).
     - `symbol`이나 slug가 경로 탈출(`..`, 절대 경로)을 만들지 않게 막는다. 최종 경로가 vault 아래인지
       확인한다.
   - 렌더링 함수 `render_research_note(note) -> str`(순수 함수)
     - frontmatter(YAML): `symbol`, `asset_name`, `question`, `generated_at`(ISO 8601),
       `embedding_model`, `source_count`, `insufficient_evidence`, `tags: [stock-agent, research-qa]`.
       문자열 값은 YAML에서 안전하게 따옴표 처리한다(콜론, 따옴표, 줄바꿈이 있는 질문 포함).
     - 본문 구성
       - `# {asset_name}({symbol}) 리서치 Q&A`
       - `[[{SYMBOL}]]` wikilink 한 줄
       - `## 질문`
       - `## 답변`: 항목마다 `- {text} [1][3]` 형식. `insufficient_evidence`이면 맨 위에 "근거가
         부족합니다" 안내를 두되 항목은 그대로 보여 준다(PR #453 S3).
       - `## 한계`: `limitations`(없으면 섹션 생략)
       - `## 근거`: `[n] [{title}]({source_url}) — {source_name}, {published_at 날짜}`
       - 끝에 생성 안내 한 줄: "이 노트는 stock-agent가 생성했습니다. 매수·매도 권유가 아닙니다."
   - factory 함수 `get_obsidian_writer() -> ObsidianWriter | None`(`app/adapters/factory.py`):
     설정이 없으면 `None`
3. **API 확장**
   - `ResearchQARequest.save_to_obsidian: bool = False`
   - `ResearchAnswer.obsidian_note_path: str | None = None`
   - `ResearchQAService`에 `obsidian_writer: ObsidianWriter | None = None` 인자를 추가한다. `ask`가
     답을 만든 뒤 `save_to_obsidian`이 참이면 저장한다.
     - writer가 `None`이면 경고 로그 후 `None`
     - `OSError`나 `ValueError`(경로 탈출 등)이면 경고 로그 후 `None`. 그 밖의 예외는 기존 관례대로
       전파한다.
     - 근거가 0건인 응답도 요청이 있으면 저장한다(무엇을 물었고 근거가 없었는지가 기록으로 의미가
       있음).
   - 엔드포인트에서 `get_obsidian_writer()`를 넘긴다.
4. **compose**(`docker-compose.yml`)
   - `backend`의 `volumes`에 `${OBSIDIAN_VAULT_HOST_PATH:-./.obsidian-vault}:/vault`를 추가하고,
     `environment`에 `OBSIDIAN_VAULT_PATH: /vault`를 추가한다. `worker`와 다른 서비스는 바꾸지 않는다.
   - `.gitignore`에 `.obsidian-vault/`를 추가한다.
   - `.env.example`에 `OBSIDIAN_VAULT_HOST_PATH`, `OBSIDIAN_VAULT_PATH`, `OBSIDIAN_EXPORT_DIR`와 짧은
     주석(호스트 실행과 compose 실행의 차이)을 추가한다.
5. **문서**
   - 설계 438 §4.3·§5.1에 위 결정(상대 경로 반환, 배타적 생성, 경로 탈출 방지, 날짜 시간대, vault
     부재 시 동작, 근거 0건도 저장)을 반영한다.
   - 설계 438 §5.1과 `docs/api/frontend-api-spec.md`에 두 필드를 추가하고, "`insufficient_evidence=true`와
     `answer_points`가 함께 올 수 있다"를 한 줄 적는다(PR #453 S3).

## Out of Scope

- vault 읽기(#446), 노트 수정·덮어쓰기
- 배포 환경 마운트
- FE(`project_stock_frontend#308`)
- 마이그레이션

## Protected Files

없음.

## Requirements

- 테스트는 실제 홈 디렉터리나 repo의 `.obsidian-vault`에 쓰지 않는다. `tmp_path`만 쓴다.
- 모든 공개 함수에 타입 주석을 단다.
- 주석은 이유가 분명하지 않은 곳에만 최소한으로 쓴다.

## Test Requirements

- 렌더링(순수 함수): frontmatter 키와 따옴표 처리(콜론·따옴표·줄바꿈이 있는 질문), 인용 표기, 근거
  목록, wikilink, `insufficient_evidence`일 때 안내와 항목이 함께 나옴, `limitations` 없음
- writer(`tmp_path`)
  - 경로 규칙과 `Asia/Seoul` 날짜(UTC 자정 직전 시각이 서울 날짜로 바뀌는 경우)
  - slug 정제(한글 유지, 금지 문자, 40자 절단, 빈 결과)
  - 파일명 충돌 시 `-2`·`-3`, 기존 파일 내용이 바이트 단위로 그대로임
  - vault 경로 없음 → `FileNotFoundError`
  - 경로 탈출 시도(`symbol="../x"`) → `ValueError`이며 vault 밖에 파일이 생기지 않음
- 서비스·API
  - `save_to_obsidian=true`이고 writer가 있음 → 응답 `obsidian_note_path`가 있고 파일이 생김
  - writer 없음 → 200, `null`
  - writer가 `OSError` → 200, `null`, 답변은 정상
  - `save_to_obsidian=false` → 파일이 생기지 않음
  - 기존 #442 테스트가 그대로 통과(계약은 추가만)

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

설계 438 §4.3·§5.1, `docs/api/frontend-api-spec.md`, `.env.example`.

## ADR Need

불필요. ADR-018의 적용이다.

## Failure Record Need

불필요.

## Risk Level

Medium — 파일 시스템 쓰기가 생긴다. 새 파일만 만들고 경로 탈출을 막는 것으로 위험을 줄인다. compose
볼륨 추가는 로컬 전용이다.

## Expected Output

- 현재 브랜치 `feat/443-obsidian-writer`에서 작업한다. 새 브랜치를 만들지 않는다.
- 커밋이 샌드박스에서 막히면 미커밋 상태로 두고 보고한다. push와 PR 생성은 하지 않는다.
- 최종 보고: 변경 파일 목록, 가정, 검증 명령별 결과, 실행하지 못한 검증

## Stop Conditions

- 설계·이 핸드오프와 다르게 구현해야 하는 상황
- 의존성 추가가 필요한 상황(YAML 라이브러리가 필요하다고 판단되면 멈추고 보고한다. frontmatter는
  직접 안전하게 직렬화하는 것을 기본으로 한다)
- 기존 테스트가 이 변경과 무관한 이유로 실패하는 상황
- 샌드박스 권한 부족

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
