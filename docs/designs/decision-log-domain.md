# BE 추가 필요 작업: 의사결정 저널(decision-log) 도메인

상태: **계약 확정(Frozen)** — 초안 2026-06-23, 계약 확정 2026-06-26(Opus, ADR-006).
`docs/api/contract-alignment.md`의 G10/N1 후속. FE `DecisionLog`(의사결정 저널) 화면을
백엔드로 영속화하기 위한 신규 도메인. **구현은 아래 §6 계약 확정을 정본으로 따른다**
(§1~§5는 초안 배경, 충돌 시 §6 우선).

## 배경

FE에 의사결정 저널 화면(`/decision-log`)이 있으나 백엔드에 대응 엔드포인트가 없다.
당분간 FE 로컬로 두되, 본 도메인을 백엔드에 추가해 영속화한다(Q7 확정).

## 1. API (스켈레톤)

| Method · Path | 책임 | Auth |
| --- | --- | --- |
| `GET /api/v1/decision-logs?page=&size=&sort=-decided_at` | 사용자 의사결정 목록 | Required |
| `POST /api/v1/decision-logs` | 의사결정 기록 생성 | Required |
| `GET /api/v1/decision-logs/{id}` | 단건 조회 | Required |
| `PATCH /api/v1/decision-logs/{id}` | 재검토/종료 등 갱신(필요 시) | Required |

소유권: `user_id` 기준, 본인 것만 접근(타인 접근 시 `*_FORBIDDEN`). 목록은 공통 pagination/sort.

## 2. 컬럼 (테이블: 예상 `decision_logs`)

| 컬럼 | 의미 | 비고 |
| --- | --- | --- |
| `id` | PK | |
| `user_id` | 소유자 | FK |
| `ticker` | 종목 코드 (AAPL, TSLA, 005930) | FE `symbol`과 동일 개념 |
| `company_name` | 회사명 | |
| `decision_type` | 판단 유형 | enum(§3) |
| `decision_status` | 판단 상태 | enum(§3, 제안값 확정 필요) |
| `summary` | 한 줄 요약 | |
| `reason` | 판단 근거 | |
| `risk_note` | 리스크 메모 | |
| `action_plan` | 이후 행동 계획 | |
| `confidence_score` | 판단 신뢰도 0~100 | int |
| `target_price` | 목표가 | Decimal 문자열(C5) |
| `stop_loss_price` | 손절 기준가 | Decimal 문자열(C5) |
| `valuation_snapshot` | 당시 밸류에이션 데이터 | JSON |
| `news_snapshot` | 당시 뉴스 요약 | JSON |
| `portfolio_snapshot` | 당시 포트폴리오 상태 | JSON |
| `ai_analysis_snapshot` | AI 분석 결과 원문 또는 요약 | JSON/Text |
| `cognitive_risks` | 인지 편향 태그 목록 | JSON 배열, FE `cognitiveRisks` 매핑 |
| `created_by` | 생성 주체 | enum USER/AI/SYSTEM |
| `decided_at` | 실제 판단 시점 | datetime(UTC, C6) |
| `reviewed_at` | 재검토 시점 | nullable |
| `closed_at` | 판단 종료 시점 | nullable |
| `created_at` | 레코드 생성 | datetime(UTC, C6) |
| `updated_at` | 레코드 수정 | datetime(UTC, C6) |

## 3. Enum 값

`decision_type`:

```text
WATCH
BUY_CONSIDER
BUY
HOLD
SELL_CONSIDER
SELL
SKIP
REBALANCE
TAKE_PROFIT
STOP_LOSS
```

`created_by`:

```text
USER
AI
SYSTEM
```

`decision_status` (확정): `OPEN` → `REVIEWED` → `CLOSED`
(`decided_at`/`reviewed_at`/`closed_at` 라이프사이클 대응).

enum 정본 표기는 contract-alignment C8에 따라 **영문 UPPER_SNAKE**, FE 표시계층에서 한글화.

## 4. FE 매핑 주의

FE 현행 `DecisionLog`는 (`symbol`, `decision`, `decisionType`, `rationale`, `cognitiveRisks[]`,
`reviewDate`, `outcome`, `createdAt`)로 더 단순하다. 본 스키마가 상위집합이며, FE 어댑터에서
`ticker↔symbol`, `reason↔rationale`, `decision_status↔outcome`,
`cognitive_risks↔cognitiveRisks` 등으로 매핑한다.

## 5. 정렬 주의

- `decision_status` = `OPEN`/`REVIEWED`/`CLOSED` **확정**.
- `cognitive_risks`(인지 편향) 컬럼 **포함 확정**(JSON 배열, FE `cognitiveRisks` 매핑).
- snapshot JSON들의 스키마 고정 여부(자유 JSON vs typed)는 미정 — MVP는 자유 JSON 권장.
- ADR + Alembic 마이그레이션 동반.

## 6. 계약 확정 (2026-06-26, Opus — 정본)

구현이 따르는 동결 계약. 와이어 컨벤션은 기존과 동일: snake_case 필드, 금액=Decimal
**문자열**, 시각=`app/core/schema.py`의 `UtcDatetime`(`...Z`), 공통 엔벨로프
`app/core/response.py`의 `ApiResponse`/`success`/`paginated`. 결정 근거는 ADR-006.

### 6.1 엔드포인트

