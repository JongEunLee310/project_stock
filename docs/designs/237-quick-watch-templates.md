# Design: 빠른 감시 설정 — 관심종목 알림 규칙 템플릿 API (#237)

## Status

Implemented

## Revision History

| 버전 | 날짜 | 변경 내용 |
|---|---|---|
| R0 | 2026-07-08 | 초안 작성. |

## Context

FE 관심종목 페이지 우측 패널 "빠른 감시 설정"은 종목별 상세 규칙 빌더로 이동하지 않고,
관심목록 전체에 자주 쓰는 감시 조건을 원클릭으로 켜고 끄는 기능이다. 이 기능을 제공하는
BE 계약이 현재 없으므로 신규 설계한다.

템플릿 4종과 그 조건은 다음과 같다.

| 템플릿 | 식별자 | 조건 |
|---|---|---|
| 가격 급변 | `PRICE_SPIKE` | 일간 변동률 ±3% 이상 |
| 뉴스 위험도 상승 | `NEWS_RISK_HIGH` | `NewsRisk.HIGH` |
| AI 판단 변경 | `AI_JUDGMENT_CHANGE` | `AiJudgment` 상태 전이 발생 |
| 테마 과열 | `THEME_OVERHEAT` | `ThemeHeat.OVERHEATED` |

선행 이슈 #234(PR #236, `WatchlistEvaluationsService` 및 enum 4종 정의)가 머지되어
있으므로 enum 계약 충돌 없이 진행할 수 있다.

## Verified Facts (origin/dev, 2026-07-08 확인)

- `app/domains/watchlists/types.py:1-31` — `NewsRisk`, `ValuationBurden`, `ThemeHeat`,
  `AiJudgment`, `BuyReadinessLevel` enum 정의. `WatchlistAlertTemplateType`은 아직 없음,
  이번에 추가 필요.
- `app/domains/watchlists/model.py:7` — `Watchlist.__tablename__ = "watchlists"`, PK `id: int`.
- `app/domains/watchlists/model.py:15-27` —
  `WatchlistItem.__tablename__ = "watchlist_items"`,
  `UniqueConstraint("watchlist_id", "asset_id")` 선례.
- `app/domains/watchlists/evaluations_service.py:144-158` —
  `_get_owned_watchlist(watchlist_id, user_id)` 패턴:
  없으면 `ErrorCode.WATCHLIST_NOT_FOUND` 404, 타인 소유이면
  `ErrorCode.WATCHLIST_FORBIDDEN` 403.
- `app/domains/alerts/model.py:10-31` — `Alert`는 `signal_id: FK → signals` 필수.
  사용자가 직접 구성하는 "알림 규칙" 테이블은 현재 없음.
- `app/domains/signals/types.py:5-12` —
  `SignalType`: `WATCH`, `RISK_ALERT`, `THESIS_BROKEN`, `BUY_CANDIDATE`,
  `SELL_REVIEW`, `OVERHEATED`.
- `app/domains/watchlists/evaluations_service.py:52-106` —
  `WatchlistEvaluationsService.generate`는 온디맨드 LLM 호출이며
  결과를 DB에 저장하지 않는다.
- `app/api/v1/endpoints/watchlists.py:204-238` —
  child endpoint 패턴: `/{watchlist_id}/evaluations`, `/{watchlist_id}/observations` 등.
  모두 `ApiResponse[...]` envelope 사용.
- `app/core/error_codes.py:17,20` — `WATCHLIST_NOT_FOUND`, `WATCHLIST_FORBIDDEN` 이미 정의.
- `alembic/versions/f6005703a129_add_raw_news_symbol_market.py` —
  alembic 사용. revision ID는 hex 문자열, `down_revision` 체인 유지.

## Design Decisions

### 1. 템플릿 규칙 저장 방식 — 신규 테이블 `watchlist_alert_rules`

