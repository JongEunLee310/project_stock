# Codex Handoff Task

## Source Issue

Issue #16: Research Report 도메인 구현

## Task Summary

종목별 AI 분석 결과를 `research_reports` 테이블에 저장하고, 생성·목록·상세 조회 API를 구현한다.

## Goal

- 종목별 리포트를 생성할 수 있다.
- 리포트에는 요약, 긍정/부정 요인, 리스크 레벨, 투자 가설 충돌 여부와 근거가 포함된다.
- 리포트와 분석에 사용된 뉴스 목록이 연결된다.

## Background

- **설계 문서를 구현 전에 반드시 읽는다:** `docs/designs/016-research-report-domain.md`
- task-011, task-012, task-013 완료 후 진행.
- `positive_factors`, `negative_factors`, `news_item_ids`는 JSON 배열 문자열로 저장하고 API 응답 시 `list`로 직렬화한다.
- `ResearchReportResponse`에서 `positive_factors`, `negative_factors`, `news_item_ids`를 `list` 타입으로 반환하려면 `model_validator` 또는 `field_validator`로 파싱 처리한다.
- 리포트 생성은 LLM 호출 없이 수동 입력 데이터 저장으로 구현한다 (LLM 연동은 향후 이슈에서 수행).
- 목록 조회 시 `asset_id` 쿼리 파라미터는 필수이다.

## Implementation Scope

- `alembic/versions/<hash>_create_research_reports.py` — 신규 테이블 마이그레이션
- `app/domains/reports/__init__.py`
- `app/domains/reports/model.py` — `ResearchReport` SQLAlchemy 모델
- `app/domains/reports/schema.py` — `ResearchReportCreate`, `ResearchReportResponse`
- `app/domains/reports/repository.py` — `ResearchReportRepository`
- `app/domains/reports/service.py` — `ResearchReportService`
- `app/api/v1/endpoints/reports.py` — API 엔드포인트
- `app/api/v1/router.py` — reports 라우터 등록
- `tests/test_research_reports.py`

## Out of Scope

- 리포트 수정(PUT) / 삭제(DELETE) API
- LLM을 통한 자동 리포트 생성
- Worker job 통합
- 알림(Signal) 생성

## Protected Files

변경하지 않는 파일:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`, `docs/decisions/`

## Requirements

### Alembic 마이그레이션 — research_reports

```
id                      INTEGER PK
asset_id                INTEGER FK(assets.id) NOT NULL INDEX
thesis_id               INTEGER FK(investment_theses.id) NULL
summary                 TEXT NOT NULL
positive_factors        TEXT NULL   -- JSON 배열 문자열
negative_factors        TEXT NULL   -- JSON 배열 문자열
risk_level              VARCHAR(20) NULL   -- LOW / MEDIUM / HIGH / CRITICAL
thesis_conflict_status  VARCHAR(20) NULL   -- SUPPORTS / NEUTRAL / CONFLICTS
conflict_reason         TEXT NULL
news_item_ids           TEXT NULL   -- JSON 배열 문자열 (int[])
created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
```

### ResearchReportCreate 스키마

```python
class ResearchReportCreate(BaseModel):
    asset_id: int
    thesis_id: int | None = None
    summary: str
    positive_factors: list[str] | None = None
    negative_factors: list[str] | None = None
    risk_level: str | None = Field(default=None, max_length=20)
    thesis_conflict_status: str | None = Field(default=None, max_length=20)
    conflict_reason: str | None = None
    news_item_ids: list[int] | None = None
```

### ResearchReportResponse 스키마

```python
class ResearchReportResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    asset_id: int
    thesis_id: int | None
    summary: str
    positive_factors: list[str] | None
    negative_factors: list[str] | None
    risk_level: str | None
    thesis_conflict_status: str | None
    conflict_reason: str | None
    news_item_ids: list[int] | None
    created_at: datetime
```

`positive_factors`, `negative_factors`, `news_item_ids` 필드는 DB에서 JSON 문자열로 읽어와 `list`로 변환하는 `field_validator`를 추가한다.

### ResearchReportRepository

```python
class ResearchReportRepository:
    def __init__(self, db: Session)
    def create(self, data: ResearchReportCreate) -> ResearchReport
    def get_by_id(self, report_id: int) -> ResearchReport | None
    def list_by_asset(self, asset_id: int) -> list[ResearchReport]
```

`create`에서 `positive_factors`, `negative_factors`, `news_item_ids`를 `json.dumps`로 직렬화 후 저장.

### ResearchReportService

```python
class ResearchReportService:
    def __init__(self, db: Session)
    def create_report(self, data: ResearchReportCreate) -> ResearchReport
    def get_report(self, report_id: int) -> ResearchReport  # 없으면 HTTPException 404
    def list_reports(self, asset_id: int) -> list[ResearchReport]
```

### API 엔드포인트 (app/api/v1/endpoints/reports.py)

```
POST   /api/v1/reports
       Request:  ResearchReportCreate
       Response: ResearchReportResponse (201)

GET    /api/v1/reports?asset_id={int}
       Response: list[ResearchReportResponse] (200)
       asset_id 파라미터 누락 시 422

GET    /api/v1/reports/{report_id}
       Response: ResearchReportResponse (200)
       존재하지 않으면 404
```

모든 엔드포인트는 인증(JWT) 필요 — 기존 `deps.get_current_user` 사용.

### app/api/v1/router.py 변경

```python
from app.api.v1.endpoints import reports
router.include_router(reports.router, prefix="/reports", tags=["reports"])
```

## Test Requirements

`tests/test_research_reports.py`:

- `POST /api/v1/reports` — 정상 생성, 201 응답, `id` 포함 검증
- `GET /api/v1/reports?asset_id={id}` — 리포트 목록 반환 검증
- `GET /api/v1/reports/{id}` — 존재하는 리포트 상세 반환 검증
- `GET /api/v1/reports/{id}` — 존재하지 않는 id 입력 시 404 검증
- `GET /api/v1/reports` — `asset_id` 누락 시 422 검증
- `positive_factors`, `news_item_ids` — API 응답에서 `list` 타입으로 반환되는지 검증

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest tests/test_research_reports.py -v
```

## Documentation Impact

없음.

## ADR Need

없음.

## Failure Record Need

없음.

## Risk Level

Medium — 신규 테이블 마이그레이션, 신규 API 라우터 등록 포함.

## Expected Output

- 위 scope 파일 신규 생성
- Alembic 마이그레이션 파일 신규 생성
- `app/api/v1/router.py`에 reports 라우터 추가
- `uv run pytest tests/test_research_reports.py` 통과
- lint/typecheck 통과

## Rules

- 구현 전 `docs/designs/016-research-report-domain.md`를 읽는다.
- task-011, task-012, task-013 완료 후 진행한다.
- `positive_factors`, `negative_factors`, `news_item_ids` DB 저장 시 `json.dumps`, 조회 시 `json.loads`.
- 기존 엔드포인트의 인증 방식(`deps.get_current_user`)을 그대로 따른다.
- 스코프 외 파일 변경 금지.
- 테스트 약화 금지.
- 보호 파일 변경 금지.
