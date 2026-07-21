# BE 설계: 판단 기록(Decision Log) 재설계 — 이슈 #348

상태: **계약 확정(Frozen)** — 2026-07-21, ADR-016. 에픽 BE #347, FE 에픽
`project_stock_frontend#242`.

이 문서는 ADR-016이 위임한 재설계 계약을 스켈레톤 수준으로 확정한다. 테이블·enum·API
계약만 담고 쿼리·비즈니스 로직은 담지 않는다. 리터럴(enum 값·필드 형식)의 출처는 사용자
제공 설계 지침(2026-07-21)과 기존 계약(`docs/designs/decision-log-domain.md`, ADR-006)이다.
출처를 댈 수 없는 값은 "가정"으로 표기한다.

## 배경

ADR-006의 단일 테이블 `decision_logs`를 6개 테이블로 분리하고, 대상 다형화·판단 유형 확장·
근거 분리·재검토 트리거·복기·버전 관리를 도입한다. 격차와 결정 근거는 ADR-016을 따른다.
와이어 컨벤션은 기존과 동일하다: snake_case 필드, 금액 = Decimal **문자열**, 시각 =
`app/core/schema.py`의 `UtcDatetime`(`...Z`), 공통 엔벨로프 `app/core/response.py`의
`ApiResponse`/`success`/`paginated`, 페이지네이션 `app/core/pagination.py`의
`PaginationParams`.

## 1. 도메인 배치

기존 도메인 패턴(`model` / `repository` / `service` / `schema` + router)을 유지하되,
`app/domains/decision_logs/`를 재설계 모델로 재편한다.

```text
app/domains/decision_logs/
  model.py        # 6개 ORM 모델
  types.py        # enum 정의
  schema.py       # 요청·응답 Pydantic 모델
  repository.py   # 영속성 접근
  service.py      # 유스케이스
app/api/v1/endpoints/decision_logs.py  # 라우터
```

## 2. Enum (types.py) — 정본 영문 UPPER_SNAKE

FE 표시 계층에서 한글화한다(contract-alignment C8). 잘못된 값은 입력 검증 422.

`TargetType`: `SYMBOL`, `PORTFOLIO`, `TOPIC`, `SECTOR`, `MARKET`.

`DecisionType`(9종): `WATCH`, `RESEARCH_REQUIRED`, `HOLD`, `BUY_REVIEW`, `SELL_REVIEW`,
`REDUCE_REVIEW`, `REBALANCE_REVIEW`, `THESIS_INVALIDATED`, `NO_ACTION`.

`DecisionStatus`: `DRAFT`, `ACTIVE`, `REVIEW_DUE`, `REVIEWED`, `CLOSED`, `CANCELLED`.

`ConfidenceLevel`: `LOW`, `MEDIUM`, `HIGH`.

`EvidenceRelationship`: `SUPPORTING`, `CONTRADICTING`, `RISK`, `BACKGROUND`.

`RiskSeverity`: `LOW`, `MEDIUM`, `HIGH`.

`ReviewTriggerType`: `DATE`, `PRICE`, `METRIC`, `EVENT`, `SIGNAL_CHANGE`, `MANUAL`.

`ReviewTriggerStatus`: `PENDING`, `TRIGGERED`, `DISMISSED`. (가정 — 트리거 라이프사이클용,
사용자 지침에는 status만 명시되고 값은 미지정.)

`CreatedBy`: `USER`, `AI`, `SYSTEM`. (ADR-006 계승.)

복기용(2차, 스키마만 예고):
- `OutcomeStatus`: `THESIS_CONFIRMED`, `THESIS_PARTIALLY_CONFIRMED`, `THESIS_INVALIDATED`,
  `INSUFFICIENT_TIME`, `CLOSED`.
- `ThesisResult`: `CONFIRMED`, `PARTIALLY_CONFIRMED`, `INVALIDATED`. (가정 — 지침의 복기
  응답 예시 `thesis_result: PARTIALLY_CONFIRMED`에서 파생.)

