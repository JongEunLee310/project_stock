# ADR-006: Decision-Log Journaling Domain (Snapshots, Lifecycle, Canonical Enums)

## Status

Proposed

## Context

프론트엔드에는 투자 판단 저널 화면(`/decision-log`)이 있으나 백엔드 대응물이 없고,
항목은 클라이언트 로컬 mock 데이터로만 존재한다. API 계약 정렬 작업
(`docs/api/contract-alignment.md`, gap **G10**, 파생 항목 **N1**, 결정 **Q7**)에서, 이
저널은 새 백엔드 도메인이 영속화해 세션·기기 간에 판단이 살아남아야 함을 확정했다.

사람/AI 투자 판단을 위한 영속 도메인은 향후 작업에 영향을 주는 몇 가지 지속적 선택을
제기한다:

1. **판단 시점에 무엇을 포착하는가.** 판단은 그것이 내려진 맥락(밸류에이션, 뉴스,
   포트폴리오 상태, AI 분석)과 함께라야 의미가 있다. 그 맥락은 이질적이고, 관계형
   스키마보다 빠르게 진화할 것이다.
2. **판단이 어떻게 진화하는가.** 기록된 판단은 나중에 검토되고 종결된다 — 정적 레코드가
   아니다. 이는 라이프사이클을 필요로 한다.
3. **FE/BE 경계의 enum 표현**을, 나머지 계약(`C8`)과 일관되게.

## Decision

기존 도메인 패턴(`model` / `repository` / `service` / `schema` + router)을 따르는 새
`decision_logs` 도메인을 추가하며, 다음을 둔다:

1. **컨텍스트 스냅샷을 nullable 자유형 JSON으로.** `valuation_snapshot`,
   `news_snapshot`, `portfolio_snapshot`, `ai_analysis_snapshot`, `cognitive_risks`를
   MVP에서 **고정 하위 스키마 없이** JSON(객체 / 문자열 배열)으로 저장한다. 백엔드는 그
   형태를 검증하거나 해석하지 않는다.
2. **명시적 라이프사이클** `decision_status`: `OPEN → REVIEWED → CLOSED`,
   `decided_at` / `reviewed_at` / `closed_at`와 짝. `PATCH`가 전이를 구동하며, 해당
   상태에 처음 진입할 때 대응 타임스탬프가 찍힌다. MVP는 forward-only 순서를 강제하지
   **않는다**(Follow-up 참조).
3. **정본 enum은 영어 `UPPER_SNAKE`**로 wire에 싣고(`decision_type`, `decision_status`,
   `created_by`), FE 표현 계층에서 한국어로 지역화한다 — 다른 모든 계약 enum과 같은
   규칙(`C8`).
4. **소유권**은 `user_id` 기준. 모든 엔드포인트는 인증을 요구하며 호출자 본인 행만
   노출한다(교차 사용자 접근 시 `*_FORBIDDEN`).

확정된 필드/enum/엔드포인트 계약은 `docs/designs/decision-log-domain.md`(§ 계약 확정)에
있다. 새 Alembic 마이그레이션이 테이블을 생성한다.

## Alternatives

- **모든 스냅샷 필드를 타입 컬럼으로.** MVP에서 기각: 포착 맥락이 이질적이고 불안정해,
  컬럼에 고정하면 형태 변경마다 마이그레이션을 강제한다. 자유형 JSON은 그 비용을
  미룬다. 필드가 안정적이라고 입증되면 나중에 컬럼으로 승격할 수 있다.
- **스냅샷 없음(판단 텍스트만 저장).** 기각: 판단 저널을 가치 있게 만드는 근거 맥락을
  잃고, 나중에 되살리는 것도 어차피 스키마 마이그레이션이다. 컬럼은 로직 없고 nullable
  이라 지금 비용이 미미하다.
- **라이프사이클 없음(불변 로그).** 기각: FE가 이미 검토/결과 상태를 모델링한다.
  `OPEN→REVIEWED→CLOSED`가 이를 지탱하는 최소치다.
- **wire에 한국어 enum 값.** 기각: `C8`과 불일치하며, 표시 언어를 계약에 섞으면 표현이
  API로 새어 나간다.

## Consequences

- 쉬워지는 것: 저널이 영속·멀티기기가 된다. 스냅샷 형태가 마이그레이션 없이 진화할 수
  있다. FE는 enum-라벨 매핑으로 적응한다(이미 그 패턴).
- 어려워지는 것/리스크: 자유형 JSON은 쿼리 불가·스키마 미보장이라, 호출자는 누락/느슨한
  스냅샷 필드를 감내해야 한다. forward-only 강제 없는 라이프사이클은 MVP에서 순서를
  벗어난 상태 편집을 허용한다.
- 새 DB 테이블(`decision_logs`) ⇒ 이 작업은 **human-gate** 항목이며
  (`human-gate-policy.md`: DB 스키마), 자동 Codex 구현 단계 실행 전 사람 승인을
  요구한다(ADR-005 #6).

## Follow-up

- 저널에 편집 UI가 생기면, 전용 에러 코드로 forward-only 라이프사이클 전이를 강제
  (`CLOSED → OPEN` 등 거부).
- 안정적 + 쿼리 가능해진 스냅샷 필드를 타입 컬럼으로 승격.
- FE 어댑터(`ticker↔symbol`, `reason↔rationale`, `decision_status↔outcome`,
  `cognitive_risks↔cognitiveRisks`)는 FE 트랙 범위(FE#48 follow-up)이며 본 ADR이 아니다.

## Related Documents

- `docs/designs/decision-log-domain.md` (작업지도 + 계약 확정)
- `docs/api/contract-alignment.md` (G10, N1, Q7)
- `JongEunLee310/project_stock#102`
- `docs/decisions/ADR-002-domain-error-code-enum.md`
- `docs/decisions/ADR-005-allow-claude-code-to-invoke-codex-exec.md`
