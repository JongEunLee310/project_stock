# API Contract Alignment — 공통 API 계약 정렬

상태: **결정 반영(Draft v3)** — Q1–Q8 답변 + 파생 항목(N1–N4) 확정 반영(2026-06-23).

이 문서는 백엔드(`project_stock`, FastAPI)와 프론트엔드(`project_stock_FE`, React)가
**하나의 공통 API 계약**에 합의하기 위한 정렬 문서다. 양쪽이 현재 가진 API를 모두
정리하고, 서로 부족한 부분을 어느 쪽이 채울지 결정하며, 통신 제약(규약)을 확정한다.

- 이 문서는 **두 저장소에 동일하게 미러링**된다(`project_stock/docs/api/contract-alignment.md`,
  `project_stock_FE/docs/api/contract-alignment.md`). 한쪽을 고치면 다른 쪽도 같이 갱신한다.
- 백엔드 구현 API의 단일 출처는 `project_stock/docs/api/frontend-api-spec.md`다. 본 문서는
  그 위에 **갭·결정·제약**을 얹는다. 요청/응답 전체 예시는 그 문서를 참조한다.
- 신규 BE 작업지도: 가격 시계열 `project_stock/docs/designs/price-series-api.md`(G4/N4),
  의사결정 저널 `project_stock/docs/designs/decision-log-domain.md`(G10/N1).
- 구현은 하지 않는다. 결정과 후속 액션만 기록한다.

---

## 0. 현재 격차 한 줄 요약

FE 도메인 모델은 백엔드 계약과 **독립적으로** 설계되어, 필드명 매핑이 아니라 구조·개념
수준에서 어긋나 있다. 정렬의 핵심은 ① 통신 규약 확정 ② 양쪽 누락 API의 소유자 지정
③ FE 도메인 모델을 계약 기준으로 재정렬(ADR-004 후속)이다.

---

## 1. 통신 규약 (Communication Constraints) — 확정

| # | 항목 | 확정안 | 소유자 | 비고 |
| --- | --- | --- | --- | --- |
| C1 | 응답 봉투 | 공통 envelope `{ data, message, error, meta }` 사용. `/health*`만 예외 | BE 유지 / FE 언랩 | FE에 unwrap 어댑터 1곳 |
| C2 | 목록 meta | `meta: { page, size, total }` 항상 포함 | BE 유지 / FE 페이징 연결 | Table을 서버 페이징으로 |
| C3 | 인증 | `Authorization: Bearer <access_token>`(JWT) + refresh 토큰 | BE 확장 / **FE 신규** | Q8: AT 15분·RT 2일(env 설정), `POST /auth/refresh` 신규, lazy refresh, 만료 시 재로그인 |
| C4 | ID 체계 | 정수 `id`/`asset_id`/`portfolio_id`가 정본. `symbol`은 표시·조회 보조 | 공통 | FE는 `symbol` 단일키 중단, asset_id 도입 |
| C5 | 금액·비율 타입 | **문자열 Decimal**(`"195.64"`, `"0.4"`)이 와이어 정본 | BE 유지 / FE 파싱 | FE 어댑터 경계에서 number 파싱, 표시 `Intl` |
| C6 | 날짜/시간 | ISO 8601, **와이어는 UTC(`Z`) 정본 / FE는 KST(Asia/Seoul) 표시**(Q6, N3) | BE 표준화(UTC) / FE 표시(KST) | 해외 종목 고려해 와이어 UTC 통일. 현재 naive `created_at`도 UTC aware로 |
| C7 | 정렬/필터 | 목록은 `sort=field`/`-field`, 리소스별 typed filter. 미허용 필드 `422` | BE 유지 / FE 준수 | |
| C8 | enum 표기 | 와이어 enum은 **영문 UPPER_SNAKE 정본**(`HIGH`, `UNREAD`, `RISK_ALERT`) | BE 유지 / **FE 한글화** | FE 현재 한글 enum(`높음`/`중간`/`낮음`)은 표시계층 매핑으로 |
| C9 | 에러 코드 | `ErrorCode` 문자열 정본(`error.code`). 신규 API는 코드 추가 | BE 유지 / FE 코드→메시지 매핑 | `app/core/error_codes.py` |
| C10 | Base/버전/CORS | prefix `/api/v1`, `CORS_ORIGINS`, FE는 `VITE_API_BASE_URL` env | 공통 | 로컬 `http://127.0.0.1:8000` |