기존 `Alert` 모델은 `signal_id` FK가 필수이고 사용자 구성 규칙 개념이 없다.
`alert_candidates`(설계 035) 도메인은 템플릿 타입이나 관심목록 범위가 없어 재사용이
부적합하다. 기존 rule engine(설계 020)은 `RuleContext`(뉴스·가설·충돌 결과)를 입력받아
Signal을 생성하는 평가 파이프라인이며, 사용자가 CRUD로 관리하는 규칙 저장소가 아니다.

따라서 신규 테이블 `watchlist_alert_rules`를 watchlists 도메인에 추가한다. 한 행이
특정 관심목록에 대한 특정 템플릿 활성 상태를 나타낸다.

### 2. 평가 기반 템플릿 3종의 상태 전이 감지 — Phase 분리

`NEWS_RISK_HIGH`, `AI_JUDGMENT_CHANGE`, `THEME_OVERHEAT` 3종은 "이전 상태 대비 변화"를
감지해야 알림을 발생시킬 수 있다. 그런데 `WatchlistEvaluationsService.generate`는 온디맨드
호출이며 결과를 DB에 저장하지 않는다(`app/domains/watchlists/evaluations_service.py:52-106`).
과거 상태가 없으면 전이를 감지할 수 없다.

이 정합 문제를 해결하려면 마지막으로 평가된 배지 상태를 저장하는
`watchlist_evaluation_snapshots` 테이블이 필요하다. 단, 이번 이슈의 수용 기준은
"템플릿 4종 일괄 적용·해제 가능"이고 실제 알림 발생(Signal 생성)은 포함되지 않는다.
스케줄러 신설은 범위에서 제외된다.

따라서 이번 범위(Phase 1)는 **규칙 CRUD**에 집중하고, 상태 전이 감지는 다음 두 Phase로
분리한다.

- **Phase 1 (이번 이슈)**: `watchlist_alert_rules` CRUD API — 템플릿 적용·해제·상태 조회.
- **Phase 2 (후속 이슈)**: 평가 스냅샷 저장 + 전이 감지 — `GET /evaluations` 호출 시
  결과를 `watchlist_evaluation_snapshots` 테이블에 upsert하고, 활성 템플릿 조건에 해당하면
  Signal을 생성한다. Phase 2 스냅샷 테이블 스펙은 아래 Interfaces 절에 참고용으로 명시한다.

Phase 2에서 `PRICE_SPIKE` 템플릿은 시장 데이터(일간 변동률)를 별도로 폴링하거나,
`GET /evaluations` 흐름에 daily_change_percent 임계값 체크를 추가하는 방식으로 통합한다.

### 3. API 계약 — `alert-rule-templates` child endpoint

기존 watchlist child endpoint 패턴(watchlists.py:204 이하)을 따라 두 엔드포인트를 추가한다.
소유권 검증은 `_get_owned_watchlist` 패턴을 그대로 사용한다.

```
GET  /api/v1/watchlists/{watchlist_id}/alert-rule-templates
PUT  /api/v1/watchlists/{watchlist_id}/alert-rule-templates
```

`GET`은 4종 모두를 항상 반환한다. DB에 행이 없는 템플릿은 `is_active: false`로 응답한다.

`PUT`은 요청에 포함된 템플릿만 upsert하고, 포함되지 않은 템플릿은 현재 상태를 유지한다.
응답은 `GET`과 동일하게 4종 전체 상태를 반환한다.

### 4. 템플릿 식별자 enum

`app/domains/watchlists/types.py`에 `WatchlistAlertTemplateType`을 추가한다. 기존
`SignalType` 스타일(대문자 스네이크, `str, Enum`)을 따른다.

| 값 | 한국어 라벨 | 조건 요약 |
|---|---|---|
| `PRICE_SPIKE` | 가격 급변 | 일간 변동률 ±3% 이상 |
| `NEWS_RISK_HIGH` | 뉴스 위험도 상승 | `NewsRisk.HIGH` |
| `AI_JUDGMENT_CHANGE` | AI 판단 변경 | `AiJudgment` 상태 전이 |
| `THEME_OVERHEAT` | 테마 과열 | `ThemeHeat.OVERHEATED` |

## Interfaces

