# 04. 수직 슬라이스 표준형 — watchlists

대상 파일: `app/domains/watchlists/*`, `app/api/v1/endpoints/watchlists.py`

38개 도메인이 모두 같은 골격을 씁니다. `watchlists`는 그 골격에 더해 "도메인이 커지면 어떻게
쪼개지는가"까지 보여주기 때문에 표준형으로 삼기에 좋습니다.

## 도메인 파일 구성

```text
model.py                   테이블 3개
schema.py                  Pydantic 스키마 21개
repository.py              repository 클래스 3개
types.py                   파이썬 enum 6개
service.py                 핵심 CRUD + 요약        (305줄)
trend_service.py           요약 추이
sparkline_service.py       가격 스파크라인
observations_service.py    AI 관찰 노트
evaluations_service.py     AI 평가 배지
recommendations_service.py AI 종목 추천
alert_rule_service.py      알림 규칙 템플릿
```

기본 4종(`model` / `schema` / `repository` / `service`)에 `types.py`가 붙고, **service가 기능별로
분화**했습니다. 한 파일에 몰아넣으면 1,000줄이 넘고 LLM을 쓰는 코드와 순수 CRUD가 뒤섞입니다.
분리 기준은 **응답 하나 = service 하나**에 가깝습니다.

계층 간 의존 방향은 단방향입니다.

```text
endpoint  →  service  →  repository  →  model
   ↓            ↓
 schema      schema
```

`repository`는 `schema`를 모르고(ORM 객체만 다룸), `service`는 HTTP를 모르며(`Request`를 받지
않음), `endpoint`는 SQLAlchemy를 모릅니다(`db`를 그대로 넘기기만 함).

## model.py — 테이블 3개

```python
class WatchlistItem(Base, TimestampMixin):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("watchlist_id", "asset_id", name="uq_watchlist_items_asset"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id"))
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    priority: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
```

`__table_args__`는 컬럼이 아닌 테이블 수준 제약을 담는 자리입니다. **튜플이므로 원소가 하나여도
뒤에 콤마가 필요**합니다(빠뜨리면 괄호가 그냥 묶음으로 해석되어 조용히 무시됩니다).

`default`와 `server_default`를 둘 다 준 것이 눈여겨볼 부분입니다.

- `default=0` — **SQLAlchemy**가 INSERT 문을 만들 때 값을 채웁니다. ORM 경로에만 적용됩니다.
- `server_default="0"` — **DB**의 DDL 기본값입니다. 직접 SQL INSERT에도 적용됩니다.

둘 다 두는 것은 ORM과 직접 SQL 양쪽에서 같은 기본값을 보장하려는 이중화입니다. 03단계에서 본
`onupdate`가 ORM 경로에만 적용되는 것과 같은 구도입니다.

`tags: Mapped[list[str]] = mapped_column(JSON, default=list, ...)`에서 `default=list`가 중요합니다.
**`default=[]`가 아니라 `list`(호출 가능 객체)** 입니다. 파이썬의 가변 기본값 함정 — 리터럴을 주면
모든 행이 같은 리스트 객체를 공유합니다 — 을 피하는 표준 방법입니다.

`tags`를 별도 테이블이 아니라 JSON 컬럼으로 둔 것은 03단계에서 본 거래입니다. 태그로 검색·집계할
일이 없다면 조인 없는 JSON이 단순합니다. 나중에 "태그별 종목 수" 같은 요구가 생기면 정규화가
필요해집니다.

### `relationship()`이 하나도 없다

세 모델 어디에도 SQLAlchemy `relationship()` 선언이 없습니다. `watchlist.items`처럼 객체를 타고
들어가는 접근이 불가능하고, **연관 데이터는 repository가 명시적으로 조인하거나 service가 따로
조회해서 조립**합니다.

장단이 분명합니다.

- 얻는 것 — lazy loading이 없으므로 "응답 직렬화 중에 예상치 못한 쿼리가 나가는" 사고가
  구조적으로 불가능합니다. 세션이 닫힌 뒤 객체를 만져도 `DetachedInstanceError`가 나지 않습니다.
