# BE 추가 필요 작업: 의사결정 저널(decision-log) 도메인

상태: **제안(Draft)** — 작성 2026-06-23. `docs/api/contract-alignment.md`의 G10/N1 후속.
구현 전 작업지도다. FE `DecisionLog`(의사결정 저널) 화면을 백엔드로 영속화하기 위한 신규 도메인.

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