### `app/domains/watchlists/types.py` — WatchlistAlertTemplateType 추가

```
class WatchlistAlertTemplateType(str, Enum):
    PRICE_SPIKE = "PRICE_SPIKE"
    NEWS_RISK_HIGH = "NEWS_RISK_HIGH"
    AI_JUDGMENT_CHANGE = "AI_JUDGMENT_CHANGE"
    THEME_OVERHEAT = "THEME_OVERHEAT"
```

기존 enum 4종 및 `BuyReadinessLevel`은 변경 없음.

### `app/domains/watchlists/model.py` — WatchlistAlertRule 추가

신규 클래스:

```
class WatchlistAlertRule(Base, TimestampMixin):
    __tablename__ = "watchlist_alert_rules"
    __table_args__ = (
        UniqueConstraint(
            "watchlist_id", "template_type",
            name="uq_watchlist_alert_rules_template",
        ),
    )
    id: Mapped[int]          # PK
    watchlist_id: Mapped[int] # FK → watchlists.id, index
    template_type: Mapped[str] # String(50), WatchlistAlertTemplateType 값
    is_active: Mapped[bool]   # server_default=True
```

`TimestampMixin`은 기존 `Watchlist`, `WatchlistItem`과 동일하게 적용한다
(`app/domains/watchlists/model.py:7,15` 선례).

### Phase 2 참고: `watchlist_evaluation_snapshots` (이번 범위 外)

```
class WatchlistEvaluationSnapshot(Base):
    __tablename__ = "watchlist_evaluation_snapshots"
    __table_args__ = (
        UniqueConstraint("watchlist_id", "symbol",
                         name="uq_wl_eval_snapshot_wl_symbol"),
    )
    id: Mapped[int]            # PK
    watchlist_id: Mapped[int]  # FK → watchlists.id, index
    symbol: Mapped[str]        # String(20)
    news_risk: Mapped[str]     # String(20)
    theme_heat: Mapped[str]    # String(20)
    ai_judgment: Mapped[str]   # String(20)
    evaluated_at: Mapped[datetime]  # DateTime(tz)
```

row = (watchlist_id, symbol) 별 마지막 평가 상태만 저장한다. Phase 2에서
`WatchlistEvaluationsService.generate` 완료 후 upsert하고, 활성 템플릿 조건이
충족되면 Signal을 생성한다.

### `app/domains/watchlists/schema.py` — 신규 클래스

```
class WatchlistAlertRuleTemplateProjection(BaseModel):
    template_type: str            # WatchlistAlertTemplateType 값
    label: str                    # 한국어 라벨
    condition_description: str    # 조건 설명
    is_active: bool

class WatchlistAlertRuleTemplateApply(BaseModel):
    template_type: str            # WatchlistAlertTemplateType 값
    is_active: bool

class WatchlistAlertRuleTemplateBulkRequest(BaseModel):
    templates: list[WatchlistAlertRuleTemplateApply]
```

기존 schema 클래스(`WatchlistSummaryResponse` 등)는 변경 없음.

### `app/domains/watchlists/repository.py` — WatchlistAlertRuleRepository 추가

신규 클래스:

```
class WatchlistAlertRuleRepository:
    def __init__(self, db: Session) -> None
    def list_by_watchlist(self, watchlist_id: int) -> list[WatchlistAlertRule]
        # watchlist_id에 해당하는 모든 규칙 반환
    def upsert_template(
        self, watchlist_id: int, template_type: str, is_active: bool
    ) -> WatchlistAlertRule
        # UniqueConstraint ON CONFLICT UPDATE is_active
```

### `app/domains/watchlists/service.py` — WatchlistAlertRuleService 추가

신규 클래스 (기존 `WatchlistService`와 분리):