- 잃는 것 — 연관 조회를 손으로 써야 하고, 뒤에서 볼 N+1을 개발자가 직접 막아야 합니다.

## schema.py — 스키마 명명 규칙

21개 스키마가 세 부류로 나뉘고, **이름의 접미사가 곧 역할**입니다.

| 접미사 | 방향 | 예 |
| --- | --- | --- |
| `~Create`, `~Request`, `~Apply` | 요청 | `WatchlistCreate`, `WatchlistAlertRuleTemplateBulkRequest` |
| `~Response` | 응답 (테이블 1:1에 가까움) | `WatchlistResponse`, `WatchlistItemResponse` |
| `~Projection` | 응답 (계산·조합된 파생 뷰) | `BuyReadinessProjection`, `StockRecommendationProjection` |

**`Projection`이라는 이름이 이 프로젝트의 규칙입니다.** 흔히 쓰는 `DTO`를 쓰지 않는데, `schema`는
HTTP 요청·응답을, `payload`는 LLM 요청 내용을 이미 가리키고 있어 용어 충돌을 피하려는
선택입니다(ADR-009). 테이블을 그대로 비추면 `Response`, 여러 소스를 조합해 만든 뷰면 `Projection`
으로 읽으면 됩니다.

```python
class WatchlistCreate(BaseModel):
    name: str = Field(max_length=255)
```

`Field(max_length=255)`는 **모델의 `String(255)`와 짝**입니다. 없으면 256자짜리 이름이 DB까지 가서
`DataError`(미처리 500)로 터집니다. 있으면 422로 친절하게 거절됩니다. **DB 제약과 스키마 제약을
같이 맞추는 것**이 규칙입니다.

```python
class WatchlistItemCreate(BaseModel):
    asset_id: int
    priority: int = 0
    tags: list[str] = Field(default_factory=list)
```

Pydantic에서도 가변 기본값은 `Field(default_factory=list)`로 씁니다. 모델의 `default=list`와 같은
이유입니다.

```python
class WatchlistItemExpandedResponse(BaseModel):
    ...                          # WatchlistItemResponse의 모든 필드를 반복
    status: str
    asset: AssetBriefResponse | None = None
```

`WatchlistItemResponse`를 상속하지 않고 **필드를 그대로 복사**했습니다. 상속하면 부모 변경이
자식에 자동 전파되는데, 응답 스키마는 외부 계약이라 "부모를 고쳤더니 다른 API 응답이 조용히
바뀌는" 상황이 더 위험하다는 판단입니다. 중복을 감수하고 계약을 고정한 것입니다.

## repository.py — 쿼리 계층

### `db.get()` vs `select()`

```python
    def get_by_id(self, watchlist_id: int) -> Watchlist | None:
        return self.db.get(Watchlist, watchlist_id)
```

`Session.get()`은 **기본키 전용 조회**이며, 세션의 아이덴티티 맵을 먼저 확인해 **이미 로드된
객체면 SQL을 아예 보내지 않습니다.** 기본키로 찾을 때는 `select().where(id == ...)`보다 이쪽이
정석입니다. 02단계 `UserRepository.get_by_id`가 `select`를 쓴 것과 다른데, 이 파일이 더 관용적인
형태입니다.

### 정렬 화이트리스트가 두 겹

```python
    def _apply_sort(self, stmt, sort: str):
        if sort == "-priority":
            return stmt.order_by(WatchlistItem.priority.desc(), WatchlistItem.id.desc())
        if sort == "created_at":
            return stmt.order_by(WatchlistItem.created_at, WatchlistItem.id)
        if sort == "-created_at":
            return stmt.order_by(WatchlistItem.created_at.desc(), WatchlistItem.id.desc())
        return stmt.order_by(WatchlistItem.priority, WatchlistItem.id)
```

02단계의 `sort_param(allowed_fields=...)`이 이미 값을 검증했는데 여기서 또 명시적 분기를 씁니다.
문자열을 `getattr(WatchlistItem, field)`로 동적 변환하지 않는 것이 핵심입니다 — **컬럼 이름이
문자열로 SQL에 들어갈 경로 자체를 없앤 것**입니다.

