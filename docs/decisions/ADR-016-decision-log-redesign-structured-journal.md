# ADR-016: Decision-Log Redesign — Structured Journal (Multi-table, Polymorphic Target, Snapshot Immutability)

## Status

Proposed — supersedes ADR-006.

## Context

ADR-006이 도입한 `decision_logs` 도메인은 단일 테이블에 판단 본문과 맥락 스냅샷을
모두 담는 최소 저널이었다. 실제 화면 설계를 진행하면서, 판단 기록 페이지가 "투자 결과를
적는 일기장"이 아니라 **의사결정 당시의 정보·가설·위험·재검토 조건을 구조적으로 저장하고
나중에 복기하는 화면**이어야 한다는 요구가 확정됐다. 이 목적을 단일 테이블 모델로는
지탱하기 어렵다.

ADR-006 모델과 목표 사이의 격차는 다음과 같다.

1. **대상이 종목에만 묶여 있다.** 현재 모델은 `ticker` 단일 컬럼이다. 판단 대상은 종목뿐
   아니라 포트폴리오, 토픽, 섹터, 시장일 수 있다.
2. **판단 유형이 매매 중심이다.** 현재 `decision_type`은 `BUY`/`SELL`/`HOLD` 등 매매 실행에
   가깝다. 목표는 `WATCH`·`RESEARCH_REQUIRED`·`NO_ACTION`처럼 "아직 결론을 내리지 않음",
   "의도적으로 아무 것도 하지 않음"까지 판단으로 기록하는 것이다. 판단 기록은 주문 기록과
   다르다.
3. **근거가 텍스트 한 덩어리다.** 현재 `reason`은 자유 텍스트다. 목표는 긍정 근거와 반대
   근거를 분리하고, 각 근거를 당시 버전이 고정된 외부 자료(Signal·Research·News 등)와
   연결하는 것이다.
4. **인지 위험이 문자열 배열이다.** 현재 `cognitive_risks`는 검증 없는 JSON 배열이다.
   목표는 위험 유형과 심각도를 구조화해 나중에 패턴을 집계하는 것이다.
5. **재검토 조건이 없다.** 현재는 `reviewed_at` 타임스탬프만 있고 "왜, 언제 다시 봐야
   하는가"를 저장하지 않는다. 목표는 날짜 조건과 이벤트 조건을 함께 저장하고, 조건 충족을
   감시하는 것이다.
6. **복기와 버전 관리가 없다.** 확정된 판단을 조용히 수정하면 과거 판단을 미화하게 된다.
   목표는 원본을 보존하고, 판단 품질과 투자 결과를 분리해 복기하는 것이다.
7. **상태 모델이 얕다.** 현재 `OPEN → REVIEWED → CLOSED`는 초안/확정을 구분하지 못한다.

이 격차는 스냅샷 컬럼 몇 개를 더하는 문제가 아니라 도메인 구조의 문제다. 따라서 단일
테이블 확장이 아니라 재설계로 간다.

## Decision

`decision_logs` 도메인을 다음 원칙으로 재설계하고 ADR-006을 supersede한다. 확정된
필드·enum·API 계약은 `docs/designs/348-decision-log-redesign.md`(계약 확정 절)에 둔다.

### 1. 판단 본문과 부속 정보를 테이블로 분리한다

단일 테이블 대신 판단 본문(`decision_logs`)과 부속 정보를 별도 테이블로 나눈다.

- `decision_logs` — 판단 본문(대상·유형·가설·확신·상태·라이프사이클 타임스탬프).
- `decision_evidence` — 근거·반대 근거(당시 버전/스냅샷 보존).
- `decision_risks` — 인지·시장 위험(유형·심각도).
- `decision_review_triggers` — 재검토 조건(날짜·이벤트).
- `decision_snapshots` — 판단 당시 수치 상태(immutable JSON).
- `decision_reviews` — 복기 결과(판단 품질·투자 결과 분리). 2차에 채우되 스키마는 이번에
  예고한다.

부속 정보를 자유 JSON이 아니라 테이블로 두는 이유는, 근거 관계·위험 유형·재검토 조건이
집계·필터·감시의 대상이기 때문이다. ADR-006이 자유 JSON을 택한 근거(맥락이 이질적이고
불안정하다)는 여전히 `decision_snapshots.data`에만 남긴다 — 수치 스냅샷은 형태가 계속
바뀌므로 자유 JSON이 맞다.

### 2. 대상을 다형화한다

`ticker` 단일 컬럼을 `target_type` + `target_id` + `symbol`(nullable)로 대체한다.
`target_type`은 `SYMBOL | PORTFOLIO | TOPIC | SECTOR | MARKET`. `symbol`은 종목 대상일 때만
채워, 종목 필터 조회를 단순화한다.

### 3. 판단 유형을 매매 중심에서 판단 중심으로 바꾼다

`decision_type`을 9종으로 재정의한다: `WATCH`, `RESEARCH_REQUIRED`, `HOLD`, `BUY_REVIEW`,
`SELL_REVIEW`, `REDUCE_REVIEW`, `REBALANCE_REVIEW`, `THESIS_INVALIDATED`, `NO_ACTION`.
"검토(REVIEW)"는 매매 실행이 아니라 검토 단계임을 이름에 드러낸다. `NO_ACTION`도 하나의
판단으로 기록한다.

### 4. 스냅샷은 immutable로 보존한다

판단 당시의 가격·밸류에이션·뉴스 위험도·시그널·포트폴리오 비중을 확정 시점에
`decision_snapshots`로 캡처하고, 이후 최신 값으로 덮어쓰지 않는다. 상세 화면의 "당시 대
현재" 비교는 스냅샷과 실시간 조회를 나란히 두는 것이지 스냅샷을 갱신하는 것이 아니다.

