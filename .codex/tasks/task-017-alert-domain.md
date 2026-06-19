# Codex Handoff Task

## Source Issue

Issue #18: Alert 도메인 구현

## Task Summary

중요 Signal로부터 사용자 내부 알림(Alert)을 생성·조회하고, 읽음/무시 처리 및 동일 이벤트 중복 방지를 구현한다.

## Goal

- 중요 Signal 발생 시 Alert가 생성된다.
- 사용자는 자신의 Alert 목록을 조회할 수 있다.
- 사용자는 Alert를 읽음 또는 무시 처리할 수 있다.
- 동일 뉴스로 중복 알림이 반복 생성되지 않는다.

## Background

- **구현 전 `docs/designs/018-alert-domain.md`와 `docs/designs/017-signal-domain.md`를 읽는다.**
- Signal 도메인(Issue #17, task-015)이 먼저 머지되어 있어야 한다.
- 1차 MVP는 외부 푸시 없이 내부 알림 목록만 구현한다.
- 중복 방지는 `UniqueConstraint(user_id, dedup_key)` + `IntegrityError` 처리로 구현한다.
- 시작 전 최신 main에서 feature 브랜치를 생성한다.

## Implementation Scope

- `alembic/versions/<hash>_create_alerts.py` — 신규 테이블 마이그레이션 (down_revision = 현재 head)
- `app/domains/alerts/__init__.py`
- `app/domains/alerts/types.py` — `AlertStatus(str, Enum)`
- `app/domains/alerts/model.py` — `Alert` 모델
- `app/domains/alerts/schema.py` — `AlertCreate`, `AlertResponse`
- `app/domains/alerts/repository.py` — `AlertRepository`
- `app/domains/alerts/service.py` — `AlertService`
- `app/api/v1/endpoints/alerts.py` — API 엔드포인트
- `app/api/v1/router.py` — alerts 라우터 등록
- `tests/test_alerts.py`

## Out of Scope

- 외부 푸시(웹푸시/이메일/슬랙)
- Signal 도메인 / Rule Engine
- Worker job 통합 (Issue #19)
- Alert 삭제 API

## Protected Files

변경하지 않는 파일:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`, `docs/decisions/`

## Requirements

### Alembic 마이그레이션 — alerts

```
id          INTEGER PK
user_id     INTEGER FK(users.id) NOT NULL INDEX
signal_id   INTEGER FK(signals.id) NOT NULL INDEX
status      VARCHAR(20) NOT NULL DEFAULT 'UNREAD'
dedup_key   VARCHAR(255) NOT NULL
created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
UNIQUE (user_id, dedup_key)   -- uq_alerts_user_dedup
```

### AlertStatus

```python
class AlertStatus(str, Enum):
    UNREAD = "UNREAD"
    READ = "READ"
    DISMISSED = "DISMISSED"
```

### 스키마

```python
class AlertCreate(BaseModel):
    user_id: int
    signal_id: int
    dedup_key: str

class AlertResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    user_id: int
    signal_id: int
    status: str
    created_at: datetime
```

### AlertRepository

```python
class AlertRepository:
    def __init__(self, db: Session)
    def create_if_absent(self, data: AlertCreate) -> Alert | None
    def get_by_id(self, alert_id: int) -> Alert | None
    def list_by_user(self, user_id: int, status: str | None) -> list[Alert]
    def update_status(self, alert: Alert, status: str) -> Alert
```

- `create_if_absent`: insert 후 `IntegrityError` 발생 시 `rollback`하고 `None` 반환(중복).
- `list_by_user`: `status` 지정 시 필터, `created_at DESC, id DESC` 정렬.

### AlertService

```python
class AlertService:
    def __init__(self, db: Session)
    def create_alert(self, user_id: int, signal: Signal) -> Alert | None
    def list_alerts(self, user_id: int, status: str | None = None) -> list[Alert]
    def mark_read(self, alert_id: int, user_id: int) -> Alert      # 없거나 타인 소유 시 AppException(404)
    def dismiss(self, alert_id: int, user_id: int) -> Alert        # 없거나 타인 소유 시 AppException(404)
```

- `create_alert`: `signal`로부터 `dedup_key`를 구성한다 — `f"{signal.signal_type}:{signal.news_item_id}"`. 중복이면 `None` 반환.
- `mark_read`/`dismiss`: 조회한 Alert의 `user_id`가 인자와 다르면 404(소유권 검증).

### API 엔드포인트 (app/api/v1/endpoints/alerts.py)

```
GET    /api/v1/alerts?status={AlertStatus=optional}
       Response: list[AlertResponse] (200), 현재 사용자 알림만

POST   /api/v1/alerts/{alert_id}/read
       Response: AlertResponse (200), 없거나 타인 소유 시 404

POST   /api/v1/alerts/{alert_id}/dismiss
       Response: AlertResponse (200), 없거나 타인 소유 시 404
```

모든 엔드포인트 인증 필요 — `deps.get_current_user`. `user_id`는 `current_user.id` 사용.

### app/api/v1/router.py 변경

```python
from app.api.v1.endpoints import alerts
router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
```

## Test Requirements

`tests/test_alerts.py`:

- `AlertService.create_alert` — 정상 생성, 동일 `dedup_key` 재요청 시 `None`(중복 방지) 검증
- `GET /api/v1/alerts` — 현재 사용자 알림만 반환, 타 사용자 알림 미포함
- `GET /api/v1/alerts?status=UNREAD` — 상태 필터 검증
- `POST /api/v1/alerts/{id}/read` — 상태가 READ로 변경
- `POST /api/v1/alerts/{id}/dismiss` — 상태가 DISMISSED로 변경
- `POST /api/v1/alerts/{id}/read` — 타인 소유/없는 id 404
- 동일 Signal(동일 뉴스·유형)로 두 번 생성 시도 시 중복 알림 미생성

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest tests/test_alerts.py -v
```

## Documentation Impact

`docs/designs/018-alert-domain.md` 외 없음.

## ADR Need

없음. 기존 도메인 패턴을 따른다.

## Failure Record Need

없음.

## Risk Level

Medium — 신규 테이블 마이그레이션(UniqueConstraint 포함), 신규 API 라우터 등록.

## Expected Output

- 위 scope 파일 신규 생성 + 마이그레이션
- `router.py`에 alerts 라우터 추가
- lint/typecheck/test 통과

## Rules

- 구현 전 `docs/designs/018-alert-domain.md`, `017-signal-domain.md`를 읽는다.
- Issue #17(task-015) 머지 후 최신 main에서 시작한다.
- 중복 방지는 DB `UniqueConstraint` + `IntegrityError` 처리로 구현한다.
- 기존 인증 방식(`deps.get_current_user`)을 따른다.
- 스코프 외 파일 변경 금지. 테스트 약화 금지. 보호 파일 변경 금지.