모든 분기에 `id`가 2차 정렬로 붙어 있는 점도 중요합니다. `priority`가 같은 행이 여럿일 때
**순서가 매 요청마다 달라지면 페이지네이션에서 행이 중복되거나 누락**됩니다. 정렬 키에 항상
유니크한 컬럼을 마지막에 붙이는 것은 페이지네이션의 기본 규칙입니다.

### 예외를 삼키지 않고 되던지기

```python
    def create(self, ...) -> WatchlistItem:
        item = WatchlistItem(...)
        self.db.add(item)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise
```

`rollback()`이 반드시 필요합니다. PostgreSQL은 트랜잭션 안에서 에러가 나면 **그 트랜잭션을
"aborted" 상태로 만들어 이후 모든 쿼리를 거부**합니다. 롤백하지 않으면 같은 요청의 다음 쿼리가
`InFailedSqlTransaction`으로 연쇄 실패합니다.

`raise`로 되던지는 것은 **HTTP 관심사를 repository가 결정하지 않겠다**는 뜻입니다. `IntegrityError`를
어떤 상태코드로 바꿀지는 service가 정합니다.

### upsert와 경합 처리

```python
    def upsert_template(self, watchlist_id, template_type, is_active) -> WatchlistAlertRule:
        rule = self.db.scalars(stmt).first()
        if rule is None:
            rule = WatchlistAlertRule(...)
            self.db.add(rule)
        else:
            rule.is_active = is_active
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            rule = self.db.scalars(stmt).one()   # 그 사이 남이 만든 행을 다시 조회
            rule.is_active = is_active
            self.db.commit()
```

"조회 → 없으면 생성"은 전형적인 경합 구간입니다. 두 요청이 동시에 "없음"을 확인하면 둘 다 INSERT를
시도하고, 유니크 제약 덕분에 하나가 `IntegrityError`로 실패합니다. 그때 **롤백 후 다시 조회해
UPDATE로 전환**합니다. 03단계에서 말한 "service는 친절한 메시지, DB는 최종 보장"의 실제 사례입니다.

두 번째 조회에서 `.first()`가 아니라 `.one()`을 쓴 것도 의도적입니다. 여기서 행이 없다면 유니크
위반이 아닌 다른 원인이므로 조용히 넘기지 말고 터져야 합니다.

## service.py — 비즈니스 규칙

### 소유권 검사

```python
    def _get_owned_watchlist(self, watchlist_id: int, user_id: int) -> Watchlist:
        watchlist = self.watchlist_repo.get_by_id(watchlist_id)
        if watchlist is None:
            raise AppException(404, "관심 목록을 찾을 수 없습니다.", ErrorCode.WATCHLIST_NOT_FOUND)
        if watchlist.user_id != user_id:
            raise AppException(403, "관심 목록 접근 권한이 없습니다.", ErrorCode.WATCHLIST_FORBIDDEN)
        return watchlist
```

**이 프로젝트에서 가장 자주 반복되는 패턴입니다.** 사용자 데이터를 다루는 거의 모든 service에
같은 형태의 `_get_owned_*` 헬퍼가 있습니다.

`watchlist_id`를 받는 public 메서드는 **예외 없이 첫 줄에서 이것을 호출**합니다(`add_item`,
`list_items`, `get_summary`, `remove_item` 등). 새 메서드를 추가할 때 이 한 줄을 빠뜨리면 곧바로
다른 사용자의 데이터가 노출되므로, 리뷰에서 가장 먼저 확인해야 할 지점입니다.

404와 403을 구분하는 선택도 짚어둘 만합니다. 남의 관심목록에 접근하면 403이 나오므로 **그
ID가 존재한다는 사실은 알려집니다.** 02단계의 인증에서는 원인을 감췄던 것과 대비되는데,
관심목록 ID의 존재 여부는 민감도가 낮다는 판단입니다.

### 중복을 두 번 막는다

