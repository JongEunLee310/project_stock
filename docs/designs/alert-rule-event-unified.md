# BE 설계: 알림 관제 통합 모델 · 규칙 엔진 (ADR-013 구현)

상태: **초안(Draft)** — 2026-07-15(Opus). ADR-013(Signals/Alerts/Decision-Log 3-화면 책임
분리)이 위임한 후속 설계 문서다. 알림을 시그널 1:1 래퍼에서 벗어나
`AlertRule`·`AlertEvent`·`AlertDelivery`·`NotificationChannel` 4개 도메인으로 재편하는 필드·
enum·API 계약·엔진 흐름·마이그레이션을 확정한다. **구현은 본 문서를 정본으로 따른다.**

## 배경

현재 알림 스택은 세 갈래로 분산되어 있다.

- `app/domains/alerts` — `Alert`는 `signal_id` + `dedup_key` + 읽음 상태만 가진 시그널 1:1
  래퍼다(`AlertService.create_alert(user_id, signal)`). ADR-013이 지목한 "알림 = 시그널의
  그림자" 문제의 원인.
- `app/domains/alert_candidates` — ADR-013 이전 v0.2 기능. 중요도·근거를 가진 후보 알림
  (`AlertCandidate`: candidate_type·importance·evidence). 규칙/채널 개념은 없다.
- `app/domains/watchlists`의 `WatchlistAlertRuleService` — watchlist 스코프의 템플릿 4종
  토글(`PRICE_SPIKE`·`NEWS_RISK_HIGH`·`AI_JUDGMENT_CHANGE`·`THEME_OVERHEAT`). 대상이
  watchlist에 한정되고 채널·이벤트 이력이 없다.

ADR-013은 `AlertRule`(전달 조건·채널·활성)과 `AlertEvent`(실제 발생 이력)로의 분리를
결정하고 상세는 본 문서로 위임했다. 후속 이슈 #255는 미이행 상태로 닫혔으므로 본 설계로
재개한다.

## 설계 범위(MVP = 1차 + 알림 상세 근거)

포함: 통합 모델 4테이블 · 템플릿 기반 규칙 CRUD · 활성/일시정지 · 앱(APP) 채널 · Overview
요약 · 최근 알림 목록/상세(근거)/읽음 · 중복 방지(dedup·cooldown·state-transition) · 스케줄러
주기 평가 엔진.

제외(2차 이후): 이메일·Discord·Slack 발송 어댑터 · 복합 조건(`all`/`any` 다중) · 일일 요약
digest · SSE 실시간 · 사용자 정의 수식 · Redis 큐 기반 Evaluator/Delivery 워커 분리.

---

## 1. 도메인 모델

PK는 repo 관례(int PK + `ForeignKey`)를 따른다(스펙의 UUID는 미채택). 시각 컬럼은 기존
도메인과 동일하게 `DateTime(timezone=True)` + `server_default=func.now()`.

### 1.1 `alert_rules` (신규 도메인 `app/domains/alert_rules`)

| 컬럼 | 의미 | 비고 |
| --- | --- | --- |
| `id` | PK | int |
| `user_id` | 소유자 | FK `users.id`, index |
| `name` | 사용자 표시용 규칙명 | 조건과 분리(자유 편집) |
| `source` | 규칙 출처 | enum `AlertRuleSource` (SYSTEM·USER) |
| `template_type` | 생성에 사용된 템플릿 | enum `AlertTemplateType`, nullable |
| `target_type` | 감시 대상 유형 | enum `AlertTargetType` |
| `target_id` | 대상 식별자 | nullable(예: symbol 문자열, watchlist/portfolio id) |
| `condition` | 구조화 조건 | JSON(§4 스키마) |
| `severity` | 중요도 | enum `AlertSeverity` |
| `channels` | 전달 채널 목록 | JSON(list[str], enum `AlertChannel` 값) |
| `enabled` | 활성 여부 | bool, index |
| `cooldown_seconds` | 재발송 억제 시간 | int, 템플릿 기본값 |
| `delivery_policy` | 재알림 정책 | enum `AlertDeliveryPolicy` |
| `last_triggered_at` | 마지막 발생 시각 | nullable, 목록 표시용 |
| `created_at` / `updated_at` | 생성·수정 시각 | |

책임: 무엇을·어떤 조건에서·어디로 감시할지 보관. 조건 평가는 엔진(§5)이 수행하며 규칙은
상태만 갖는다.