`risk_type`은 enum이 아닌 문자열로 저장한다(자유 태그). 권장 태그 집합(사용자 지침):
`VALUATION`, `DEMAND_SLOWDOWN`, `COMPETITION`, `REGULATION`, `MARGIN_PRESSURE`,
`SUPPLY_CHAIN`, `MACRO_RATE`, `CURRENCY`, `CONCENTRATION`, `LIQUIDITY`, `MANAGEMENT`,
`ACCOUNTING`. 인지·행동 편향 태그(`FOMO`·`LOSS_AVERSION` 등)도 같은 컬럼에 저장 가능하다.
검증은 강제하지 않는다(집계 편의를 위한 권장 집합).

## 3. 테이블

기본키는 프로젝트 관례상 `Integer` autoincrement를 사용한다(기존 도메인과 동일). 사용자
지침의 `UUID`는 개념 표기로 보고, 실제 타입은 기존 컨벤션을 따른다(가정 — 정합성 우선).
타임스탬프는 `TimestampMixin`(`created_at`/`updated_at`) 사용.

### 3.1 `decision_logs` (재편)

| 컬럼 | 타입 | 제약 |
| --- | --- | --- |
| `id` | Integer | PK |
| `user_id` | Integer | FK `users.id`, NOT NULL |
| `target_type` | String(20) | NOT NULL (`TargetType`) |
| `target_id` | String(64) | NOT NULL (대상 식별자: ticker·portfolio id·topic key 등) |
| `symbol` | String(20) | nullable (종목 대상일 때만) |
| `decision_type` | String(30) | NOT NULL (`DecisionType`) |
| `status` | String(20) | NOT NULL, default `DRAFT` |
| `thesis` | Text | nullable (핵심 가설) |
| `rationale` | Text | nullable (핵심 판단 이유) |
| `confidence_level` | String(10) | nullable (`ConfidenceLevel`) |
| `created_by` | String(20) | NOT NULL, default `USER` (`CreatedBy`) |
| `superseded_by_id` | Integer | nullable, FK `decision_logs.id` (버전 대체, 2차 사용) |
| `decided_at` | DateTime(tz) | nullable (확정 시 스탬프) |
| `activated_at` | DateTime(tz) | nullable |
| `reviewed_at` | DateTime(tz) | nullable |
| `closed_at` | DateTime(tz) | nullable |
| `created_at` / `updated_at` | DateTime(tz) | `TimestampMixin` |

주: 지침의 `summary`는 `rationale`에서 파생하거나 목록 응답에서 잘라 노출한다(별도 컬럼
두지 않음, 가정). 긍정/반대 근거는 `decision_evidence`로 분리 저장한다(§3.2).

### 3.2 `decision_evidence`

| 컬럼 | 타입 | 제약 |
| --- | --- | --- |
| `id` | Integer | PK |
| `decision_id` | Integer | FK `decision_logs.id`, NOT NULL |
| `evidence_type` | String(30) | NOT NULL (`SIGNAL`·`RESEARCH`·`NEWS`·`DISCLOSURE`·`TOPIC_INSIGHT`·`PORTFOLIO`·`CHART`·`USER_MEMO` 등 문자열) |
| `evidence_id` | String(64) | nullable (외부 자료 식별자) |
| `evidence_version` | Integer | nullable (당시 버전 고정) |
| `title` | String(255) | NOT NULL |
| `summary` | Text | nullable |
| `snapshot` | JSON | nullable (당시 값 보존) |
| `relationship` | String(20) | NOT NULL (`EvidenceRelationship`) |
| `created_at` | DateTime(tz) | `TimestampMixin` |

긍정 근거 = `relationship=SUPPORTING`, 반대 근거 = `CONTRADICTING`. `evidence_type`은 자유
문자열로 두어 연결 대상 확장에 열어 둔다.

### 3.3 `decision_risks`