```python
        if self.item_repo.get_by_watchlist_asset(watchlist.id, data.asset_id):
            raise AppException(400, "이미 관심 목록에 추가된 종목입니다.",
                               ErrorCode.WATCHLIST_ITEM_DUPLICATE)
        try:
            item = self.item_repo.create(...)
        except IntegrityError as exc:
            raise AppException(400, "이미 관심 목록에 추가된 종목입니다.",
                               ErrorCode.WATCHLIST_ITEM_DUPLICATE) from exc
```

앞의 조회는 **일반적인 경우의 친절한 응답**, 뒤의 `except`는 **동시 요청 경합의 최종 방어**입니다.
조회와 INSERT 사이에 다른 요청이 끼어들면 앞의 검사는 통과하고 DB 제약이 잡습니다. 사용자에게는
같은 400이 나가므로 경합 여부와 무관하게 동작이 일관됩니다.

`raise ... from exc`는 예외 체인을 유지해 로그에 원인이 남게 합니다.

### service가 다른 도메인을 조합한다

```python
class WatchlistService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.asset_repo = AssetRepository(db)
        self.portfolio_repo = PortfolioRepository(db)
        self.signal_repo = SignalRepository(db)
        self.watchlist_repo = WatchlistRepository(db)
        self.item_repo = WatchlistItemRepository(db)
```

**service는 다른 도메인의 repository를 직접 씁니다.** 5개 repository가 모두 같은 `db` 세션을 공유하고,
그 세션은 02단계의 `get_db` 의존성이 요청당 하나만 만들어 줍니다.

한 곳에서는 다른 도메인의 **service**까지 부릅니다.

```python
        portfolio_summary = PortfolioService(self.db).get_summary(resolved_portfolio_id, user_id)
```

repository를 부르면 계산 로직을 여기서 다시 구현해야 하므로, 계산이 필요한 경우 service를 부르는
것이 맞습니다. 다만 이 방향(watchlists → portfolios)이 늘어나면 순환 import 위험이 생기므로
`import` 위치와 방향을 볼 때 주의해야 합니다.

`from app.domains.portfolios.service import CASH_FLOOR_HIGH, CASH_FLOOR_MEDIUM`처럼 **임계값 상수를
정의한 도메인에서 가져다 쓰는 것**도 규칙입니다. 같은 숫자를 두 곳에 적어두면 반드시 어긋납니다.

### 화폐·비율은 Decimal

```python
    def _buy_readiness_level(self, cash_weight: Decimal) -> BuyReadinessLevel:
        if cash_weight >= CASH_FLOOR_MEDIUM:
            return BuyReadinessLevel.SUFFICIENT
```

`float`이 아니라 `Decimal`입니다. `0.1 + 0.2 != 0.3`인 부동소수점 오차가 금액·비율 비교에서
경계값 오판을 만들기 때문입니다. `AssetBriefResponse`가 `price: str`, `change_percent: str`로
**문자열**을 쓰는 것도 같은 맥락 — JSON에 숫자로 내보내면 JavaScript의 `number`(배정도
부동소수점)로 변환되면서 정밀도가 깨집니다. 문자열로 보내면 프런트가 원본 그대로 받습니다.

### walrus 연산자로 조립

```python
            recent_items=[
                RecentWatchlistItemResponse(symbol=asset.symbol, name=asset.name,
                                            created_at=item.created_at)
                for item in recent_items
                if (asset := assets.get(item.asset_id)) is not None
            ],
```

`:=`(walrus)로 **필터링과 값 바인딩을 한 번에** 합니다. asset을 못 찾은 항목은 조용히 빠집니다.
데이터 정합성이 깨진 경우(FK가 있으니 실제로는 드묾)에 500 대신 부분 응답을 택한 것입니다.

### N+1 쿼리가 실재한다

```python
        asset_ids = [item.asset_id for item in items]
        assets = {
            asset.id: asset
            for asset in [self.asset_repo.get_by_id(aid) for aid in asset_ids]
            if asset is not None
        }
```

**항목 수만큼 `get_by_id`를 반복 호출합니다.** 20개면 목록 조회 1번 + 종목 조회 20번입니다.
`WHERE id IN (...)`을 쓰는 repository 메서드 하나면 2번으로 줄어듭니다.

