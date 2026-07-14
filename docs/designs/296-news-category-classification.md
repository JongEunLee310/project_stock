# Design: 뉴스·공시 카테고리 자동 분류 — 규칙 기반 1차 (#296)

- Status: Accepted
- Issue: #296
- 소비처: FE 뉴스·공시 카테고리 배지 (FE #184에서 색 구분 적용됨)

## 1. 배경

`news_items.category`(String(30), nullable)와 `NewsCategory` Literal
(EARNINGS·PRODUCT·PARTNERSHIP·REGULATION·PERSONNEL·CAPITAL·MARKET·OTHER)이
계약에 정의되어 있으나 수집 데이터에서 채워지지 않아 FE 배지가 표시되지
않습니다. 1차로 규칙 기반 키워드 분류를 도입합니다. LLM 분류는 2차
(하이브리드 LLM 아키텍처 라운드)로 미룹니다.

## 2. 분류기

- `app/domains/news/categorizer.py` 신규.
  - `categorize(title: str, summary: str | None) -> NewsCategory`
  - 카테고리별 한국어·영어 키워드 사전을 상수로 정의 (예: EARNINGS —
    실적/영업이익/매출/분기/earnings/revenue/guidance, CAPITAL —
    유상증자/자사주/배당/buyback/dividend, REGULATION — 규제/소송/제재/
    FTC/공정위 등).
  - 우선순위가 있는 첫 매칭 반환, 무매칭 시 `OTHER` 폴백.
  - 순수 함수 — DB·외부 호출 없음.

## 3. 적용 지점

- 뉴스 정규화 경로: `NewsItemCreate` 생성 시 `category`가 비어 있으면
  분류기 적용 (`app/domains/news/normalization_service.py` 또는
  `normalizer.py` — 기존 구조를 따라 구현에서 확정).
- 공시 경로: 공시 항목이 같은 `news_items` 테이블/계약을 지나면 동일
  지점에서 처리, 별도 경로면 해당 정규화 지점에 동일 분류기 적용.
- 기존 저장 행 backfill: 수집 태스크와 분리된 idempotent 일회성 처리
  (`category IS NULL` 행에 분류기 적용). 구현은 관리 스크립트
  (`scripts/` 관례) 또는 기존 태스크 러너 재사용 중 저장소 관례를 따른다.

구현에서는 `NewsItemRepository.create()`를 공통 fallback으로 사용해 모든 저장
경로에서 비어 있는 category만 분류하고, 원시 뉴스 정규화와 공시 projection에도
분류기를 명시적으로 적용한다. 기존 행은 다음 명령으로 idempotent하게 채운다.

```bash
uv run python scripts/backfill_news_categories.py
```

## 4. 계약 영향

없음 (기존 nullable 필드를 채우는 것뿐). `OTHER` 폴백으로 신규 저장 행의
category는 항상 non-null이 되지만, 과거 행·계약상 null 허용은 유지.

## 5. Test / Verification

- 분류기 단위 테스트: 카테고리별 대표 제목(한국어·영어) 최소 1건씩,
  무매칭 → OTHER, 복수 매칭 시 우선순위.
- 정규화 경로 테스트: 수집 항목의 category가 채워져 저장됨.
- 기존 계약 테스트 회귀 없음.
- `uv run ruff check .` / `uv run mypy .` / `uv run pytest`
