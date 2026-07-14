# Codex Handoff Task

## Source Issue

이슈 #296 — 뉴스·공시 카테고리 자동 분류. 설계:
`docs/designs/296-news-category-classification.md` (먼저 전체를 읽는다).

## Task Summary

계약에 정의만 되어 있고 채워지지 않는 `news_items.category`를 규칙 기반
키워드 분류로 채운다. LLM 분류는 후속 단계로 이번 범위가 아니다.

## Goal

- 신규 수집·정규화되는 뉴스·공시 항목의 `category`가 `NewsCategory`
  값으로 저장된다 (무매칭은 `OTHER`).
- 기존 `category IS NULL` 행을 채우는 idempotent backfill 경로가 있다.
- 계약(스키마)·기존 수집 동작 회귀 없음.

## Implementation Scope

- `app/domains/news/categorizer.py` 신규 — 설계 §2의 순수 함수
  분류기. 카테고리별 한국어·영어 키워드 사전과 우선순위.
- 뉴스·공시 정규화 경로에 분류기 적용 (설계 §3 — `category`가 비어
  있을 때만; 기존 구조에서 적용 지점을 확인해 결정하고, 뉴스와 공시가
  다른 경로면 두 곳 모두).
- 기존 행 backfill — 저장소 관례에 맞는 방식 (scripts/ 일회성 스크립트
  또는 기존 태스크 재사용; idempotent 필수).
- 테스트 — 분류기 단위 테스트(카테고리별 한/영 대표 케이스·OTHER
  폴백·우선순위), 정규화 경로에서 category 저장 검증.

## Out of Scope

- LLM 기반 분류 (Phase 2)
- `NewsCategory` 값 추가·계약 변경
- FE 표시 (이미 카테고리 배지 구현됨 — FE #184)

## Protected Files

없음.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Constraints

- 현재 브랜치(`feat/296-news-category`)에서 그대로 작업한다.
  새 브랜치 생성·checkout 금지.
- 커밋은 한국어 `type: 본문` 형식으로 작성한다.
- 설계 문서·이 태스크 문서·구현이 같은 PR에 함께 실린다.