`db.get()`이 아이덴티티 맵 캐시를 쓰므로 같은 asset이 반복되면 SQL이 줄긴 하지만, 서로 다른
종목이 대부분인 관심목록에서는 완화되지 않습니다. 앞에서 본 "`relationship()`을 쓰지 않는" 설계의
비용이 드러나는 지점입니다 — lazy loading 사고는 막았지만, 배치 조회는 손으로 챙겨야 합니다.

바로 아래 줄은 반대로 잘 되어 있습니다.

```python
        quotes = {q.symbol: q for q in get_market_provider().get_quote(symbols)} if symbols else {}
        active_types = self.signal_repo.active_signal_types_by_asset(asset_ids)
```

외부 시세 조회와 시그널 조회는 **심볼 목록·ID 목록을 한 번에 넘기는 배치 호출**입니다. 외부 API는
왕복 비용이 눈에 보여서 처음부터 배치로 설계되고, DB는 빨라 보여서 루프가 남는 전형적인 양상입니다.

### 트랜잭션 경계의 한계

`add_item`을 보면 **`item_repo.create`가 스스로 커밋**합니다(03단계). 만약 항목 추가와 동시에 다른
테이블도 갱신해야 한다면, 앞의 커밋은 이미 확정된 뒤라 뒤가 실패해도 되돌릴 수 없습니다.

현재 이 프로젝트가 감당 가능한 이유는 대부분의 쓰기가 **단일 테이블 단위**이기 때문입니다. 여러
테이블을 원자적으로 바꿔야 하는 곳(09단계 알림 엔진)에서는 service가 세션을 직접 다뤄야 합니다.

## endpoints/watchlists.py — HTTP 계층

### 의존성 3종 세트

```python
def create_watchlist(
    data: WatchlistCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[WatchlistResponse]:
    return success(WatchlistService(db).create_watchlist(current_user.id, data))
```

인증이 필요한 모든 엔드포인트가 `db` + `current_user` 조합을 받습니다. 02단계에서 본 대로
`get_current_user`가 내부적으로 `get_db`를 쓰지만, **요청 스코프 캐싱** 덕분에 세션은 하나만
만들어집니다.

`current_user.id`를 service에 넘기는 것이 핵심 계약입니다. **service는 `User` 객체가 아니라
`user_id`만 받습니다** — 인증 방식이 바뀌어도 service는 영향받지 않습니다.

### `Annotated[X, Depends()]` — 빈 Depends

```python
def list_watchlists(
    pagination: Annotated[PaginationParams, Depends()],
    ...
```

`Depends()`에 인자가 없습니다. FastAPI는 이 경우 **타입 어노테이션(`PaginationParams`)을 그대로
의존성으로 사용**합니다. `Depends(PaginationParams)`라고 써도 같지만 이름을 두 번 쓰지 않는 쪽이
관용적입니다.

`Annotated[...]` 형식과 `= Depends(...)` 형식이 이 파일에 섞여 있습니다. `Annotated`가 FastAPI 최신
권장 방식이고(기본값 자리를 비워둘 수 있어 재사용에 유리), `= Depends(...)`는 기존 방식입니다.
동작은 같습니다.

```python
watchlist_item_sort = sort_param(allowed_fields={"priority", "created_at"}, default="priority")
...
    sort: Annotated[SortParams, Depends(watchlist_item_sort)],
```

02단계의 의존성 팩토리를 **모듈 수준에서 한 번만 호출**해 재사용합니다. 데코레이터 안에서 매번
호출하면 요청마다 새 클로저가 생기고, 팩토리가 하는 기동 시점 자기검증의 의미도 흐려집니다.

### 쿼리 파라미터 세 가지 형태

```python
    recent_limit: int = Query(default=5, ge=0, le=50),
    portfolio_id: int | None = Query(default=None),
    days: Annotated[int, Query(ge=1, le=90)] = 14,
```

전부 쿼리 파라미터입니다. 범위 제약(`ge`/`le`)이 붙어 있어 위반 시 422가 나가고, `/docs`에도
제약이 표시됩니다. **상한선(`le=50`, `le=90`)은 클라이언트가 과도한 계산을 요구하지 못하게 막는
방어선**입니다.