### 5. 상태 모델을 확장하고 확정 후 수정을 제한한다

`DRAFT → ACTIVE → REVIEW_DUE → REVIEWED → CLOSED`(+`CANCELLED`)로 확장한다.

- `DRAFT` — 작성 중. 자유 수정.
- `ACTIVE` — 확정(`activate`). 스냅샷 캡처·근거 버전 고정·재검토 조건 등록. 이후 핵심 본문
  수정 제한.
- `REVIEW_DUE` — 재검토 날짜/조건 도달.
- `REVIEWED` — 복기 1회 이상 작성.
- `CLOSED` — 추적 종료.
- `CANCELLED` — 확정 전 취소.

확정 후 본문을 조용히 고치는 대신, 새 버전을 만들어 이전 판단을 대체 연결한다(2차 `revise`).
1차는 forward-only 전이를 강제하지 않는다(ADR-006과 동일하게 MVP 유예).

### 6. 판단 품질과 투자 결과를 분리한다

복기(`decision_reviews`)는 투자 결과(수익률·벤치마크·MDD)와 판단 품질(근거 충분성·반대 근거
검토·위험 인식·재검토 명확성·규칙 준수)을 별도 필드로 저장한다. 결과가 좋아도 과정이
나쁠 수 있고 그 반대도 가능하다. 이 분리가 없으면 판단 기록이 단순 승패표가 된다.

### 7. AI는 판단을 대신하지 않는다

AI는 구조화·누락 안내·반대 근거 후보·자동 근거 연결·복기 요약·패턴 분석으로 역할을
제한한다. AI 제안은 사용자 확인 후에만 정식 필드로 저장한다. AI가 최종 판단을 확정하거나
사용자 이름으로 근거를 작성하거나 과거 기록을 조용히 수정하지 않는다.

### 8. 소유권과 wire 컨벤션은 유지한다

소유권은 `user_id` 기준, 전 엔드포인트 인증 필수, 타인 접근은 `*_FORBIDDEN`. wire 컨벤션은
기존과 동일하게 snake_case 필드, 금액 Decimal 문자열, 시각 `UtcDatetime`, 공통 엔벨로프
`ApiResponse`를 따른다.

## Alternatives

- **단일 테이블 확장(ADR-006 유지 + 컬럼 추가).** 기각. 근거·위험·재검토 조건·복기는 1:N이며
  집계·감시 대상이라 컬럼/JSON로 눌러 담으면 필터와 트리거를 만들 수 없다. 대상 다형화와
  버전 관리도 단일 테이블로는 어색하다.
- **전면 이벤트 소싱(모든 변경을 이벤트 로그로).** 기각. 감사 요구가 아직 그 수준이 아니고
  MVP 대비 과설계다. 버전 관리는 `revise`로 새 레코드를 연결하는 최소치로 충분하다.
- **재검토 트리거를 Alert 도메인에 바로 저장.** 기각. 판단 기록과 알림 규칙은 별도 도메인으로
  유지한다(ADR-013 경계). 판단은 재검토 조건을 `decision_review_triggers`로 소유하고, 알림
  발송이 필요하면 2차에서 Alert와 연동한다.
- **스냅샷도 테이블 컬럼으로 타입 고정.** 기각. 수치 스냅샷 형태는 계속 진화하므로
  `decision_snapshots.data`는 자유 JSON을 유지한다. 이 부분만은 ADR-006의 판단을 계승한다.

## Consequences

- 쉬워지는 것: 근거/위험/재검토가 구조화돼 필터·집계·감시·패턴 분석이 가능해진다. 대상이
  종목을 넘어 포트폴리오·토픽까지 확장된다. 판단 품질과 결과가 분리돼 저널이 승패표로
  전락하지 않는다. 확정 후 미화가 버전 관리로 막힌다.
- 어려워지는 것/리스크: 테이블이 1개에서 6개로 늘어 생성/조회가 다중 테이블 트랜잭션이
  된다. ADR-006 계약(단일 테이블·enum·상태)과 하위호환이 깨진다. 기존 `decision_logs`는 현재
  테스트·mock 수준이라 실데이터 이관 부담은 낮지만, 마이그레이션에서 전환 또는 재생성
  전략을 명시해야 한다.
- 새 DB 테이블·스키마 변경이므로 이 작업은 **human-gate**(`human-gate-policy.md`: DB 스키마)
  이며, 자동 구현 단계 실행 전 사람 승인을 요구한다(ADR-005 #6). 대상 이슈는 BE #349.

## Follow-up

- forward-only 라이프사이클 전이 강제(`CLOSED → DRAFT` 등 거부)는 편집 UI 안정화 후 전용
  에러 코드로 도입.
- 안정적·쿼리 가능해진 스냅샷 필드를 타입 컬럼으로 승격(ADR-006 Follow-up 계승).
- 이벤트 기반 재검토 트리거와 Alert 연동, 복기, 버전 관리(`revise`)는 2차(BE #353).
- 패턴 분석·편향 점검 Agent·품질 점수·거래 결과 연동은 3차(BE #354). AI는 점검 후보만
  제시하고 확정 진단을 하지 않는다.

## Related Documents

- ADR-006 (Decision-Log Journaling Domain) — 본 ADR이 supersede한다.
- ADR-013 (Signals / Alerts / Decision-Log 3-화면 경계) — 판단 기록의 화면 책임.
- `docs/designs/348-decision-log-redesign.md` — 재설계 계약 확정(테이블·enum·API 스켈레톤).
- `docs/designs/decision-log-domain.md` — ADR-006 시절 계약(이력).
- Epic BE #347, FE `project_stock_frontend#242`.