### 1.2 `alert_events` (신규 도메인 `app/domains/alert_events`)

| 컬럼 | 의미 | 비고 |
| --- | --- | --- |
| `id` | PK | int |
| `rule_id` | 발생 근거 규칙 | FK `alert_rules.id`, index |
| `user_id` | 소유자 | FK, index |
| `target_type` / `target_id` | 발생 대상 | 규칙에서 복제 |
| `asset_id` | 관련 종목 | FK `assets.id`, nullable, index |
| `title` | 알림 제목 | |
| `message` | 사용자 전달 메시지 | 자연어 |
| `severity` | 중요도 | enum `AlertSeverity` |
| `triggered_value` | 발생 시점 조건 값 | JSON(현재값·임계값·이전값) |
| `evidence` | 근거 목록 | JSON(list), 상세 화면용 |
| `dedup_key` | 중복 방지 키 | §6, index |
| `read_at` | 읽음 시각 | nullable |
| `triggered_at` | 발생 시각 | index, 정렬 기준 |

제약: `UniqueConstraint(user_id, dedup_key)` — 기존 `alerts`와 동일 패턴으로 중복 삽입 차단.

책임: 규칙 충족으로 실제 발생한 통지 이력. `alerts` + `alert_candidates`를 대체한다.
상세 화면(발생 조건·현재값·임계값·이전값·근거)에 필요한 필드를 자체 보유한다.

### 1.3 `alert_deliveries` (도메인 `app/domains/alert_events` 하위)

| 컬럼 | 의미 | 비고 |
| --- | --- | --- |
| `id` | PK | int |
| `alert_event_id` | 대상 이벤트 | FK `alert_events.id`, index |
| `channel` | 전달 채널 | enum `AlertChannel` |
| `status` | 전달 상태 | enum `AlertDeliveryStatus` (PENDING·SUCCESS·FAILED) |
| `attempted_at` | 시도 시각 | |
| `delivered_at` | 완료 시각 | nullable |
| `error_code` | 실패 코드 | nullable |

책임: 채널별 전달 결과 기록. MVP는 `APP` 채널만 즉시 `SUCCESS`로 기록(외부 발송 없음).
이메일/Discord/Slack 어댑터는 2차에서 이 테이블 위에 붙인다.

### 1.4 `notification_channels` (신규 도메인 `app/domains/notification_channels`)

| 컬럼 | 의미 | 비고 |
| --- | --- | --- |
| `id` | PK | int |
| `user_id` | 소유자 | FK, index |
| `channel_type` | 채널 유형 | enum `AlertChannel` |
| `configuration` | 채널 설정 | JSON(이메일 주소·webhook 등) |
| `enabled` | 활성 여부 | bool |
| `verified_at` | 검증 완료 시각 | nullable(테스트 발송 성공 시) |

책임: "어디로 알릴지"를 규칙과 분리해 보관. MVP는 `APP` 채널을 사용자별 기본 1건으로 보장,
`EMAIL`은 미검증 placeholder까지만 허용(발송 어댑터는 2차).

---

## 2. Enum 정의 (신규 `app/domains/alert_rules/types.py` 등)

| Enum | 값 | 비고 |
| --- | --- | --- |
| `AlertRuleSource` | SYSTEM · USER | 시스템 규칙은 삭제 불가·음소거만 |
| `AlertTargetType` | SYMBOL · WATCHLIST · PORTFOLIO · TOPIC · MARKET | MVP 활성: SYMBOL·WATCHLIST·PORTFOLIO. TOPIC·MARKET은 enum 등록만·비활성(데이터 인프라 선행) |
| `AlertMetric` | NEWS_RISK · PRICE_CHANGE_1D · SIGNAL_CHANGED · AI_JUDGMENT_CHANGED · THEME_HEAT · POSITION_WEIGHT · EARNINGS_DATE · TOPIC_IMPACT_SCORE | TOPIC_IMPACT_SCORE는 뉴스·인사이트 토픽 인프라(보류) 선행이라 등록만·비활성. 나머지는 보유 데이터로 MVP 활성 |
| `AlertOperator` | EQ · GTE · LTE · CHANGED | MVP 4종. GT/LT/CROSSED 등은 후속 |
| `AlertSeverity` | LOW · MEDIUM · HIGH · CRITICAL | UI는 LOW·MEDIUM·HIGH 노출, CRITICAL은 내부용 |
| `AlertChannel` | APP · EMAIL · DISCORD · SLACK | MVP는 APP 발송, EMAIL placeholder |
| `AlertDeliveryPolicy` | ONCE_PER_TRANSITION · ONCE_PER_DAY | MVP 2종 |
| `AlertDeliveryStatus` | PENDING · SUCCESS · FAILED | |
| `AlertTemplateType` | HOLDING_NEWS_RISK · WATCHLIST_AI_JUDGMENT · EARNINGS_D3 · POSITION_WEIGHT_OVER · NEWS_RISK_HIGH · TOPIC_IMPACT_SURGE | 템플릿 카탈로그(§3) |
| `AlertEventStatus` | UNREAD · READ | `read_at` 파생, 필터용 |

