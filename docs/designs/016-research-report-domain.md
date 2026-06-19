# 016: Research Report 도메인

## 목적

종목별 AI 분석 결과를 리포트로 저장하고 조회한다.
뉴스 요약 및 투자 가설 충돌 판단을 종합한 이력을 보관한다.

## DB 모델

테이블: `research_reports`

| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | Integer PK | |
| asset_id | FK → assets, index | |
| thesis_id | FK → investment_theses, nullable | 분석 기준 가설 |
| summary | Text | 종합 요약 |
| positive_factors | Text, nullable | JSON 배열 문자열 |
| negative_factors | Text, nullable | JSON 배열 문자열 |
| risk_level | String(20), nullable | LOW / MEDIUM / HIGH / CRITICAL |
| thesis_conflict_status | String(20), nullable | SUPPORTS / NEUTRAL / CONFLICTS |
| conflict_reason | Text, nullable | 충돌 근거 |
| news_item_ids | Text, nullable | JSON 배열 문자열 — 분석 대상 news_items.id 목록 |
| created_at | DateTime(tz) | |
| updated_at | DateTime(tz) | |

## 스키마 (Pydantic)

```
class ResearchReportCreate(BaseModel):
    asset_id: int
    thesis_id: int | None
    summary: str
    positive_factors: list[str] | None
    negative_factors: list[str] | None
    risk_level: str | None
    thesis_conflict_status: str | None
    conflict_reason: str | None
    news_item_ids: list[int] | None

class ResearchReportResponse(BaseModel):
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

## API

```
POST   /api/v1/reports                — 리포트 생성
GET    /api/v1/reports?asset_id={id} — 목록 조회 (asset_id 필터 필수)
GET    /api/v1/reports/{id}           — 상세 조회
```

## 서비스·레포지토리

```
class ResearchReportRepository:
    def create(self, data: ResearchReportCreate) -> ResearchReport
    def get_by_id(self, report_id: int) -> ResearchReport | None
    def list_by_asset(self, asset_id: int) -> list[ResearchReport]

class ResearchReportService:
    def create_report(self, data: ResearchReportCreate) -> ResearchReport
    def get_report(self, report_id: int) -> ResearchReport
    def list_reports(self, asset_id: int) -> list[ResearchReport]
```

## 의존성

Issue #13, #14, #15 완료 후 진행
