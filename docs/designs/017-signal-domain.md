# 017: Signal 도메인

## 목적

뉴스 요약, 투자 가설 충돌 판단, 리스크 레벨을 종합해 사용자가 검토해야 할 신호(Signal)를 저장하고 조회한다.
Signal은 Rule Engine(#20)의 산출물이며 Alert(#18)의 입력이 된다.

## Signal Type

`app/domains/signals/types.py` — `SignalType(str, Enum)`

| 값 | 의미 |
|---|---|
| WATCH | 관찰 필요 |
| RISK_ALERT | 리스크 경고 |
| THESIS_BROKEN | 투자 가설 훼손 |
| BUY_CANDIDATE | 매수 후보 |
| SELL_REVIEW | 매도 검토 |
| OVERHEATED | 과열 |

## DB 모델

테이블: `signals`

| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | Integer PK | |
| asset_id | FK → assets, index | |
| thesis_id | FK → investment_theses, nullable | 근거 가설 |
| news_item_id | FK → news_items, nullable | 트리거 뉴스 |
| signal_type | String(20), index | SignalType |
| score | Integer | 신호 강도 0–100 |
| risk_level | String(20), nullable | LOW / MEDIUM / HIGH / CRITICAL |
| reason | Text | 근거 요약(사람이 읽는 문장) |
| evidence | Text, nullable | 생성 근거 JSON 문자열 |
| expires_at | DateTime(tz), nullable | 만료 시각 |
| created_at | DateTime(tz) | |

`updated_at`은 사용하지 않는다(Signal은 불변).

## 스키마 (Pydantic)

```
class SignalCreate(BaseModel):
    asset_id: int
    thesis_id: int | None
    news_item_id: int | None
    signal_type: SignalType
    score: int
    risk_level: str | None
    reason: str
    evidence: dict | None
    expires_at: datetime | None

class SignalResponse(BaseModel):
    id: int
    asset_id: int
    thesis_id: int | None
    news_item_id: int | None
    signal_type: str
    score: int
    risk_level: str | None
    reason: str
    evidence: dict | None
    expires_at: datetime | None
    is_expired: bool
    created_at: datetime
```

- `evidence`는 DB에 JSON 문자열로 저장하고 응답 시 `dict`로 역직렬화한다(`field_validator`).
- `is_expired`는 `expires_at`과 현재 시각 비교로 계산한다(`computed_field` 또는 `model_validator`).

## API

```
POST   /api/v1/signals                                  — 신호 생성
GET    /api/v1/signals?asset_id={id}&include_expired={bool}  — 목록 조회 (asset_id 필수, 기본 만료 제외)
GET    /api/v1/signals/{id}                              — 상세 조회
```

모든 엔드포인트 인증 필요(`deps.get_current_user`).

## 서비스·레포지토리

```
class SignalRepository:
    def create(self, data: SignalCreate) -> Signal
    def get_by_id(self, signal_id: int) -> Signal | None
    def list_by_asset(self, asset_id: int, include_expired: bool) -> list[Signal]
    def exists_active(self, asset_id: int, signal_type: str, news_item_id: int | None) -> bool

class SignalService:
    def create_signal(self, data: SignalCreate) -> Signal
    def get_signal(self, signal_id: int) -> Signal           # 없으면 AppException 404
    def list_signals(self, asset_id: int, include_expired: bool = False) -> list[Signal]
```

- `exists_active`: Rule Engine(#20)의 중복 방지 규칙에서 사용. 미만료(`expires_at`이 없거나 미래) 신호만 대상으로 한다.
- `list_by_asset`: `created_at DESC, id DESC` 정렬. `include_expired=False`면 미만료만 반환.

## 의존성

Issue #15(투자 가설 충돌), #16(Research Report) 완료 후 진행.