지표별 값 도메인: `NEWS_RISK`/`THEME_HEAT`는 기존 `watchlists.types`의 `NewsRisk`·
`ThemeHeat` enum 값을 재사용한다. `AI_JUDGMENT_CHANGED`·`SIGNAL_CHANGED`는 상태 전이
감지(operator `CHANGED`)로만 평가한다.

---

## 3. 템플릿 카탈로그

규칙 생성은 SQL 편집기가 아니라 템플릿 선택 → 대상 → 조건 미세조정 → 채널 순서. 각 템플릿은
기본 `condition`·`severity`·`cooldown_seconds`·`delivery_policy`·기본 채널을 미리 채운다.

| `template_type` | 라벨 | 기본 대상 | 기본 조건(자연어) |
| --- | --- | --- | --- |
| `HOLDING_NEWS_RISK` | 보유 종목 위험 증가 | PORTFOLIO | 뉴스 위험도 High 이상 |
| `WATCHLIST_AI_JUDGMENT` | 관심 종목 AI 판단 변경 | WATCHLIST | AI 판단 상태 전이 |
| `EARNINGS_D3` | 실적 발표 3일 전 | WATCHLIST | 실적 발표 D-3 |
| `POSITION_WEIGHT_OVER` | 단일 종목 비중 초과 | PORTFOLIO | 비중 15% 초과 |
| `NEWS_RISK_HIGH` | 뉴스 위험도 High 이상 | SYMBOL | 뉴스 위험도 High 이상 |
| `TOPIC_IMPACT_SURGE` | 토픽 영향도 급등 | TOPIC | 영향도 80 이상 (토픽 인프라 선행·MVP 비활성) |

`GET /alert-rules/templates`가 이 카탈로그를 반환한다. `TOPIC_IMPACT_SURGE`는 비활성으로
표기해 반환하고, 토픽 인프라가 도입되면 활성화한다. 기존 `WatchlistAlertRuleService`의 4종
템플릿은 이 카탈로그로 흡수한다(§7).

---

## 4. 조건(condition) JSON 스키마

조건은 자유 문자열이 아니라 구조화 JSON으로 저장한다. MVP는 단일 조건과 `all`(AND) 배열만
지원한다.

- 단일 조건 필드: `metric`(enum `AlertMetric`) · `operator`(enum `AlertOperator`) ·
  `value`(지표별 값 도메인).
- 복합: `{"all": [<condition>, ...]}` 형태. `any`(OR)는 2차.

서비스 계층에 조건 검증기(`validate_condition`)를 두어 지원하지 않는 metric·operator·값
도메인 조합을 `422 VALIDATION_ERROR`로 차단한다. FE에는 JSON을 노출하지 않고 자연어로
번역해 표시한다("뉴스 위험도가 높음 이상일 때").

---

## 5. 알림 엔진 (스케줄러 주기 평가)

ADR-003의 스케줄러 접근을 따른다. HTTP 요청 경로에서 평가하지 않는다. Redis 큐 기반
Evaluator/Delivery 워커 분리는 2차.

흐름(스켈레톤):

1. 스케줄러 주기 작업이 `enabled=true` 규칙을 대상 유형별로 조회한다.
2. 규칙의 대상 자산 목록을 확정하고 자산별 지표 스냅샷을 수집한다(기존 `signals`·
   `watchlists.trend_service`·`prices`·`portfolios`·`earnings` 재사용). 신규 수집 파이프라인은
   만들지 않는다. 대상을 확정하지 못하면 `NO_TARGET`, 대상은 있으나 계산할 데이터가 없으면
   `NO_DATA`로 구분한다. ADR-015에 따라 여러 자산의 지표를 하나로 합치지 않는다.
