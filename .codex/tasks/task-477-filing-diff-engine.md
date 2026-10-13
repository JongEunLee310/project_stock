# Codex Handoff Task

## Source Issue

#477 — [BE] 에이전트2-1: 보고서 비교 저장 모델과 문단 비교 엔진 (트래킹 #464, 에픽 #459)

## Task Summary

연간보고서 비교 분석 리포트를 저장할 수 있게 `research_reports`에 `source_ref`를 추가하고, 두 해의 공시 섹션
본문을 문단 단위로 비교하는 결정적 비교 엔진을 만든다. LLM 해석과 워크플로는 #478이다.

## Goal

- `research_reports.source_ref`와 부분 unique, `ReportType.FILING_ANALYSIS`, repository 함수 3개가 생긴다.
- `diff_sections(old_text, new_text)`가 문단을 `UNCHANGED`·`MODIFIED`·`TRIVIAL`·`ADDED`·`REMOVED`로 분류하고
  번호(`A1`·`R1`·`M1`)와 통계를 돌려준다.

## Background

- 설계 정본: `docs/designs/464-filing-analysis-agent.md` §1·§2·§3. **반드시 먼저 읽는다.** 경계값(0.97·0.6, 40자)은
  리뷰어가 실제 공시 6쌍으로 측정한 값이다(§1 표).
- 리포트: `app/domains/reports/model.py`·`types.py`·`repository.py`·`schema.py`. 부분 unique 선례는
  `uq_research_reports_daily_brief`(마이그레이션 `c3d4e5f60071`)다. 현재 head는 `c3d4e5f60072`다.
- 새 패키지 `app/domains/agents/filing_analysis/`를 만든다(ADR-020 §2: 에이전트 코드는 `app/domains/agents/{agent}/`).
- 측정에 쓴 방식(참고): 문단 = 줄 단위 분할 후 40자 초과 줄, 머리말 패턴 제외. 유사도 = 공백 기준 단어 토큰에
  `difflib.SequenceMatcher(autojunk=False).ratio()`, 계산 전 `real_quick_ratio`·`quick_ratio`로 현재 최댓값 이하인
  후보를 건너뜀. 표준 라이브러리만으로 충분하다.
- 의존성 추가는 없다. `uv add`, `uv sync`, 네트워크, `git fetch`, docker 명령을 하지 않는다.

## Implementation Scope

1. **저장 모델**(설계 §2)
   - `ReportType.FILING_ANALYSIS`
   - `research_reports.source_ref: str(200) | None`, 부분 unique (`asset_id`, `report_type`, `source_ref`) where
     `source_ref is not null`(Postgres·SQLite 모두 부분 인덱스, 기존 선례와 같은 방식), 마이그레이션(downgrade 포함)
   - repository: `get_by_source_ref(asset_id, report_type, source_ref)`, `create_filing_analysis(asset_id, source_ref,
     summary, risk_level, content) -> ResearchReport`(commit하지 않음), `list_filing_analyses_created_between(asset_id,
     start, end)`(생성 시각 오름차순, `start` 초과 `end` 이하)
   - 기존 리포트 API 응답 형태는 바꾸지 않는다.
2. **비교 엔진**(`app/domains/agents/filing_analysis/diff.py`, 설계 §3)
   - `split_paragraphs(text) -> list[str]`
   - `diff_sections(old_text, new_text) -> SectionDiff`
     - 짝짓기: 새 문단마다 옛 문단 후보와의 유사도를 구하고, 전체 (유사도, 새, 옛) 쌍을 높은 순으로 확정해 옛 문단이
       한 번만 짝지어지게 한다(설계 "먼저 높은 유사도부터 확정"). 0.6 미만은 짝짓지 않는다.
     - `TRIVIAL`: `MODIFIED` 중 바뀐 토큰(양쪽 모두)이 숫자·날짜·연도·통화 금액·퍼센트 패턴뿐인 경우
     - `MODIFIED` 항목은 옛 문단, 새 문단, 바뀐 구간 목록(옛 토큰열, 새 토큰열)을 담는다.
     - 번호는 새 문단 순서(ADDED·MODIFIED)와 옛 문단 순서(REMOVED)로 1부터 붙인다.
     - `stats`: 분류별 수, `ADDED`·`REMOVED` 글자 수, `MODIFIED` 바뀐 글자 수
   - 값 객체는 `schema.py`에 둔다(frozen dataclass 또는 Pydantic, 주변 코드에 맞춤).
3. 설계 문서는 구현과 다르게 정한 것이 있을 때만 고친다.

## Out of Scope

- LLM, 워크플로, 신호·알림, job(#478)
- Obsidian, 일일 브리프(#479)

## Protected Files

없음.

## Test Requirements

- 마이그레이션: 단일 head, 부분 unique(같은 `source_ref` 중복 거부, `source_ref` null은 여러 개 허용), 왕복
- repository 세 함수(기간 경계 포함)
- `split_paragraphs`: 40자 경계, 머리말 패턴(`Table of Contents`, `Apple Inc. | 2025 Form 10-K | 4`) 제거
- `diff_sections`: 경계값 0.97·0.6 양쪽, 옛 문단 중복 짝짓기 방지(비슷한 새 문단 2개가 옛 문단 1개를 다툼),
  `TRIVIAL`(연도·금액·퍼센트만 바뀜) vs `MODIFIED`(단어가 바뀜), 번호 부여 순서, 빈 입력, 통계 합계
- 성능: 문단 250개 × 250개 합성 입력이 수 초 안에 끝남(시간 상한 assertion은 넉넉히)

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
uv run alembic heads
```

## ADR Need

불필요.

## Failure Record Need

불필요.

## Risk Level

Low — 스키마 컬럼 추가와 순수 함수.

## Expected Output

- 현재 브랜치 `feat/477-filing-diff-engine`에서 작업한다. 새 브랜치를 만들지 않는다.
- 커밋이 샌드박스에서 막히면 미커밋 상태로 두고 보고한다. push와 PR 생성은 하지 않는다.
- 최종 보고: 변경 파일 목록, 가정, 검증 결과

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