```python
    sparkline_range: Annotated[
        Literal["1M", "3M", "6M", "1Y", "1D"],
        Query(alias="range"),
    ] = "1M",
```

두 가지 기법이 겹쳐 있습니다.

- **`alias="range"`** — URL에는 `?range=3M`으로 받고 파이썬 변수는 `sparkline_range`입니다. `range`는
  파이썬 내장 함수 이름이라 파라미터명으로 쓰면 가려지므로, 외부 계약과 내부 이름을 분리했습니다.
- **`Literal[...]`** — 허용값을 타입으로 못박습니다. 다른 값이 오면 422이고, OpenAPI에는 `enum`으로
  나가 `/docs`에 드롭다운이 생깁니다. 문자열을 받아 service에서 검사하는 것보다 훨씬 낫습니다.

### 하나의 엔드포인트가 두 가지 응답을 내는 곳

```python
@router.get(
    "/{watchlist_id}/items",
    response_model=ApiResponse[list[Any]],     # ← Any
)
def list_watchlist_items(..., expand: str | None = Query(default=None, ...)) -> Any:
    if expand is not None and "asset" in [e.strip() for e in expand.split(",")]:
        expanded_items = service.list_items_expanded(...)
        return paginated(expanded_items, ...)
    plain_items = service.list_items(...)
    return paginated(plain_items, ...)
```

`?expand=asset`이면 시세가 붙은 항목을, 아니면 기본 항목을 돌려줍니다. GraphQL 스타일의 `expand`
관례를 REST에 얹은 것입니다.

**대가가 명확합니다.** `response_model=ApiResponse[list[Any]]`이므로 `/docs`에 `data` 배열의 실제
필드가 하나도 나오지 않고, 1단계에서 본 **응답 검증과 필드 필터링도 사실상 무력화**됩니다.
`response_model`이 주던 세 가지 이점(검증·유출 방지·문서화)을 모두 포기한 것입니다.

대안은 `Union[list[A], list[B]]`을 `response_model`로 주거나(OpenAPI에 `anyOf`로 표현됨), 경로를
`/items`와 `/items/expanded`로 분리하는 것입니다. **읽을 때는 이 엔드포인트만 문서가 비어 있다는
점을 기억**해 두면 됩니다.

`expand` 파싱이 `"asset" in [e.strip() for e in expand.split(",")]`로 인라인 처리된 점도 눈에
띕니다. 확장 필드가 늘어나면 헬퍼로 빼야 할 자리입니다.

### 커밋 이후에 워커 큐 넣기

```python
def add_watchlist_item(...):
    item = WatchlistService(db).add_item(watchlist_id, current_user.id, data)
    enqueue_watchlist_analysis_safe(watchlist_id)
    return success(item)
```

항목을 추가한 뒤 **분석 잡을 큐에 넣습니다.** 순서가 중요합니다. `add_item`이 이미 커밋했으므로
워커가 즉시 집어가도 데이터가 보입니다. 반대로 넣었다면 워커가 아직 없는 행을 읽을 수 있습니다.

함수명의 `_safe` 접미사가 계약을 드러냅니다 — **큐 적재가 실패해도 예외를 던지지 않습니다.**
Redis가 죽어 있어도 관심목록 추가라는 주 기능은 성공해야 하기 때문입니다. 부가 작업이 주 작업을
망가뜨리지 않게 하는 패턴이며, 08단계에서 구현을 봅니다.

FastAPI의 `BackgroundTasks`를 쓰지 않은 것도 짚어둘 만합니다. `BackgroundTasks`는 같은 프로세스에서
실행되므로 서버가 재시작하면 유실되고, 무거운 작업이면 워커 스레드를 잡아먹습니다. 별도 워커
프로세스로 보내는 것이 이 프로젝트의 선택입니다.

### DELETE가 204를 쓰지 않는다

```python
@router.delete("/{watchlist_id}/items/{item_id}", response_model=ApiResponse[None])
def remove_watchlist_item(...) -> ApiResponse[None]:
    WatchlistService(db).remove_item(watchlist_id, item_id, current_user.id)
    return success(None)
```