```
class WatchlistAlertRuleService:
    def __init__(self, db: Session) -> None
    def get_template_statuses(
        self, watchlist_id: int, user_id: int
    ) -> list[WatchlistAlertRuleTemplateProjection]
        # 소유 확인, 4종 모두 반환 (미설정 = is_active=False)
    def apply_templates(
        self, watchlist_id: int, user_id: int,
        data: WatchlistAlertRuleTemplateBulkRequest
    ) -> list[WatchlistAlertRuleTemplateProjection]
        # 소유 확인, 요청 포함 템플릿 upsert, 4종 전체 상태 반환
    def _get_owned_watchlist(
        self, watchlist_id: int, user_id: int
    ) -> Watchlist
        # evaluations_service.py:144 패턴과 동일
```

### API 엔드포인트 (`app/api/v1/endpoints/watchlists.py`)

```
GET /{watchlist_id}/alert-rule-templates
  Response: ApiResponse[list[WatchlistAlertRuleTemplateProjection]]
  Auth: 인증 필요
  Handler: WatchlistAlertRuleService(db).get_template_statuses(watchlist_id, current_user.id)

PUT /{watchlist_id}/alert-rule-templates
  Body: WatchlistAlertRuleTemplateBulkRequest
  Response: ApiResponse[list[WatchlistAlertRuleTemplateProjection]]
  Auth: 인증 필요
  Handler: WatchlistAlertRuleService(db).apply_templates(watchlist_id, current_user.id, data)
```

### DB Migration

alembic revision 신규 생성. `watchlist_alert_rules` 테이블을 `watchlists` 테이블 이후에
생성한다 (`down_revision`은 최신 revision ID `f6005703a129` 기준으로 확인 후 설정).

```
upgrade(): op.create_table("watchlist_alert_rules", ...)
downgrade(): op.drop_table("watchlist_alert_rules")
```

## Dependencies

### 신규

- `app/domains/watchlists/model` — `WatchlistAlertRule` (이번에 추가)
- `app/domains/watchlists/repository` — `WatchlistAlertRuleRepository` (이번에 추가)

### 기존 (유지)

- `app/domains/watchlists` — `WatchlistRepository`, `WatchlistItemRepository`
- `app/core.error_codes` — `WATCHLIST_NOT_FOUND`, `WATCHLIST_FORBIDDEN`

## Out of Scope

- FE 빠른 감시 설정 패널 (`project_stock_frontend#120`)
- 실제 알림 발송 채널(푸시·이메일)
- 스케줄러 신설
- 상태 전이 감지 및 Signal 생성 (Phase 2 후속 이슈)
- `watchlist_evaluation_snapshots` 테이블 생성 (Phase 2)
- `PRICE_SPIKE` 실시간 가격 폴링

## ADR Need

불필요하다. 신규 테이블 추가는 설계 문서로 충분히 기록된다. "기존 alert 모델 재사용
vs 신규 테이블" 판단은 기술적으로 자명하다 — 기존 `Alert`는 `signal_id` FK가 필수이고
사용자 구성 규칙 개념이 없으므로 재사용 불가, 대안이 없다.

## Test Strategy

### 신규·변경 테스트

- `WatchlistAlertRuleService.get_template_statuses` — 규칙 미설정 시 4종 모두 `is_active=False`
  반환, 일부 활성화 후 정확히 반영됨
- `WatchlistAlertRuleService.apply_templates` — 1종·4종 일괄 upsert, is_active True/False
  각각, 요청에 없는 템플릿은 현재 상태 유지
- 소유권 검증: 타인 watchlist 접근 시 403, 존재하지 않는 watchlist 시 404
- `GET /{watchlist_id}/alert-rule-templates` 통합 테스트
- `PUT /{watchlist_id}/alert-rule-templates` 통합 테스트 — 동일 template_type 중복 upsert 시
  UniqueConstraint 위반 없이 정상 처리
- enum 외 `template_type` 값 입력 시 422 반환
- 기존 watchlist endpoint 테스트 약화·삭제 금지

### 픽스처 출처 주석 규율

픽스처의 enum 값(`"PRICE_SPIKE"` 등)은 `app/domains/watchlists/types.py`에서 직접 인용하고
`# Enum values are sourced from app/domains/watchlists/types.py.` 주석을 추가한다.

## Open Questions

없음.
