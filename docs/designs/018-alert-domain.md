# 018: Alert 도메인

## 목적

사용자가 확인해야 할 중요 이벤트를 알림(Alert)으로 저장한다.
1차 MVP는 외부 푸시 대신 내부 알림 목록을 우선 구현한다.
중요 Signal(#17)이 발생하면 Alert가 생성된다.

## 상태

`app/domains/alerts/types.py` — `AlertStatus(str, Enum)`: `UNREAD` / `READ` / `DISMISSED`

## DB 모델

테이블: `alerts`

| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | Integer PK | |
| user_id | FK → users, index | 수신자 |
| signal_id | FK → signals, index | 원천 Signal |
| status | String(20) | UNREAD / READ / DISMISSED, 기본 UNREAD |
| dedup_key | String(255) | 중복 방지 키 |
| created_at | DateTime(tz) | |
| updated_at | DateTime(tz) | |

`__table_args__`: `UniqueConstraint(user_id, dedup_key)` — 동일 사용자·동일 이벤트 중복 알림 차단.

`dedup_key`는 Signal 식별 정보로 구성한다(예: `f"{signal_type}:{news_item_id}"`). 동일 뉴스로 같은 유형 Signal이 재생성돼도 Alert는 1회만 생성된다.

## 스키마 (Pydantic)

```
class AlertCreate(BaseModel):
    user_id: int
    signal_id: int
    dedup_key: str

class AlertResponse(BaseModel):
    id: int
    user_id: int
    signal_id: int
    status: str
    created_at: datetime
```

## API

```
GET    /api/v1/alerts?status={status}   — 현재 사용자 Alert 목록 (status 필터 선택)
POST   /api/v1/alerts/{id}/read         — 읽음 처리
POST   /api/v1/alerts/{id}/dismiss      — 무시 처리
```

- 모든 엔드포인트 인증 필요. 목록·상태 변경은 `current_user` 소유 Alert로 제한.
- 타인 Alert 접근 시 404.

## 서비스·레포지토리

```
class AlertRepository:
    def create_if_absent(self, data: AlertCreate) -> Alert | None
    def get_by_id(self, alert_id: int) -> Alert | None
    def list_by_user(self, user_id: int, status: str | None) -> list[Alert]
    def update_status(self, alert: Alert, status: str) -> Alert

class AlertService:
    def create_alert(self, user_id: int, signal: Signal) -> Alert | None   # dedup_key 생성 + 중복 시 None
    def list_alerts(self, user_id: int, status: str | None = None) -> list[Alert]
    def mark_read(self, alert_id: int, user_id: int) -> Alert       # 없거나 타인 소유 시 AppException 404
    def dismiss(self, alert_id: int, user_id: int) -> Alert         # 없거나 타인 소유 시 AppException 404
```

- `create_if_absent`: `UniqueConstraint` 위반(`IntegrityError`) 시 `rollback` 후 `None` 반환.
- `list_by_user`: `created_at DESC, id DESC` 정렬.

## 의존성

Issue #17(Signal 도메인) 완료 후 진행.