3. 조건 평가기가 `condition`을 자산별 스냅샷에 각각 적용한다.
4. 충족한 자산마다 중복·cooldown·state-transition 검사(§6)를 통과한 건만 `AlertEvent` 생성.
   이벤트는 (규칙 × 자산) 단위이며 `asset_id`로 어느 종목인지 가리킨다.
5. 규칙 `channels`에 대해 `AlertDelivery` 생성. MVP는 `APP`을 즉시 `SUCCESS`로 기록.
6. 규칙 `last_triggered_at` 갱신.

함수 스켈레톤(시그니처 · 책임만):

- `MetricSnapshotProvider.get_snapshots(rule, as_of) -> list[MetricSnapshot]` — 대상 자산을
  확정하고 자산별 스냅샷을 반환. 각 스냅샷은 자신이 어느 자산의 것인지 담는다.
- `AlertEvaluator.evaluate_rule(rule, snapshot) -> AlertEvaluationResult` — 단일 규칙을 단일
  자산 스냅샷에 대해 평가, 충족 여부·triggered_value·evidence 반환.
- `AlertEngineService.run_cycle() -> AlertCycleSummary` — 활성 규칙 순회, 규칙마다 자산별
  평가·이벤트/전달 생성 오케스트레이션. 스케줄러 job에서 호출.
- `AlertDedupService.should_emit(rule, result, asset_id) -> bool` — (규칙 × 자산) 단위의
  dedup_key·cooldown·전이 검사.

**경계**: 엔진은 시그널을 생성하지 않는다. 이미 존재하는 지표·시그널의 변화만 감시한다
(ADR-013 §15).

---

## 6. 중복 방지

세 가지를 조합한다. ADR-015에 따라 판정 단위는 (규칙 × 자산)이다.

- **dedup_key**: `rule_id` + `target_id` + `asset_id` + `event_fingerprint`(조건 충족 상태의
  해시). `alert_events`의 `UniqueConstraint(user_id, dedup_key)`로 물리 차단.
- **cooldown**: 규칙 `cooldown_seconds` 내 동일 규칙·동일 자산 재발송 금지. 판정 근거는
  `alert_events`에서 조회한 (규칙, 자산)의 최근 발생 시각이다. `alert_rules.last_triggered_at`은
  규칙이 마지막으로 발동한 시각을 보여주는 표시용으로만 남는다.
- **state-transition**: `delivery_policy=ONCE_PER_TRANSITION`이면 상태가 실제로 전이될 때만
  발생(예: Medium→High). High 유지 중 재발생 금지. High→Critical 상승은 새 이벤트. 전이는
  자산별 이전·현재 스냅샷으로 판정하며 다른 자산의 상태는 영향을 주지 않는다.
  `ONCE_PER_DAY`이면 자산·규칙당 하루 1회로 제한한다.

---

## 7. 기존 인프라 흡수·전환

전환기에는 계약을 병존시키고 단계적으로 정리한다.

- `alert_candidates` → `alert_events`로 개념 통합. `importance`→`severity`, `evidence`→
  `evidence`, `candidate_type`→규칙 기반 발생. 신규 발생 경로는 엔진으로 일원화하고, 구
  `/api/v1/alert-candidates` 엔드포인트는 deprecated 상태로 읽기 호환을 유지한 뒤 후속 이슈에서
  제거한다.
- `alerts`(시그널 래퍼) → `SIGNAL_CHANGED` 시스템 규칙이 생성하는 `alert_events`로 대체.
  신규 이벤트 조회·읽음 계약은 `/api/v1/alert-events`에 두고, 구 `/api/v1/alerts` 엔드포인트는
  deprecated 상태로 병존시킨다. 분석 파이프라인의 `AlertService.create_alert` 직접 호출 경로는
  엔진 규칙 평가로 전환한다. `/api/v1/alerts/overview`는 통합 관제 요약 경로로 유지한다.
- `WatchlistAlertRuleService`의 템플릿 4종 → `alert_rules`(target_type=WATCHLIST) 레코드로
  이관. 기존 토글 UI는 규칙 목록으로 흡수.
- 데이터 백필은 필수 아님(신규 이벤트부터 통합 테이블 사용). 구 테이블은 읽기 호환 유지 후
  후속 이슈에서 제거.