| 컬럼 | 타입 | 제약 |
| --- | --- | --- |
| `id` | Integer | PK |
| `decision_id` | Integer | FK `decision_logs.id`, NOT NULL |
| `risk_type` | String(40) | NOT NULL (자유 태그, §2 권장 집합) |
| `description` | Text | nullable |
| `severity` | String(10) | NOT NULL (`RiskSeverity`) |
| `created_at` | DateTime(tz) | `TimestampMixin` |

### 3.4 `decision_review_triggers`

| 컬럼 | 타입 | 제약 |
| --- | --- | --- |
| `id` | Integer | PK |
| `decision_id` | Integer | FK `decision_logs.id`, NOT NULL |
| `trigger_type` | String(20) | NOT NULL (`ReviewTriggerType`) |
| `condition` | JSON | NOT NULL (조건 명세; `DATE`는 빈 객체 가능) |
| `scheduled_at` | DateTime(tz) | nullable (`DATE` 트리거의 재검토 시각) |
| `status` | String(20) | NOT NULL, default `PENDING` (`ReviewTriggerStatus`) |
| `triggered_at` | DateTime(tz) | nullable |
| `created_at` | DateTime(tz) | `TimestampMixin` |

1차는 `DATE` 트리거만 사용한다. `PRICE`/`METRIC`/`EVENT`/`SIGNAL_CHANGE`는 컬럼만 두고 감시
로직은 2차(#353)에서 Alert 연동과 함께 구현한다.

### 3.5 `decision_snapshots`

| 컬럼 | 타입 | 제약 |
| --- | --- | --- |
| `id` | Integer | PK |
| `decision_id` | Integer | FK `decision_logs.id`, NOT NULL |
| `snapshot_type` | String(30) | NOT NULL (`VALUATION`·`NEWS`·`PORTFOLIO`·`AI_SIGNAL`·`PRICE` 등) |
| `data` | JSON | NOT NULL (자유 객체, immutable) |
| `captured_at` | DateTime(tz) | NOT NULL |

`data` 예시 키(사용자 지침): `price`, `forward_per`, `news_risk`, `valuation_risk`,
`theme_heat`, `portfolio_weight`, `cash_ratio`. 백엔드는 형태를 검증·해석하지 않는다
(ADR-016 §1·§4).

### 3.6 `decision_reviews` (2차 도입, 스키마 예고)

| 컬럼 | 타입 | 제약 |
| --- | --- | --- |
| `id` | Integer | PK |
| `decision_id` | Integer | FK `decision_logs.id`, NOT NULL |
| `outcome_status` | String(30) | NOT NULL (`OutcomeStatus`) |
| `thesis_result` | String(30) | NOT NULL (`ThesisResult`) |
| `process_quality` | JSON | nullable (근거충분성·반대근거검토·위험인식·재검토명확성·규칙준수 항목별 점수) |
| `result_metrics` | JSON | nullable (`return_rate`·`benchmark_return_rate`·`max_drawdown`) |
| `what_went_well` | Text | nullable |
| `what_was_missed` | Text | nullable |
| `what_to_change` | Text | nullable |
| `reviewed_at` | DateTime(tz) | NOT NULL |

판단 품질(`process_quality`)과 투자 결과(`result_metrics`)를 분리해 저장한다(ADR-016 §6).
1차에서는 테이블만 생성하고 API는 2차(#353)에서 연다.

## 4. API 계약 (1차)

전부 Auth Required(`get_current_user`), 소유권 `user_id` 기준. 응답은 공통 엔벨로프.

| Method · Path | 책임 | request schema | response schema |
| --- | --- | --- | --- |
| `GET /api/v1/decision-logs/overview` | 판단 활동 요약 | — | `DecisionOverviewResponse` |
| `GET /api/v1/decision-logs` | 목록(필터·페이지네이션) | query params(§4.1) | `DecisionLogListItem[]` |
| `POST /api/v1/decision-logs` | 판단 생성(DRAFT) | `DecisionLogCreate` | `DecisionLogResponse` |
| `GET /api/v1/decision-logs/{id}` | 상세 | — | `DecisionLogDetailResponse` |
| `PATCH /api/v1/decision-logs/{id}` | DRAFT 수정 | `DecisionLogUpdate` | `DecisionLogResponse` |
| `POST /api/v1/decision-logs/{id}/activate` | 확정 | `DecisionActivateRequest`(옵션) | `DecisionLogResponse` |
| `GET /api/v1/decision-logs/review-queue` | 재검토 예정 목록 | query params | `DecisionLogListItem[]` |

2차 예고: `POST /{id}/revise`, `POST /{id}/reviews`.

기존 `GET /decision-logs/stats`는 `overview`로 대체한다(하위호환 불필요 — 현재 mock 수준).

### 4.1 목록 필터 (query params)

`target_type`, `symbol`, `decision_type`, `status`, `risk_type`, `review_due_before`,
페이지네이션(`page`/`size`), 정렬(`sort`, 허용 `decided_at`·`created_at`, 기본 `-created_at`).
잘못된 enum/정렬 값은 422.

### 4.2 요청 스키마 (schema.py, 필드 요지)

- `DecisionTarget`: `type`(`TargetType`), `id`(str), `label?`.
- `DecisionEvidenceInput`: `type`, `id?`, `version?`, `title?`, `summary?`, `snapshot?`,
  `relationship`(기본 `SUPPORTING`).
- `DecisionRiskInput`: `type`(str), `severity`(`RiskSeverity`), `description?`.
- `DecisionReviewTriggerInput`: `type`(`ReviewTriggerType`), `condition`(obj),
  `scheduled_at?`.
- `DecisionLogCreate`: `target`(`DecisionTarget`), `decision_type`, `thesis?`, `rationale?`,
  `confidence_level?`, `supporting_reasons?`(str[] 또는 `evidence`로 흡수),
  `counter_arguments?`(str[]), `risks?`(`DecisionRiskInput[]`),
  `evidence?`(`DecisionEvidenceInput[]`), `review_triggers?`(`DecisionReviewTriggerInput[]`),
  `created_by?`(기본 `USER`). 필수: `target`, `decision_type`.
- `DecisionLogUpdate`: 전 필드 optional, `DRAFT`에서만 허용.
- `DecisionActivateRequest`: `snapshots?`(`snapshot_type`+`data` 목록). 생략 시 서버가 캡처
  가능한 스냅샷만 저장.

주: `supporting_reasons`/`counter_arguments`(문자열 배열, 사용자 지침 POST 예시)는 서버에서
`decision_evidence`(`relationship=SUPPORTING`/`CONTRADICTING`, `title`에 문장)로 정규화한다.
구조화 `evidence` 입력과 병존한다(가정 — 지침이 두 형태를 모두 예시).

### 4.3 응답 스키마

- `DecisionOverviewResponse`: `total_count`, `created_this_week`, `review_due_count`,
  `active_count`, `decision_type_distribution`(`{type,count,share}[]`), `as_of`(`UtcDatetime`).
- `DecisionLogListItem`: `id`, `target`(`{type,id,label}`), `decision_type`,
  `decision_label`, `summary`, `risks`(str[]), `confidence_level`, `status`,
  `review_at?`(`UtcDatetime`), `created_at`.
- `DecisionLogResponse`: 본문 전 컬럼(snake_case) + 중첩 `risks`/`evidence`/`review_triggers`.
- `DecisionLogDetailResponse`: `DecisionLogResponse` + `snapshots` + (2차) `reviews`·버전 링크.

`decision_label`은 서버가 내려주지 않고 FE 표시 계층이 매핑할 수도 있다 — 정본은 enum 값,
라벨은 FE(C8). 지침의 `decision_label`은 편의 필드이며 포함 여부는 구현에서 확정(가정).

### 4.4 확정(activate) 동작 (책임 요지, 로직 미포함)

- 상태 `DRAFT → ACTIVE`, `activated_at`·`decided_at` 스탬프.
- `decision_snapshots`에 당시 수치 캡처(요청 제공분 또는 서버 조회분).
- `decision_evidence.evidence_version` 고정(당시 버전 보존).
- `DATE` 재검토 트리거의 `scheduled_at` 확정·`status=PENDING` 등록.
- 이후 본문 핵심 필드 수정 제한(수정은 2차 `revise`).

## 5. Service / Repository 시그니처 (스켈레톤)

책임 한 줄만 기술한다. 구현은 핸드오프(#350 등)에서.

`DecisionLogRepository`
- `create(user_id, ...) -> DecisionLog` — 본문·중첩 부속 생성.
- `get_owned(id, user_id) -> DecisionLog | None` — 소유 단건.
- `list(user_id, filters, pagination, sort) -> list[DecisionLog]` — 필터 목록.
- `count(user_id, filters) -> int` — 목록 총계.
- `list_review_due(user_id, now) -> list[DecisionLog]` — 재검토 도래분.
- `aggregate_overview(user_id, now) -> OverviewAgg` — 요약 집계.
- `add_snapshots(decision_id, items)` — 스냅샷 캡처.

`DecisionLogService`
- `create_decision(user_id, DecisionLogCreate) -> DecisionLog` — DRAFT 생성·부속 정규화.
- `get_decision(id, user_id) -> DecisionLog` — 상세(없으면 `DECISION_LOG_NOT_FOUND`, 타인
  `DECISION_LOG_FORBIDDEN`).
- `list_decisions(user_id, ...) -> (items, total)` — 목록·필터.
- `update_draft(id, user_id, DecisionLogUpdate) -> DecisionLog` — DRAFT 한정 수정.
- `activate(id, user_id, DecisionActivateRequest) -> DecisionLog` — §4.4 동작.
- `get_overview(user_id) -> DecisionOverviewResponse` — 요약.
- `get_review_queue(user_id) -> (items, total)` — 재검토 예정.

## 6. 에러 코드

- `DECISION_LOG_NOT_FOUND` = 404.
- `DECISION_LOG_FORBIDDEN` = 403.
- `DECISION_LOG_INVALID_STATE` = 409 — DRAFT 아닌데 수정, 이미 ACTIVE인데 재확정 등
  (가정 — 상태 전이 위반용 신규 코드; ADR-006에는 없던 상태 제약이 생겨 추가).
- 입력 검증 실패 = 기존 `VALIDATION_ERROR`(422).

## 7. 의존

- `app/domains/users`(소유권), `app/core`(response·pagination·schema·error_codes).
- 근거 자동 연결(Signal·Research·News·Portfolio)과 Alert 연동은 2차(#353) 의존이며 1차는
  느슨한 문자열 참조만 저장한다(외래키 강제하지 않음).

## 8. 마이그레이션·기존 데이터

- Alembic 신규 리비전으로 6개 테이블을 만든다(`decision_reviews` 포함, API는 2차).
- 기존 `decision_logs`는 테스트·mock 수준이라 실데이터 이관 부담이 낮다. 재생성(drop &
  create) 또는 컬럼 재편 중 택1을 마이그레이션에서 명시한다. 기본 방침은 재편이되, 기존
  컬럼(`ticker`→`symbol`/`target_id`, `reason`→`rationale`, `decision_status`→`status`,
  `cognitive_risks`→`decision_risks` 이관)의 매핑을 리비전 주석에 남긴다.
- 이 작업은 human-gate(DB 스키마)다. BE #349에서 사람 승인 후 진행.

## 9. 범위 밖(후속)

복기(`reviews`)·버전(`revise`)·이벤트 재검토 감시·당시/현재 비교·타임라인·자동 근거 연결은
2차(#353). 패턴 분석·편향 점검·품질 점수·거래 결과 연동은 3차(#354). FE 계약 매핑은 FE
트랙(`project_stock_frontend#242`).
