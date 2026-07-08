# Codex Handoff Task

## Source Issue

https://github.com/JongEunLee310/project_stock/issues/237

## Task Summary

관심종목 알림 규칙 템플릿 4종(가격 급변·뉴스 위험도 상승·AI 판단 변경·테마 과열)을
관심목록 단위로 적용·해제하는 CRUD API를 구현한다. 신규 테이블 `watchlist_alert_rules`,
`WatchlistAlertRuleService`, 엔드포인트 2개를 추가하고, alembic migration을 작성한다.

## Goal

- `GET /api/v1/watchlists/{watchlist_id}/alert-rule-templates`가 4종 템플릿의 활성 상태를
  반환한다. DB에 행이 없는 템플릿은 `is_active: false`로 반환한다.
- `PUT /api/v1/watchlists/{watchlist_id}/alert-rule-templates`가 요청 포함 템플릿을
  upsert하고 4종 전체 상태를 반환한다.
- `uv run ruff check .` / `uv run mypy .` / `uv run pytest` 세 검증 명령이 통과한다.

## Background

설계 문서: `docs/designs/237-quick-watch-templates.md`

설계 문서의 Verified Facts에 현재 코드 위치를 검증해 두었다. 구현 전 실코드와 대조하고
불일치하면 보고 후 실코드를 우선하라.

**Phase 분리**: 평가 기반 템플릿 3종(NEWS_RISK_HIGH, AI_JUDGMENT_CHANGE, THEME_OVERHEAT)은
상태 전이 감지가 필요하지만, 온디맨드 평가 결과를 저장하는 `watchlist_evaluation_snapshots`
테이블과 Signal 생성 로직은 이번 범위에 포함하지 않는다. 이번 이슈는 Rule CRUD API만
구현한다. 평가 파이프라인 통합은 후속 이슈로 분리된다.

**'DTO' 용어 금지**: Pydantic 타입은 `projection` 또는 `schema`로 명명한다.
`WatchlistAlertRuleTemplateProjection`처럼 응답 뷰는 `Projection` 접미사를 사용한다.

선행: #234(PR #236 머지 완료) — `WatchlistAlertTemplateType`과 충돌 없이 진행 가능.

현재 브랜치 `feat/237-quick-watch-templates`에서만 작업한다. 새 브랜치를 생성하지 않는다.
커밋하지 않는다.

## Implementation Scope

설계 문서의 Interfaces 절을 따른다.

### 신규 파일

**`app/domains/watchlists/alert_rule_service.py`**

```
class WatchlistAlertRuleService:
    def __init__(self, db: Session) -> None
    def get_template_statuses(
        self, watchlist_id: int, user_id: int
    ) -> list[WatchlistAlertRuleTemplateProjection]
    def apply_templates(
        self, watchlist_id: int, user_id: int,
        data: WatchlistAlertRuleTemplateBulkRequest
    ) -> list[WatchlistAlertRuleTemplateProjection]
    def _get_owned_watchlist(self, watchlist_id: int, user_id: int) -> Watchlist
```

`_get_owned_watchlist` 구현은 `app/domains/watchlists/evaluations_service.py:144-158` 패턴과
동일하다 (`WATCHLIST_NOT_FOUND` 404, `WATCHLIST_FORBIDDEN` 403).

`get_template_statuses` 처리 순서:
1. `_get_owned_watchlist`로 소유 확인
2. `WatchlistAlertRuleRepository.list_by_watchlist(watchlist_id)`로 기존 규칙 조회
3. `WatchlistAlertTemplateType` 4종 전체를 순회하며 projection 생성.
   DB 행 있으면 해당 `is_active`, 없으면 `is_active=False`

`apply_templates` 처리 순서:
1. `_get_owned_watchlist`로 소유 확인
2. 요청의 각 `template_type`을 `WatchlistAlertTemplateType`으로 검증
   (유효하지 않으면 `AppException` 422)
3. `WatchlistAlertRuleRepository.upsert_template`으로 각 템플릿 upsert
4. `get_template_statuses`와 동일하게 4종 전체 상태 반환

**`tests/test_watchlist_alert_rule_templates.py`** (신규)