REST 관례라면 204 No Content가 자연스럽지만, 여기서는 200 + `{"data": null, ...}`을 돌려줍니다.
**공통 봉투 규칙을 우선한 것**입니다. 204는 본문이 없어야 하므로 봉투를 실을 수 없고, 그러면
프런트엔드가 이 엔드포인트만 다르게 처리해야 합니다. 일관성을 REST 관례보다 위에 둔 선택입니다.

### 경로 파라미터

```python
def get_watchlist_summary(watchlist_id: int, ...)
```

`watchlist_id`가 경로 템플릿 `/{watchlist_id}`에 있으므로 FastAPI가 **경로 파라미터로 인식하고
`int`로 변환**합니다. `/watchlists/abc/summary`처럼 숫자가 아니면 service에 닿기 전에 422가
나갑니다. 타입 어노테이션 하나가 검증기 역할을 합니다.

## 요청 흐름 — `POST /api/v1/watchlists/{id}/items`

```text
1. 라우팅        /api/v1 → /watchlists → post("/{watchlist_id}/items")
2. 경로 검증     watchlist_id: int 변환 (실패 시 422)
3. 의존성        get_db → 세션 1개
                 get_current_user → 토큰 검증 → User 조회 (같은 세션 재사용)
4. 본문 검증     WatchlistItemCreate (실패 시 422)
5. service       WatchlistService(db).add_item(...)
   5-1 소유권    _get_owned_watchlist → 404 / 403
   5-2 종목 존재 asset_repo.get_by_id → 404 ASSET_NOT_FOUND
   5-3 중복      item_repo.get_by_watchlist_asset → 400 WATCHLIST_ITEM_DUPLICATE
   5-4 생성      item_repo.create → INSERT + COMMIT
                 (경합 시 IntegrityError → 400으로 변환)
   5-5 변환      WatchlistItemResponse.model_validate(item)
6. 큐 적재       enqueue_watchlist_analysis_safe (실패해도 무시)
7. 응답          success(item) → response_model 검증 → 201
8. 정리          get_db finally → db.close()
```

## 이 단계에서 확인한 프로젝트 규칙

1. 도메인은 `model` / `schema` / `repository` / `service` 4종이 기본이고, enum은 `types.py`,
   커진 service는 기능별 파일로 분리한다.
2. 사용자 데이터를 다루는 service 메서드는 **첫 줄에서 `_get_owned_*` 소유권 검사**를 호출한다.
   없으면 데이터 유출이다.
3. 중복·경합은 두 겹으로 막는다. service의 사전 조회(친절한 메시지) + DB 유니크 제약과
   `IntegrityError` 변환(최종 보장).
4. 정렬은 문자열을 컬럼으로 동적 변환하지 않고 명시적 분기로 처리하며, 항상 유니크 컬럼을 2차
   정렬로 붙인다.
5. 스키마 이름은 `~Create`/`~Request`(요청), `~Response`(테이블 반영), `~Projection`(계산된 뷰).
   `DTO`는 쓰지 않는다.
6. 금액·비율은 `Decimal`로 계산하고 응답에는 문자열로 내보낸다.
7. 응답 스키마의 길이 제약은 모델의 컬럼 길이와 맞춘다.
8. 쓰기 후 부가 작업은 커밋 이후에, 실패해도 무시되는 `_safe` 형태로 호출한다.
9. `relationship()`을 쓰지 않으므로 연관 데이터는 배치 조회로 직접 모은다. 루프 안의 단건 조회는
   N+1이다.

## 알아둘 만한 개선 지점

- `list_items_expanded`와 `get_summary`의 `asset_repo.get_by_id` 루프는 N+1이다.
  `list_by_ids` 성격의 repository 메서드가 있으면 해소된다.
- `/items`의 `response_model=ApiResponse[list[Any]]`는 문서화·검증을 포기한 상태다.
- `add_item`처럼 repository가 각자 커밋하는 구조에서는 다중 테이블 원자성을 보장할 수 없다.

### 교차 도메인 순환 의존 5개

