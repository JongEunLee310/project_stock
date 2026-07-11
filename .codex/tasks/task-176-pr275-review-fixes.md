# Codex Handoff Task

## Source

PR #275 리뷰 후속 조치 (개발자 코멘트 지시). 리뷰 기록:
`docs/reviews/pr-275.md`. 갱신된 설계:
`docs/designs/271-research-coverage-counterview.md` (Endpoint 1 시맨틱
단락을 먼저 읽는다).

## Task Summary

두 가지를 수정한다.

1. **Q1 — `last_collected_at` 시맨틱 정정**: `created_at`은 최초 삽입
   시각이라 "마지막 수집"과 어긋난다 (뉴스: URL 중복 스킵, 가격: upsert
   in-place 갱신). 필드를 "마지막으로 데이터가 갱신된 시각"으로 재정의한다.
   - `app/domains/research_coverage/schema.py` — `last_collected_at` →
     `last_updated_at` 리네임 (미머지 PR이라 계약 소비자 없음).
   - `app/domains/research_coverage/service.py` — NEWS·PRICE 모두
     `max(created_at)` → `max(updated_at)` 파생으로 변경. `updated_at`을
     쓰는 이유(upsert 갱신·요약 보강 반영)를 짧은 WHY 주석으로 남긴다.
   - `tests/test_research_coverage.py` — 픽스처·단언을 `updated_at`
     기준으로 갱신. 가격 upsert 갱신이 반영되는지 확인하는 케이스가
     가능하면 추가한다 (기존 bar 갱신 후 `last_updated_at`이 앞으로
     이동).
   - `tests/test_api_contract.py` — 계약 스냅샷의 필드명 갱신.
2. **S2 — 템플릿 전수 테스트 연동**: `tests/test_assets.py`의
   `test_get_research_summary_returns_structured_fields_for_all_templates`
   가 자산 수를 하드코딩하지 않고
   `len(_SUMMARY_TEMPLATES)`에 연동해 템플릿 추가 시 자동으로 전수
   순회하도록 수정한다.

## Out of Scope

- S1(`_collected_axis` 방어 분기 가독성)은 후속 이슈로 분리됐다. 손대지
  않는다.
- 다른 도메인·설계 문서·alembic 불변.

## Rules

- 현재 브랜치 `feat/271-research-context-contract`에서 그대로 작업한다.
- 커밋은 1개로 만든다. push는 하지 않는다.
- 커밋 메시지는 한국어 `type: 본문` 형식으로 작성한다.
- `docs/designs/266-research-queue-contract.md`(추적되지 않는 파일)는
  건드리지 않는다.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `NEWS_PROVIDER=mock uv run pytest`