Test Requirements 절 참고.

### 수정 파일

**`app/domains/watchlists/types.py`**

`WatchlistAlertTemplateType` enum 추가:

```
class WatchlistAlertTemplateType(str, Enum):
    PRICE_SPIKE = "PRICE_SPIKE"
    NEWS_RISK_HIGH = "NEWS_RISK_HIGH"
    AI_JUDGMENT_CHANGE = "AI_JUDGMENT_CHANGE"
    THEME_OVERHEAT = "THEME_OVERHEAT"
```

기존 enum 4종과 `BuyReadinessLevel`은 변경하지 않는다.

**`app/domains/watchlists/model.py`**

`WatchlistAlertRule` 추가:

```
class WatchlistAlertRule(Base, TimestampMixin):
    __tablename__ = "watchlist_alert_rules"
    __table_args__ = (
        UniqueConstraint(
            "watchlist_id", "template_type",
            name="uq_watchlist_alert_rules_template",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id"), index=True)
    template_type: Mapped[str] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
```

`TimestampMixin`은 기존 `Watchlist`(model.py:7) 선례와 동일하게 적용한다.

**`app/domains/watchlists/repository.py`**

`WatchlistAlertRuleRepository` 추가:

```
class WatchlistAlertRuleRepository:
    def __init__(self, db: Session) -> None
    def list_by_watchlist(self, watchlist_id: int) -> list[WatchlistAlertRule]
    def upsert_template(
        self, watchlist_id: int, template_type: str, is_active: bool
    ) -> WatchlistAlertRule
```

`upsert_template`: UniqueConstraint `(watchlist_id, template_type)`를 이용해
이미 존재하면 `is_active`만 업데이트하고 행을 반환한다. SQLAlchemy의
`on_conflict_do_update` 또는 merge 패턴을 사용한다. 구현 전 repository.py의
기존 upsert 패턴 유무를 확인하고, 없으면 `IntegrityError` catch-update 방식으로 구현한다.

**`app/domains/watchlists/schema.py`**

신규 클래스 3개 추가:

```
class WatchlistAlertRuleTemplateProjection(BaseModel):
    template_type: str
    label: str
    condition_description: str
    is_active: bool

class WatchlistAlertRuleTemplateApply(BaseModel):
    template_type: str
    is_active: bool

class WatchlistAlertRuleTemplateBulkRequest(BaseModel):
    templates: list[WatchlistAlertRuleTemplateApply]
```

기존 클래스는 변경하지 않는다.

**`app/api/v1/endpoints/watchlists.py`**

엔드포인트 2개 추가:

```
GET  /{watchlist_id}/alert-rule-templates
  Response: ApiResponse[list[WatchlistAlertRuleTemplateProjection]]
  Auth: 인증 필요
  Handler: WatchlistAlertRuleService(db).get_template_statuses(watchlist_id, current_user.id)

PUT  /{watchlist_id}/alert-rule-templates
  Body: WatchlistAlertRuleTemplateBulkRequest
  Response: ApiResponse[list[WatchlistAlertRuleTemplateProjection]]
  Auth: 인증 필요
  Handler: WatchlistAlertRuleService(db).apply_templates(watchlist_id, current_user.id, data)
```

패턴: `get_watchlist_evaluations`(watchlists.py:223) 선례와 동일한 구조.
`WatchlistAlertRuleService`를 import에 추가한다.

**`alembic/versions/<new_revision>_create_watchlist_alert_rules.py`** (신규)

구현 전 최신 migration revision을 확인한다:
```
alembic history --verbose | head -5
```
확인된 최신 revision을 `down_revision`으로 설정한다.

```python
def upgrade() -> None:
    op.create_table(
        "watchlist_alert_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("watchlist_id", sa.Integer(), sa.ForeignKey("watchlists.id"),
                  nullable=False, index=True),
        sa.Column("template_type", sa.String(50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("watchlist_id", "template_type",
                            name="uq_watchlist_alert_rules_template"),
    )

def downgrade() -> None:
    op.drop_table("watchlist_alert_rules")
```

## Out of Scope