핵심 매핑 규칙(C8): `RiskLevel` 높음/중간/낮음 ↔ `HIGH/MEDIUM/LOW`,
`StockStatus`/`ValuationLevel` 등 한글 enum은 모두 FE 표시계층에서만 한글화한다.
와이어에는 영문 enum만 흐른다.

---

## 2. 전체 API 인벤토리

### 2.1 백엔드 구현 완료 (37 routes, frontend-api-spec.md 기준)

| 그룹 | 엔드포인트 | FE 사용 예정 화면 |
| --- | --- | --- |
| Auth | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` | (신규)로그인, 설정 |
| Assets | `POST /assets`, `GET /assets`, `GET /assets/{id}`, `GET /assets/{id}/detail`, `GET /assets/{id}/research-summary`, `GET·PUT /assets/{id}/buy-checklist` | Research |
| Watchlists | `POST·GET /watchlists`, `POST·GET /watchlists/{id}/items`, `DELETE /watchlists/{id}/items/{itemId}` | Watchlist |
| Portfolios | `POST·GET /portfolios`, `GET /portfolios/{id}/summary`, `POST /portfolios/{id}/check`, `POST·PATCH·DELETE /portfolios/{id}/positions...` | Portfolio |
| Theses | `POST /theses`, `PUT /theses/{id}`, `GET /theses/latest`, `PATCH /theses/{id}/deactivate` | Research(가설) — FE 화면 미존재 |
| Reports | `POST·GET /reports`, `GET /reports/{id}` | Research(리포트) — FE 부분 |
| Signals | `POST·GET /signals`, `GET /signals/{id}` | Signals |
| Alerts | `GET /alerts`, `POST /alerts/{id}/read`, `POST /alerts/{id}/dismiss` | Alerts(인박스로 재정의) |
| Alert Candidates | `GET /alert-candidates`, `POST /alert-candidates/{id}/read`, `POST /alert-candidates/{id}/confirm` | Alerts(인박스) |
| Ops | `GET /job-runs`, `POST /worker/jobs/*`, `POST /worker/scheduler/...`, `GET /health*` | (화면 불요) |

### 2.2 프론트엔드 화면·도메인 (목 전용, API 미연동)

| FE 화면 | 라우트 | 핵심 도메인 타입(`src/shared/model/domain.ts`) |
| --- | --- | --- |
| Dashboard | `/` | `DashboardSummary`, `AiBriefing`, `PriorityQueueItem` |
| Watchlist | `/watchlist` | `Stock`, `WatchlistSummaryCard`, `RecentWatchlistItem`, `WatchlistAlertSetting` |
| Signals | `/signals` | `Signal`(kind/confidence/trendSeries…) |
| Research | `/research/:symbol` | `StockResearch`(pricePoints/targetPrice/catalysts/checklist…) |
| Portfolio | `/portfolio` | `Portfolio`, `Holding`, `PortfolioRiskExposure` |
| Alerts | `/alerts` | `AlertRule`(규칙 빌더·채널) → 폐기 |
| DecisionLog | `/decision-log` | `DecisionLog`(의사결정 저널) |
| Settings | `/settings` | (계정/알림 설정) |

---

## 3. 갭 해소 결정 (소유자 지정, Q1–Q8 반영)

| GAP | 내용 | 결정 | 소유자 |
| --- | --- | --- | --- |
| G1 | FE 인증 부재 | 백엔드 auth 사용 + FE에 로그인·토큰 흐름 신설(access+refresh, Q8) | **FE** |
| G2 | 봉투/Decimal/enum/페이징 | FE에 어댑터 계층(언랩·파싱·한글화·서버페이징) 도입(ADR-004) | **FE** |
| G3 | 대시보드 집계 API 없음 | 경량 집계 엔드포인트 신설(Q1 확정) | **BE 신규** |
| G4 | 가격 시계열 API 없음 | OHLCV 일봉 시계열 API 신설(Q1/Q5). **Signal보다 먼저 완성**(N4). 작업지도 → `docs/designs/price-series-api.md` | **BE 신규** |
| G5 | Watchlist 항목 thin | item에 asset 시세/상태 expand 응답 신설(Q2 확정) | **BE 확장** |
| G6 | symbol→asset_id 해소 | Research 라우팅이 `:symbol` 기반 → `GET /assets?symbol=` 필터 신설 | **BE 확장** |
| G7 | asset 펀더멘털 부족 | detail에 per/peg/52주/목표가 nullable 확장(Q4 확정). catalysts는 후속 | **BE 확장(nullable)** |
| G8 | Alerts 개념 충돌 | **BE 인박스 모델에 맞춰 FE 재정의**(Q3 확정). FE 규칙 빌더/채널 폐기, BE 규칙 API 신설 안 함 | **FE 재정의** |
| G9 | Signal 모델 상이 | **BE 리스크/가설충돌 모델로 통일**(Q5 확정). 단 FE 모멘텀 시각화는 G4 가격 시계열로 재구성해 유지 | **FE 재정의(+G4 선행)** |
| G10 | DecisionLog 백엔드 부재 | **BE에 decision-log 도메인 신규 추가**(Q7 확정). 작업지도 → `docs/designs/decision-log-domain.md`. 추가 전까지 FE 로컬 임시 | **BE 신규** |
| G11 | 알림 설정(Settings) | Q3로 Alerts가 인박스로 재정의됨 → 규칙/채널 설정 API 불요. Settings는 `auth/me`만 | **폐기(불요)** |

---

## 4. 화면별 목표 매핑 (정렬 후)

| FE 화면 | 사용할 백엔드 API(목표) | 합성/주의 |
| --- | --- | --- |
| Dashboard | `GET /dashboard/summary`(G3 신규) | 집계는 BE 소유 |
| Watchlist | `GET /watchlists`, `GET /watchlists/{id}/items`(+asset expand G5) | 단일평면 → 다중그룹 모델 수용 |
| Signals | `GET /signals?asset_id=`, `GET /signals/{id}`, `GET /stocks/{symbol}/prices`(G4) | FE Signal을 BE 모델로 교체, 모멘텀 스파크라인은 가격 시계열로 재구성(G9). G4 선행(N4) |
| Research | `GET /assets/{id}/detail`·`/research-summary`·`/buy-checklist`, `GET /reports?asset_id=`, `GET /theses/latest`, `GET /stocks/{symbol}/prices`(G4) | symbol→id 해소(G6), 펀더멘털(G7) |
| Portfolio | `GET /portfolios`, `GET /portfolios/{id}/summary` | sector_weights 직접 사용, dayChange·briefing은 BE 부재 |
| Alerts | `GET /alerts`(+read/dismiss), `GET /alert-candidates`(+read/confirm) | 인박스로 재정의(G8), 규칙/채널 폐기 |
| Settings | `GET /auth/me` | 알림 설정 API 불요(G11) |
| DecisionLog | `GET·POST /decision-logs`(G10 BE 신규 예정) | 추가 전까지 FE 로컬 임시(G10) |

---

## 5. 제안 신규/확장 API (백엔드 소유, 스켈레톤)

확정 시 `frontend-api-spec.md`·`tests/test_api_contract.py`에 반영. **시그니처·필드만**, 구현 없음.

| ID | Method · Path | 책임 | 주요 응답 필드(제안) | Auth |
| --- | --- | --- | --- | --- |
| G3 | `GET /api/v1/dashboard/summary` | 사용자 전체 집계 카드 | `risk_alert_count`, `important_news_count`, `review_signal_count`, `cash_weight`, 각 delta | Required |
| G4 | `GET /api/v1/stocks/{symbol}/prices?market=&range=&interval=1d&adjusted=` | 가격 시계열(차트 + Signal 모멘텀 공급) | item `date/open/high/low/close/adjustedClose/volume`, meta `symbol/market/currency/source/lastUpdatedAt` | Not required(제안) |
| G5 | `GET /api/v1/watchlists/{id}/items?expand=asset` | 항목+자산 시세 조인 | 기존 item + `asset: { symbol, name, price, change_percent, sector }` | Required |
| G6 | `GET /api/v1/assets?symbol={symbol}` | symbol→asset 해소(필터) | 기존 asset list(필터만 추가) | Not required |
| G7 | `GET /api/v1/assets/{id}/detail` 확장 | 펀더멘털 추가 | 기존 + `per?`, `peg?`, `fifty_two_week_low?`, `fifty_two_week_high?`, `target_price?`, `target_upside_percent?` (모두 nullable) | Not required |
| G10 | `GET·POST /api/v1/decision-logs` (필요 시 `PATCH /{id}`) | 의사결정 저널 영속화 | 전체 컬럼·enum은 `docs/designs/decision-log-domain.md` 참조 | Required |
| Q8 | `POST /api/v1/auth/refresh` | access 토큰 갱신 | `access_token`, `token_type`, `expires_in` (+ refresh 발급/회전 정책) | refresh 토큰 제시 |

세부 작업지도: G4 → `docs/designs/price-series-api.md`(OHLCV·`stock_price_bars`·PriceProvider·
에러코드·MVP 범위), G10 → `docs/designs/decision-log-domain.md`(컬럼·enum·소유권).

contract 변경 주의: Q8 적용 시 `POST /auth/login` 응답에 `refresh_token`·`expires_in` 추가가
필요하다(기존 `{ access_token, token_type }` 확장). 프론트 직접 연동 contract 변경이므로
`frontend-api-spec.md`·contract 테스트를 함께 갱신한다(N2).

데이터 출처 주의: G4/G7은 mock provider 외 실데이터 출처(시세/펀더멘털) 확보 여부가 선결.
현재 `*_PROVIDER`는 deterministic mock — 실연동 전까지 mock 값으로 계약만 고정 가능.

---

## 6. FE 도메인 재정렬 (프론트엔드 소유, ADR-004 후속)

구현은 FE #17 라운드. 본 문서는 방향만 고정한다.

- **어댑터 계층**: API DTO(snake_case·string Decimal·영문 enum·envelope) ↔ FE 도메인(camelCase·
  number·한글 라벨) 변환을 한 경계에서 수행. 화면은 FE 도메인만 본다.
- **ID 전환**: `symbol` 단일키 → `assetId: number` 도입(`symbol`은 표시·라우팅 보조).
- **모델 교체**:
  - `Signal`: `kind/confidence/previousStatus/trendSeries` → BE `signalType/score/riskLevel/reason/evidence/expiresAt` 기반으로 재정의. **모멘텀 시각화 유지 방법**: 스파크라인은 `GET /stocks/{symbol}/prices`(G4)의 최근 구간으로 렌더, confidence 게이지는 `score`로 매핑. embed된 `trendSeries`·`previousStatus` 델타는 BE 출처 없어 폐기(G9).
  - `Stock`(Watchlist): asset detail + research-summary + signals 합성 뷰모델로 분리(시세는 G5 expand).
  - `AlertRule`·채널 설정 → **폐기**. 인박스 모델로 재정의: `Alert`(status UNREAD/READ/DISMISSED, read/dismiss) + `AlertCandidate`(read/confirm)(G8).
  - `Portfolio`: BE summary 구조 수용(`sectorWeights`/`exceedsThreshold` 직접 사용, `cash_weight` 파생 중단).
- **인증 흐름 신설**: 로그인 + **access·refresh 토큰 스토어** / `Authorization` 주입 / 401 시 refresh 시도 → 실패 시 재로그인(Q8). 만료 감시는 **서버 401 기반 lazy refresh**만(클라 타이머 없음, N2).
- **시간 표시**: 와이어 UTC를 받아 FE에서 KST(Asia/Seoul) 포맷(C6). `TZ=UTC` 검증 유지.
- **서버 페이징**: Table 페이지네이션을 `page/size/sort/meta.total`에 연결.
- **DecisionLog**: BE `decision-logs` 신규(G10) 완료 시 연동. 그 전까지 클라이언트 로컬 임시 유지.

---

## 7. 결정 기록 (Q1–Q8 확정 + 파생 항목 N1–N4)

| Q | 결정 |
| --- | --- |
| Q1 | 대시보드 집계 = **BE 신규 API**(G3) |
| Q2 | Watchlist 항목 시세 = **BE expand 응답**(G5) |
| Q3 | Alerts = **BE 인박스 모델에 맞춰 FE 재정의**. FE 규칙/채널 폐기(G8) |
| Q4 | asset 펀더멘털 = **BE detail nullable 확장**(G7). catalysts는 후속 |
| Q5 | Signal = **BE 모델로 통일**. 모멘텀 시각화는 가격 시계열(G4)로 재구성해 유지(G9) |
| Q6 | datetime = **와이어 UTC / FE KST 표시**(C6) |
| Q7 | DecisionLog = **BE에 decision-log 도메인 신규 추가**(G10) |
| Q8 | 토큰 = **access + refresh**, 만료 시 refresh → 실패 시 재로그인 |

### 파생 항목 (N1–N4)

- **N1 (Q7) — 확정**: decision-log 컬럼·enum 확정(`docs/designs/decision-log-domain.md`).
  `decision_type` 10종·`created_by` USER/AI/SYSTEM, `decision_status` `OPEN→REVIEWED→CLOSED`,
  `cognitive_risks`(인지 편향) 컬럼 **포함** 확정. ADR/마이그레이션 동반.
- **N2 (Q8) — 확정**: 만료 env 설정, 기본 **AT 15분 / RT 2일**. 흐름: access 만료 요청 → 유효
  refresh면 access 갱신해 요청 성공시킴(거부 안 함) → refresh도 만료면 클라이언트에 '로그인 만료'
  통지 + 로그아웃. login 응답 contract 변경 + `POST /auth/refresh` 신규. 만료 감시 = **서버 401 기반
  lazy refresh만**(클라 만료 타이머 없음).
- **N3 (Q6) — 확정**: 해외 주식 포함 고려 → **와이어 UTC 통일**(naive `created_at` 포함 전 응답
  timezone-aware UTC), **FE에서 KST 표시**. 직렬화 변경 회귀 범위 큼 → contract 테스트 갱신.
- **N4 (Q5) — 확정**: **G4(가격 시계열)를 Signal 작업 전 완성**. MVP는 일봉 OHLCV + Mock
  Provider + FE 연결까지(`docs/designs/price-series-api.md`).

---

## 8. 후속 액션 분배

**백엔드(`project_stock`)**: C6(UTC 통일, N3) · G3/G5/G6/G7 · G4(가격 시계열, Signal 선행,
`docs/designs/price-series-api.md`) · G10(decision-logs, `docs/designs/decision-log-domain.md`) ·
Q8(refresh, AT 15분/RT 2일, login 응답 변경, N2) 계약 확정 → `frontend-api-spec.md` +
`test_api_contract.py` 갱신. G8 규칙/채널·G11은 폐기(불요).

**프론트엔드(`project_stock_FE`)**: ADR-004(서버상태·API client·어댑터) 초안 →
인증 흐름(access+refresh) → 도메인 재정렬(§6) → 화면별 연동(#17~). 계약 확정 전까지 화면은 현 mock 유지.

**공통**: 본 문서를 양 저장소에 미러링·동기 유지. 와이어 contract 변경은
`frontend-api-spec.md`의 "Contract 변경 검토 기준" 절차를 따른다.