마이그레이션: Alembic으로 4개 테이블 신설. 구 테이블 삭제는 별도 후속 마이그레이션.

---

## 8. API 계약 (스켈레톤)

모든 엔드포인트 `Auth: Required`, 소유권 `user_id` 기준(타인 접근 `*_FORBIDDEN`).

| Method · Path | 책임 |
| --- | --- |
| `GET /api/v1/alerts/overview` | 요약(active_rule_count·triggered_today_count·high_severity_count·paused_rule_count·unread_count·as_of) |
| `GET /api/v1/alert-rules` | 규칙 목록(필터: status·target_type, 공통 pagination) |
| `GET /api/v1/alert-rules/templates` | 템플릿 카탈로그(§3) |
| `POST /api/v1/alert-rules` | 규칙 생성(template 기반) |
| `PATCH /api/v1/alert-rules/{id}` | 규칙 수정(name·condition·channels·severity 등) |
| `POST /api/v1/alert-rules/{id}/pause` | 일시정지(enabled=false) |
| `POST /api/v1/alert-rules/{id}/resume` | 재개(enabled=true) |
| `DELETE /api/v1/alert-rules/{id}` | 삭제(SYSTEM 규칙은 불가) |
| `GET /api/v1/alert-events` | 최근 알림 목록(필터: severity·read·target_type, 공통 pagination) |
| `GET /api/v1/alert-events/{id}` | 알림 상세(발생 조건·현재값·임계값·이전값·근거) |
| `POST /api/v1/alert-events/{id}/read` | 단건 읽음 |
| `POST /api/v1/alert-events/read` | 다건 읽음(alert_ids) |
| `GET /api/v1/notification-channels` | 채널 목록 |
| `POST /api/v1/notification-channels` | 채널 추가 |

`POST /notification-channels/{id}/test`(테스트 발송)는 외부 채널 도입(2차)과 함께 추가한다.

구 `/api/v1/alerts`(시그널 래퍼)와 `/api/v1/alert-candidates` 계약은 deprecated 상태로 병존하며,
소비처 이관이 끝난 뒤 후속 이슈에서 제거한다. `/api/v1/alerts/overview`는 이 deprecated 범위에
포함하지 않는다.

파생 뷰 타입은 'DTO'가 아닌 'projection'으로 명명한다(예: `AlertRuleProjection`·
`AlertEventProjection`·`AlertOverviewProjection`).

---

## 9. 서브이슈 분해

**BE 에픽**(본 문서 기준):

- B1 통합 모델 4테이블 + Alembic 마이그레이션 (재개된 #255).
- B2 `alert_rules` 도메인: 템플릿 카탈로그 + CRUD + pause/resume + `overview`.
- B3 `alert_events` 도메인: 목록/상세(근거)/읽음 + 구 `alerts`·`alert_candidates` 흡수.
- B4 `notification_channels` 도메인(APP 기본).
- B5 알림 엔진: 스케줄러 평가 + dedup/cooldown/transition + `AlertDelivery`(APP).

**FE 에픽**(FE #133 확장, 계약은 B1~B4 선행):

- F0 알림 아이콘 교체(FiBell, Sidebar+Topbar) — BE 무관 선행.
- F1 알림 API 클라이언트 · `alertKeys` 재편 + 상단 요약 카드.
- F2 규칙 관리(목록 테이블 + 생성/수정 drawer + 조건 자연어 번역).
- F3 최근 내역 패널 + 알림 상세(근거) + 채널 설정 + 페이지 통합 레이아웃.
- FE #134 Signals → Rule Builder deep-link(기존 이슈, 연계).

---

## 10. 검증

- `uv run ruff check .` / `uv run mypy .` / `uv run pytest`
- 픽스처는 실제 계약 형태로 구성(스냅샷 계약 테스트에 신규 응답 구조 반영).

## Related Documents

- ADR-013 (Signals/Alerts/Decision-Log 3-화면 책임 분리) — 본 문서의 상위 결정.
- ADR-003 (Scheduler approach) — 엔진 실행 방식.
- ADR-009 (CloudSafe projection) — 파생 뷰 명명.
- `app/domains/alerts`, `app/domains/alert_candidates`, `app/domains/watchlists`
  (`alert_rule_service.py`) — 흡수 대상.
- FE #133(Alerts 재설계) · FE #134(Signals deep-link).