- FE 빠른 감시 설정 패널 (`project_stock_frontend#120`)
- 실제 알림 발송 채널(푸시·이메일)
- 스케줄러 신설
- 평가 기반 상태 전이 감지 및 Signal 생성 (Phase 2 후속 이슈)
- `watchlist_evaluation_snapshots` 테이블 생성 (Phase 2)
- `PRICE_SPIKE` 실시간 가격 폴링
- 기존 파일의 리팩터링·네이밍 변경

## Protected Files

없음. 보호 파일을 수정하지 않는다.

## Requirements

- 'DTO' 용어 금지. 응답 뷰 타입은 `Projection` 접미사를 사용한다.
- `template_type` 값은 반드시 `WatchlistAlertTemplateType` enum에 정의된 값만 허용한다.
  enum 외 값 입력 시 422를 반환한다.
- `GET` 응답은 DB에 행이 없는 템플릿도 포함해 항상 4종을 반환한다.
- `PUT`은 요청에 포함된 템플릿만 upsert하고, 포함되지 않은 템플릿의 현재 상태는 유지한다.
- 소유권이 다른 watchlist 접근 시 403, 존재하지 않는 watchlist 접근 시 404.
- 기존 `/summary`, `/evaluations`, `/observations`, `/recommendations`, `/sparklines`
  응답 계약을 변경하지 않는다.
- DB migration의 `down_revision`은 실제 현재 최신 revision에서 확인한 값을 사용한다.
  추측으로 작성하지 않는다.

## Test Requirements

**`tests/test_watchlist_alert_rule_templates.py`** (신규):

- `get_template_statuses`: 규칙 미설정 시 4종 모두 `is_active=False` 반환
- `get_template_statuses`: 일부 활성화 후 해당 템플릿만 `is_active=True` 반환
- `apply_templates`: 1종 단독 upsert — 해당 템플릿 상태 변경, 나머지 3종은 기본값 유지
- `apply_templates`: 4종 동시 upsert (True/False 혼합)
- `apply_templates`: 동일 템플릿 중복 호출 시 UniqueConstraint 위반 없이 `is_active`가
  마지막 값으로 갱신됨
- 소유권 검증: 타인 watchlist 접근 시 403
- 존재하지 않는 watchlist 접근 시 404
- `GET /{watchlist_id}/alert-rule-templates` 엔드포인트 통합 테스트 (200, 응답 구조 확인)
- `PUT /{watchlist_id}/alert-rule-templates` 엔드포인트 통합 테스트 (200, upsert 반영 확인)
- 픽스처 enum 값은 `app/domains/watchlists/types.py`에서 직접 인용하고
  `# Enum values are sourced from app/domains/watchlists/types.py.` 주석을 추가한다

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

구현 완료 후 `docs/designs/237-quick-watch-templates.md`의 Status를 `Implemented`로 갱신한다.

## ADR Need

불필요하다. 신규 테이블 추가는 설계 문서에서 충분히 기록된다.

## Failure Record Need

불필요하다.

## Risk Level

Medium — 신규 테이블·migration·endpoint를 추가하며 기존 watchlist endpoint를 수정한다.
`WatchlistAlertRuleRepository.upsert_template`의 중복 처리 방식이 잘못 구현되면
UniqueConstraint 위반이 발생할 수 있으므로, DB upsert 로직을 구현 후 반드시 중복 시나리오
테스트로 검증한다. 또한 mypy는 `Mapped[bool]`의 `server_default` 타입에 민감하므로
기존 Boolean 컬럼 선례(`app/domains/watchlists/model.py`)를 확인 후 맞춘다.

## Expected Output

- 신규·수정 파일 목록 보고
- 검증 3종(`ruff` / `mypy` / `pytest`) 실행 결과 보고
- 설계 Verified Facts 인용 위치의 실제 코드 일치 여부 보고
- alembic `down_revision` 결정 근거(실제 실행 값) 보고
- 가정·잔여 위험 보고

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 브랜치 `feat/237-quick-watch-templates`에서 작업한다. 새 브랜치를 생성하지 않는다.
- PR은 `dev` 브랜치를 대상으로 한다 (`main` 대상 금지).
- 커밋하지 않는다.
