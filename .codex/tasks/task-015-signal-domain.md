# Codex Handoff Task

## Source Issue

Issue #17: Signal 도메인 구현

## Task Summary

뉴스 요약·가설 충돌·리스크 레벨을 종합한 신호(Signal)를 `signals` 테이블에 저장하고, 생성·목록·상세 조회 API를 구현한다.

## Goal

- 신호를 생성·조회할 수 있다.
- Signal에는 유형, 점수, 리스크 레벨, 근거(JSON), 만료 시각이 포함된다.
- 만료된 Signal을 구분(`is_expired`)하고 목록에서 제외할 수 있다.

## Background

- **구현 전 `docs/designs/017-signal-domain.md`를 반드시 읽는다.**
- 본 도메인은 Rule Engine(#20)의 산출물 저장소이자 Alert(#18)의 입력이다. `exists_active`는 #20의 중복 방지 규칙에서 사용하므로 시그니처를 정확히 맞춘다.
- `evidence`는 JSON 문자열로 저장하고 응답 시 `dict`로 역직렬화한다(`reports` 도메인의 `field_validator` 패턴 참고).
- Signal은 불변이므로 `updated_at`을 두지 않는다(`TimestampMixin` 대신 `created_at`만 정의).
- 시작 전 `git checkout main && git pull` 후 최신 main에서 feature 브랜치를 생성한다. 현재 단일 head는 `7a8b9c0d1e23`.

## Implementation Scope

- `alembic/versions/<hash>_create_signals.py` — 신규 테이블 마이그레이션 (down_revision = 현재 head)
- `app/domains/signals/__init__.py`
- `app/domains/signals/types.py` — `SignalType(str, Enum)`
- `app/domains/signals/model.py` — `Signal` 모델
- `app/domains/signals/schema.py` — `SignalCreate`, `SignalResponse`
- `app/domains/signals/repository.py` — `SignalRepository`
- `app/domains/signals/service.py` — `SignalService`
- `app/api/v1/endpoints/signals.py` — API 엔드포인트
- `app/api/v1/router.py` — signals 라우터 등록
- `tests/test_signals.py`

## Out of Scope

- Signal 수정/삭제 API
- Rule Engine (Issue #20, 별도 태스크)
- Alert 생성 (Issue #18)
- Worker job 통합 (Issue #19)

## Protected Files

변경하지 않는 파일:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`, `docs/decisions/`

## Requirements

### Alembic 마이그레이션 — signals

```
id            INTEGER PK
asset_id      INTEGER FK(assets.id) NOT NULL INDEX
thesis_id     INTEGER FK(investment_theses.id) NULL
news_item_id  INTEGER FK(news_items.id) NULL
signal_type   VARCHAR(20) NOT NULL INDEX
score         INTEGER NOT NULL
risk_level    VARCHAR(20) NULL
reason        TEXT NOT NULL
evidence      TEXT NULL          -- JSON 문자열
expires_at    TIMESTAMPTZ NULL
created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
```

### SignalType

```python
class SignalType(str, Enum):
    WATCH = "WATCH"
    RISK_ALERT = "RISK_ALERT"
    THESIS_BROKEN = "THESIS_BROKEN"
    BUY_CANDIDATE = "BUY_CANDIDATE"
    SELL_REVIEW = "SELL_REVIEW"
    OVERHEATED = "OVERHEATED"
```

### 스키마

```python
class SignalCreate(BaseModel):
    asset_id: int
    thesis_id: int | None = None
    news_item_id: int | None = None
    signal_type: SignalType
    score: int
    risk_level: str | None = Field(default=None, max_length=20)
    reason: str
    evidence: dict[str, Any] | None = None
    expires_at: datetime | None = None

class SignalResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    asset_id: int
    thesis_id: int | None
    news_item_id: int | None
    signal_type: str
    score: int
    risk_level: str | None
    reason: str
    evidence: dict[str, Any] | None
    expires_at: datetime | None
    is_expired: bool
    created_at: datetime
```

- `evidence`에 DB의 JSON 문자열을 `dict`로 변환하는 `field_validator(mode="before")`를 추가한다.
- `is_expired`는 `expires_at`이 존재하고 현재 UTC 시각보다 과거면 `True`. `computed_field` 또는 `model_validator(mode="after")`로 산출한다. ORM 객체에는 `expires_at`만 있으므로 응답 변환 시 계산한다.

### SignalRepository

```python
class SignalRepository:
    def __init__(self, db: Session)
    def create(self, data: SignalCreate) -> Signal
    def get_by_id(self, signal_id: int) -> Signal | None
    def list_by_asset(self, asset_id: int, include_expired: bool) -> list[Signal]
    def exists_active(self, asset_id: int, signal_type: str, news_item_id: int | None) -> bool
```

- `create`: `evidence`를 `json.dumps(..., ensure_ascii=False)`로 직렬화 후 저장.
- `list_by_asset`: `created_at DESC, id DESC` 정렬. `include_expired=False`면 `expires_at IS NULL OR expires_at > now()`만 반환.
- `exists_active`: 동일 `asset_id`·`signal_type`·`news_item_id`이면서 미만료인 행이 있으면 `True`.

### SignalService

```python
class SignalService:
    def __init__(self, db: Session)
    def create_signal(self, data: SignalCreate) -> Signal
    def get_signal(self, signal_id: int) -> Signal          # 없으면 AppException(404)
    def list_signals(self, asset_id: int, include_expired: bool = False) -> list[Signal]
```

### API 엔드포인트 (app/api/v1/endpoints/signals.py)

```
POST   /api/v1/signals
       Request:  SignalCreate
       Response: SignalResponse (201)

GET    /api/v1/signals?asset_id={int}&include_expired={bool=false}
       Response: list[SignalResponse] (200)
       asset_id 누락 시 422

GET    /api/v1/signals/{signal_id}
       Response: SignalResponse (200), 없으면 404
```

모든 엔드포인트 인증 필요 — `deps.get_current_user` 사용.

### app/api/v1/router.py 변경

```python
from app.api.v1.endpoints import signals
router.include_router(signals.router, prefix="/signals", tags=["signals"])
```

## Test Requirements

`tests/test_signals.py`:

- `POST /api/v1/signals` — 정상 생성 201, `evidence`가 응답에서 `dict`로 반환
- `GET /api/v1/signals?asset_id={id}` — 목록 반환, 기본적으로 만료 신호 제외
- `include_expired=true` — 만료 신호 포함 검증
- `is_expired` — 과거 `expires_at` 신호는 `True`, 미래/`None`은 `False`
- `GET /api/v1/signals/{id}` — 상세 반환 / 없는 id 404
- `GET /api/v1/signals` — `asset_id` 누락 시 422
- `SignalRepository.exists_active` — 미만료 동일 신호 존재 시 `True`, 만료 신호는 `False`

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest tests/test_signals.py -v
```

## Documentation Impact

`docs/designs/017-signal-domain.md` 외 없음.

## ADR Need

없음. 기존 도메인 패턴을 따른다.

## Failure Record Need

없음.

## Risk Level

Medium — 신규 테이블 마이그레이션, 신규 API 라우터 등록 포함.

## Expected Output

- 위 scope 파일 신규 생성 + 마이그레이션
- `router.py`에 signals 라우터 추가
- lint/typecheck/test 통과

## Rules

- 구현 전 `docs/designs/017-signal-domain.md`를 읽는다.
- 최신 main에서 feature 브랜치를 만들고 시작한다.
- `evidence` 저장/조회는 `json.dumps`/`json.loads`.
- 기존 인증 방식(`deps.get_current_user`)을 따른다.
- 스코프 외 파일 변경 금지. 테스트 약화 금지. 보호 파일 변경 금지.