`app/domains/` 전체를 실측하면 37개 도메인에 교차 의존 간선이 94개이고, 그중 **양방향 순환이
5개** 있습니다. 의존은 대체로 조합 계층(`analysis`·`research_queue`·`alert_engine`·`llm_context`·
`dashboard`) → 기반 계층(`assets` 23회·`signals` 10회·`prices` 9회 참조당함) 방향으로 흐르지만,
아래 쌍들은 그 방향이 뒤집혀 있습니다.

| 순환 쌍 | 원인이 되는 import | 성격 |
| --- | --- | --- |
| `signals` ↔ `watchlists` | `signals/schema.py:12`, `signals/service.py:30`이 `watchlists.schema.AssetBriefResponse` 참조 | 계약 결합 |
| `prices` ↔ `watchlists` | `watchlists/sparkline_service.py:6`이 `prices.service._RANGE_INTERVALS`(비공개 상수) 참조 | 캡슐화 위반 |
| `alert_events` ↔ `alert_rules` | `alert_rules/repository.py`의 카운트 메서드 3개가 `AlertEvent`만 조회 | 배치 오류 |
| `news` ↔ `raw_news` | `raw_news/ingestion_service.py:28`이 `NewsNormalizationService`를 직접 생성 | 오케스트레이션 부재 |
| `benchmark` ↔ `prices` | `prices/universe.py:5`가 `benchmark.sector_map.resolve_sector_etf` 참조 | 위치 문제 |

각각을 짧게 보면 이렇습니다.

- **`AssetBriefResponse`** 는 이름 그대로 종목 요약이지 관심목록 전용이 아닙니다. `watchlists`에서
  먼저 필요해 거기 정의됐을 뿐인데, 기반 도메인인 `signals`가 조합 도메인의 **응답 계약**을 끌어다
  씁니다. `assets/schema.py`로 옮기면 양쪽 모두 기반 도메인을 참조하는 형태가 되어 순환이
  사라집니다.
- **`_RANGE_INTERVALS`** 는 `_`가 붙은 모듈 내부용 상수인데 도메인 경계를 넘어 import됩니다.
  `prices` 쪽 리팩터링이 `watchlists`를 조용히 깨뜨릴 수 있습니다.
- **`AlertRuleRepository`의 카운트 3종**(`count_events_triggered_since` 76행,
  `count_high_severity_events` 87행, `count_unread_events` 98행)은 `select_from(AlertEvent)`만 하고
  `AlertRule`을 전혀 건드리지 않습니다. `AlertEventRepository`로 옮기면 해소되는 단순 배치 오류이며,
  5건 중 가장 손쉽습니다.
- **뉴스 수집·정규화**는 수집 단계(`raw_news`)가 정규화 단계(`news`)를 자기 안에서 생성해 부르고,
  정규화 단계는 원본 모델을 읽어야 해서 양방향이 됩니다. 10단계에서 볼 `news_insights/pipeline.py`
  처럼 **단계를 순서대로 부르는 별도 오케스트레이터**를 두면 단계끼리 서로를 몰라도 됩니다.
- **`sector_map.py`** 는 20줄짜리 순수 매핑 테이블(섹터명 → 섹터 ETF 티커)입니다. `benchmark` 고유
  로직이라기보다 공용 참조 데이터에 가까워 위치만 옮기면 됩니다. 위험도는 가장 낮습니다.

교차 도메인 접근을 어디까지 허용할지는 별도 결정이 필요합니다. 현재 `WatchlistService`가 다른
도메인의 repository를 직접 쓰는 방식은 같은 세션(=같은 트랜잭션)을 공유한다는 실익이 있어
무조건 금지할 사안은 아닙니다. 논의와 선행 조치 목록은 이슈 #426에 있습니다.

## 다음 단계로 이어지는 질문

- `get_market_provider()`는 무엇을 돌려주며 mock과 real은 어떻게 갈리는가? (05·06단계)
- `AssetRepository`에는 배치 조회 메서드가 있는가? (05단계)
- 가격 데이터는 외부에서 직접 가져오는가, DB에 적재된 것을 읽는가? (05단계)
