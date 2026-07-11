# Codex Handoff Task

## Source

PR #273 로컬 리뷰(`docs/reviews/pr-273.md`)의 Blocking B1 수정.

## 수정 지시

`tests/test_news_disclosure.py`만 수정한다. 구현 코드는 바꾸지 않는다.

- B1: `test_get_news_disclosure_separates_news_and_disclosures`가
  `data["news"][0]`을 `"id": 2` 리터럴 포함 dict 전체와 비교한다.
  conftest가 StaticPool 단일 in-memory SQLite를 공유하므로 autoincrement
  값은 실행 순서에 의존한다. `id`는 정수 존재 여부만 단언하고 나머지
  필드는 기존대로 정확 비교하도록 바꾼다 (예: id를 분리 검증 후 dict
  비교에서 제외).
- 같은 파일에 유사한 id 리터럴 단언이 더 있으면 같은 방식으로 정리한다.

## Verification

- `uv run ruff check .`, `uv run mypy .`, `NEWS_PROVIDER=mock uv run pytest`
  전부 통과.

## Rules

- 현재 브랜치(feat/268-news-disclosure-metadata)에서 새 커밋 1개. push 금지.
- 커밋 메시지는 한국어 `type: 본문` 형식.
