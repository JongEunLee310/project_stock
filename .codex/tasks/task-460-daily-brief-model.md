# Codex Handoff Task

## Source Issue

#460 — [BE] 에이전트1: 일일 브리프 저장 모델(research_reports 확장) (에픽 #459)

## Task Summary

일일 리서치 에이전트의 브리프를 `research_reports`에 저장할 수 있게 컬럼 세 개와 enum, 부분 unique
인덱스, 마이그레이션, repository 함수를 추가한다. 기존 리포트 API와 리서치 큐 동작은 바뀌지 않는다.

## Goal

- `research_reports`에 `report_type`(기본 `ARTICLE`), `brief_date`, `content`가 있다.
- 같은 종목·날짜의 `DAILY_BRIEF`는 하나만 존재할 수 있다.
- repository로 일일 브리프를 upsert하고, 종목의 가장 최근 일일 브리프를 조회할 수 있다.
- 기존 테스트(리포트 API, 리서치 큐)가 그대로 통과한다.

## Background

- 설계 정본: `docs/designs/459-daily-research-agent.md` §2. 결정: ADR-020. **반드시 먼저 읽는다.**
- 현재 모델: `app/domains/reports/model.py`(`ResearchReport`, `TimestampMixin`), repository
  `app/domains/reports/repository.py`(`create`, `get_by_id`, `list_by_asset`, `count_by_asset`), schema
  `app/domains/reports/schema.py`(`ResearchReportCreate`, `ResearchReportResponse`)
- 리서치 큐는 종목별 최근 리포트 시각을 쓴다(`app/domains/research_queue/repository.py:45-46`).
  `report_type`과 무관하게 지금처럼 모든 리포트를 대상으로 둔다.
- 마이그레이션 head는 `c3d4e5f60070`이다(`uv run alembic heads`). revision id는 기존 수작업 스타일을 따른다.
- 테스트 DB는 SQLite이고, CI `Verify pgvector` 잡이 Postgres에서 마이그레이션 왕복과 `postgres` 마커
  테스트를 실행한다.
- 의존성 추가는 없다. `uv add`, `uv sync`, 네트워크, `git fetch`, docker 명령을 하지 않는다.

## Implementation Scope

1. `app/domains/reports/types.py`: `ReportType(str, Enum)` — `ARTICLE`, `DAILY_BRIEF`
2. 모델 `ResearchReport`에 컬럼 추가
   - `report_type: str`(String(20), not null, 기본값 `ARTICLE` — Python 기본값과 `server_default` 모두)
   - `brief_date: date | None`
   - `content: dict | None`(JSON)
   - 부분 unique 인덱스 `uq_research_reports_daily_brief`: (`asset_id`, `brief_date`) where
     `report_type = 'DAILY_BRIEF'`. Postgres(`postgresql_where`)와 SQLite(`sqlite_where`) 모두 적용한다.
3. 마이그레이션: 컬럼 추가(기존 행은 `ARTICLE`), 부분 unique 인덱스 생성. downgrade는 역순으로 제거.
4. repository 함수 추가(`ResearchReportRepository`)
   - `upsert_daily_brief(asset_id: int, brief_date: date, summary: str, risk_level: str | None, content: dict) -> ResearchReport`
     — 같은 종목·날짜의 `DAILY_BRIEF`가 있으면 `summary`·`risk_level`·`content`와 `updated_at`을 갱신하고,
     없으면 만든다. 커밋하지 않고 `flush`까지만 한다(에이전트가 종목 단위로 커밋한다, 설계 §3).
   - `get_latest_daily_brief(asset_id: int) -> ResearchReport | None` — `created_at` 기준 가장 최근
     `DAILY_BRIEF`. 갱신된 브리프의 시각 판단에는 `updated_at`이 필요할 수 있으니 둘 다 조회 가능해야 한다.
5. `ResearchReportResponse`와 리포트 API의 응답 형태는 바꾸지 않는다(설계 §2: FE 표시 작업에서 정함).
6. 기존 `create`는 `report_type`을 넘기지 않아도 `ARTICLE`로 저장돼야 한다.

## Out of Scope

- 에이전트 워크플로·LLM·Obsidian·스케줄(#461~#463)
- 리포트 API 응답 필드 추가
- 기존 `ARTICLE` 리포트 데이터 변경

## Protected Files

없음.

## Requirements

- 마이그레이션은 단일 head를 유지한다.
- 모든 공개 함수에 타입 주석을 단다.
- 주석은 이유가 분명하지 않은 곳에만 최소한으로 쓴다.

## Test Requirements

- SQLite
  - 기존 `create`가 `ARTICLE`로 저장됨
  - `upsert_daily_brief` 신규 생성과 같은 날 재호출 시 행이 하나로 유지되고 내용이 갱신됨
  - 다른 날짜·다른 종목은 별도 행
  - `ARTICLE` 리포트는 같은 종목·날짜 값이 있어도 unique 제약에 걸리지 않음(부분 인덱스 확인)
  - `get_latest_daily_brief`가 `ARTICLE`을 무시하고 가장 최근 `DAILY_BRIEF`를 돌려줌
  - 리서치 큐의 최근 리포트 시각에 `DAILY_BRIEF`도 반영됨
- `postgres` 마커: 부분 unique 인덱스가 Postgres에서도 같은 종목·날짜 `DAILY_BRIEF` 중복을 막음
- 기존 `tests/test_research_reports.py`와 리서치 큐 테스트가 수정 없이 통과(필요하면 픽스처만 보강)

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
uv run alembic heads
```

## Documentation Impact

없음(설계 459 §2가 정본). 구현 중 설계와 다르게 정한 값이 있으면 설계 459 §2에 반영한다.

## ADR Need

불필요. ADR-020의 적용이다.

## Failure Record Need

불필요.

## Risk Level

High — DB 스키마 변경. 사용자가 2026-10-12 설계 459와 "#460부터 진행"을 승인했다. 머지는 개발자가 결정한다.

## Expected Output

- 현재 브랜치 `feat/460-daily-research-agent`에서 작업한다. 새 브랜치를 만들지 않는다.
- 커밋이 샌드박스에서 막히면 미커밋 상태로 두고 보고한다. push와 PR 생성은 하지 않는다.
- 최종 보고: 변경 파일 목록, 가정, 검증 명령별 결과, 실행하지 못한 검증

## Stop Conditions

- 설계와 다르게 구현해야 하는 상황
- 의존성 추가가 필요한 상황
- 기존 테스트가 이 변경과 무관한 이유로 실패하는 상황
- 샌드박스 권한 부족

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
