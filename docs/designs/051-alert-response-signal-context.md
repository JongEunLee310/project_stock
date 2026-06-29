# BE 보강: AlertResponse에 시그널 맥락 추가

상태: **계약 확정(Frozen)** — 2026-06-29(Opus). FE WatchlistPage "알림 현황" 카드 및 AlertsPage 페어.
`AlertResponse`가 `signal_id`(정수)만 노출해, FE가 알림이 "무엇에 대한" 것인지 표시할 수 없다.
연결된 시그널의 진실된 맥락(종목 심볼, 시그널 유형, 사유)을 응답에 additive로 추가한다.
**구현은 §3 계약 확정을 정본으로 따른다.**

## 배경

`GET /api/v1/alerts`의 `AlertResponse`는 `id, user_id, signal_id, status, created_at`만 반환한다.
그러나 FE `AlertDto`는 이미 `symbol, alert_type, title, message`를 기대하고 AlertsPage(알림 인박스)에서
이를 렌더한다. 즉 FE 계약이 BE보다 앞서 작성돼 **현재 AlertsPage는 제목·내용·종목이 빈 채로 표시되는
드리프트** 상태다. 본 변경으로 이 드리프트를 해소하고, FE WatchlistPage "알림 현황" 카드가 의미 있는
최근 알림을 표시할 수 있게 한다.

진실성: 추가 필드는 모두 연결된 `Signal`(및 그 `Asset`)의 실데이터에서 파생한다.
- `symbol` ← `signal.asset.symbol`
- `alert_type` ← `signal.signal_type`
- `message` ← `signal.reason`

`title`은 Signal에 대응 필드가 없으므로 BE에서 만들지 않는다. FE가 `alert_type`(시그널 유형) 라벨로
파생한다(§2). 의미 분류·임의 텍스트를 BE에서 합성하지 않는다.

스키마 변경(마이그레이션)·인증 변경·신규 외부 호출 없음. 가격 표기가 없어 시세 호출도 없다.
기존 패턴(alert-candidates expand BE#113, signals expand BE#112) 재사용이므로 ADR 불요.

## 1. 변경 범위

| Method · Path | 변경 |
| --- | --- |
| `GET /api/v1/alerts` | 각 항목에 `asset_id, symbol, alert_type, message` 추가(연결 시그널에서 파생) |
| `POST /api/v1/alerts/{id}/read` | 응답 단건에 동일 필드 추가 |
| `POST /api/v1/alerts/{id}/dismiss` | 응답 단건에 동일 필드 추가 |

기존 필드(`id, user_id, signal_id, status, created_at`)와 정렬·필터·페이지네이션·dedup 로직은 불변.

## 2. FE 매핑

FE는 추가 필드를 다음과 같이 소비한다(상세는 FE 설계 72):
- `alert_type` → 시그널 유형 라벨(`WATCH`/`RISK_ALERT`/… → 한국어 라벨).
- `title` → FE가 `alert_type` 라벨(필요 시 `symbol` 결합)로 파생. BE 미전송.
- `message` → `signal.reason` 그대로.
- `symbol`/`asset_id` → 종목 식별 및 딥링크.

`asset` 객체 전체(price 등)는 불필요하다. AlertsPage·WatchlistPage 카드 모두 가격을 표시하지 않으므로
`symbol`만 노출하고 시세 호출은 하지 않는다(alert-candidates expand와 달리 quote 미사용).

## 3. 계약 확정 (2026-06-29, Opus — 정본)

와이어 컨벤션: snake_case, 시각=`UtcDatetime`, 공통 엔벨로프 `app/core/response.py`.

### 3.1 응답 스키마 (`app/domains/alerts/schema.py`)

`AlertResponse`에 additive 필드 추가(모두 기본값으로 하위호환):

| 필드 | 타입 | 출처 |
| --- | --- | --- |
| `asset_id` | `int \| None = None` | `signal.asset_id` |
| `symbol` | `str \| None = None` | `signal.asset.symbol` |
| `alert_type` | `str \| None = None` | `signal.signal_type` |
| `message` | `str \| None = None` | `signal.reason` |

기존 필드는 변경하지 않는다. 시그널/자산이 조회되지 않는 예외적 경우 해당 필드는 `None`.

### 3.2 서비스 동작 (`app/domains/alerts/service.py`)

목록·단건 모두 연결 시그널 맥락을 채워 응답을 구성한다. alert-candidates `list_candidates_expanded`
패턴을 미러하되 **시세 호출은 제외**한다.

- 목록: 기존 `list_alerts`로 알림을 조회한 뒤, 항목들의 `signal_id` 집합으로 시그널을 배치 조회하고,
  그 `asset_id` 집합으로 자산을 배치 조회해 `signal_id → (asset_id, signal_type, reason)`,
  `asset_id → symbol` 맵을 만들어 항목별 응답에 합친다(N+1 회피).
- 단건(read/dismiss): 갱신된 알림의 연결 시그널·자산을 조회해 동일 필드를 채운다.
- 응답 조립용 메서드를 서비스에 추가한다(시그널 repo·자산 repo 의존 추가). 엔드포인트는 이 메서드 결과를
  반환하도록 조정한다.

시그널 조회는 기존 `SignalRepository`(또는 동등 배치 조회)를, 자산 조회는 `AssetRepository.get_by_id`를
재사용한다. 신규 repo 메서드가 필요하면 배치 조회(`asset_id in (...)`) 형태로 최소 추가한다.

### 3.3 에러

신규 에러 코드 없음. 기존 인증·소유권(`ALERT_NOT_FOUND`) 에러만.

## 4. 범위 밖(후속)

- `expand` 게이팅: 알림은 FE가 항상 맥락을 필요로 하므로 무조건 포함한다(게이팅하지 않음).
- 시세/`asset` 전체 객체(price/change_percent) 포함.
- `title`의 BE 합성(FE 파생 책임).
- alerts 생성·dedup·상태 전이 로직 변경.
- FE 어댑터·카드 매핑은 FE 트랙 별도 PR(설계 72).