| Method · Path | 책임 | meta |
| --- | --- | --- |
| `GET /api/v1/decision-logs?page=&size=&sort=` | 본인 의사결정 목록(페이지네이션) | 페이지 meta |
| `POST /api/v1/decision-logs` | 의사결정 기록 생성 | null |
| `GET /api/v1/decision-logs/{id}` | 단건 조회(본인) | null |
| `PATCH /api/v1/decision-logs/{id}` | 갱신(라이프사이클·가변필드, 본인) | null |

- 전부 Auth Required(`get_current_user`). 소유권 `user_id` 기준.
- `sort` 허용 필드: `decided_at`, `created_at`. 기본 `-decided_at`(최신순). 그 외 값은 기존
  `sort_param` 규약대로 422.
- 페이지네이션은 공통 `PaginationParams`(page≥1, 1≤size≤100, 기본 20).

### 6.2 테이블 `decision_logs`

| 컬럼 | 타입 | 제약 |
| --- | --- | --- |
| `id` | Integer | PK |
| `user_id` | Integer | FK `users.id`, NOT NULL |
| `ticker` | String(20) | NOT NULL |
| `company_name` | String(255) | nullable |
| `decision_type` | String(30) | NOT NULL (enum §6.4 값) |
| `decision_status` | String(20) | NOT NULL, default `OPEN` |
| `summary` | Text | nullable |
| `reason` | Text | nullable |
| `risk_note` | Text | nullable |
| `action_plan` | Text | nullable |
| `confidence_score` | Integer | nullable (0~100) |
| `target_price` | Numeric(20,4) | nullable |
| `stop_loss_price` | Numeric(20,4) | nullable |
| `valuation_snapshot` | JSON | nullable (자유 객체) |
| `news_snapshot` | JSON | nullable (자유 객체) |
| `portfolio_snapshot` | JSON | nullable (자유 객체) |
| `ai_analysis_snapshot` | JSON | nullable (자유 객체) |
| `cognitive_risks` | JSON | NOT NULL, default `[]` (string 배열) |
| `created_by` | String(20) | NOT NULL, default `USER` (enum §6.4) |
| `decided_at` | DateTime(tz) | NOT NULL |
| `reviewed_at` | DateTime(tz) | nullable |
| `closed_at` | DateTime(tz) | nullable |
| `created_at` | DateTime(tz) | server_default now (`TimestampMixin`) |
| `updated_at` | DateTime(tz) | server_default now, onupdate (`TimestampMixin`) |

### 6.3 요청·응답 스키마

**POST body** — 필수: `ticker`, `decision_type`. 선택(+기본):
`company_name?`, `decision_status?`(기본 `OPEN`), `summary?`, `reason?`, `risk_note?`,
`action_plan?`, `confidence_score?`(0~100, 범위 밖 422), `target_price?`/`stop_loss_price?`
(Decimal 문자열), `valuation_snapshot?`/`news_snapshot?`/`portfolio_snapshot?`/
`ai_analysis_snapshot?`(객체), `cognitive_risks?`(string 배열, 기본 `[]`),
`created_by?`(기본 `USER`), `decided_at?`(생략 시 서버 `now()`).

**PATCH body** — 전 필드 optional. 의미:
- `decision_status`를 `REVIEWED`로 바꾸고 `reviewed_at`이 null이면 서버가 `now()`로 스탬프.
- `decision_status`를 `CLOSED`로 바꾸고 `closed_at`이 null이면 서버가 `now()`로 스탬프.
- 전이 순서(forward-only)는 MVP 미강제(ADR-006 Follow-up). `reviewed_at`/`closed_at` 명시 제공 시 그 값 우선.
- 그 외 가변 텍스트/숫자/스냅샷 필드는 제공된 것만 갱신.

**응답 `data`** (단건/목록 항목 공통): 위 테이블 전 컬럼을 snake_case로.
`target_price`/`stop_loss_price`는 Decimal **문자열 또는 null**, `confidence_score`는 int/null,
스냅샷 4종은 객체/null, `cognitive_risks`는 string 배열,
`decided_at`/`created_at`/`updated_at`는 `UtcDatetime`, `reviewed_at`/`closed_at`는 `UtcDatetime`/null.

### 6.4 Enum (정본 영문 UPPER_SNAKE)

- `decision_type`: `WATCH`, `BUY_CONSIDER`, `BUY`, `HOLD`, `SELL_CONSIDER`, `SELL`,
  `SKIP`, `REBALANCE`, `TAKE_PROFIT`, `STOP_LOSS` (10종).
- `decision_status`: `OPEN`, `REVIEWED`, `CLOSED`.
- `created_by`: `USER`, `AI`, `SYSTEM`.
- 잘못된 enum 값은 입력 검증(422). `cognitive_risks`는 자유 string 배열(enum 미강제).

### 6.5 에러 코드 (신규)

- `DECISION_LOG_NOT_FOUND` = 404 (없음).
- `DECISION_LOG_FORBIDDEN` = 403 (타인 소유 접근).
- 그 외: 입력 검증 실패 = 기존 `VALIDATION_ERROR`(422).

### 6.6 범위 밖(후속)

forward-only 전이 강제, 스냅샷 typed 스키마, 검색/필터(ticker·status·기간), 페이지네이션 외
정렬 필드 확장, AI 자동 생성 연동. FE 어댑터(매핑 §4)는 FE 트랙(FE#48 후속).
