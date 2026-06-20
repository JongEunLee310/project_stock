# Domain Knowledge

`project_stock`는 투자 리서치와 감시 흐름을 지원하는 백엔드다. 이 문서는 코드에서
다시 추론해야 할 비즈니스 규칙·도메인 용어·정책 결정을 기록한다. 구현 세부는
`docs/designs/`, API 계약은 `docs/api/frontend-api-spec.md`를 기준으로 한다.

## Users

- 개인 투자자가 리서치와 감시 판단을 빠르게 확인하는 용도다.
- 사용자 범위 리소스(watchlist, portfolio, thesis, alert 등)는 인증이 필요하고
  타 사용자 리소스 접근은 거부된다(404/403).
- 시스템은 투자 판단을 돕는 정보만 제공하며 사용자를 대신해 매매하지 않는다.

## Business Rules

- **포트폴리오 집중도**: `concentration_threshold`(0~1)를 초과하면 과다 비중으로
  본다. 종목 비중과 섹터 비중 모두 시세 기반 `weight`(= 종목 시가평가액 / `total_value`)로
  판정하며, `total_value`는 현금(`cash_balance`)을 포함한다. 원가 기준 비중은
  `cost_weight`와 evidence(`cost_value`)로 추적만 한다.
- **매수 전 체크리스트**: 필수 4개 키(`valuation`, `news_overheated`,
  `portfolio_concentration`, `earnings_disclosure`)가 모두 체크되고 `memo`에 공백이
  아닌 내용이 있을 때만 `is_complete`가 true다. `decided_at`은 미완료 동안 null이며,
  처음 완료된 시점에 기록되고 완료가 유지되는 동안 보존된다.
- **시그널 만료**: `expires_at`이 없거나 미래면 유효하다. 목록 조회는 기본
  `include_expired=false`로 만료 시그널을 제외한다.
- **가설 충돌 분석**: 충돌 status는 `SUPPORTS`, `NEUTRAL`, `CONFLICTS` 중 하나이며,
  `invalidation_triggered`가 true면 가설 무효화 조건이 충족된 것으로 보고 리스크
  시그널 생성으로 이어진다.
- **알림 상태**: Alert는 `UNREAD` / `READ` / `DISMISSED`. Alert Candidate는
  `UNREAD` / `READ` / `CONFIRMED`이며 상태 전이 순서를 강제하지 않는다(아래 Policy
  Decisions 참고).

## Core Use Cases

- **관심종목 분석 플로우**: 뉴스 수집 → AI 요약 → 가설 충돌 판단 → 리서치 리포트와
  Signal/Alert 생성. 결과는 처리 종목 수, 생성된 news item / report / signal / alert
  수로 집계된다.
- **포트폴리오 집중도 점검**: 요약(섹터/현금 비중 포함) 조회와 집중도 점검 실행 →
  기준 초과 시 시그널 생성.
- **종목 리서치 보조**: 종목 기본 정보, 리서치 요약, 매수 전 체크리스트 제공.
- **알림 후보 검토**: 발송 전 후보를 사람이 검토해 읽음/확정 처리.

## Domain Terms

- **Asset**: 투자 대상 종목. symbol, name, market 보유.
- **Watchlist / Watchlist Item**: 관심종목 그룹과 항목(사유·태그·메모·우선순위).
- **Investment Thesis**: 투자 가설(요약, 리스크 요인, 무효화 조건). 종목당 최신본 사용.
- **Research Report**: 리서치 리포트(요약·근거·위험 수준·가설 충돌 상태).
- **Signal**: 투자 시그널. type(`WATCH`, `RISK_ALERT`, `THESIS_BROKEN`,
  `BUY_CANDIDATE`, `SELL_REVIEW`, `OVERHEATED`), score, risk_level, 만료 시각.
- **Alert**: 사용자에게 전달된 알림(시그널 기반). 읽음/숨김 처리 대상.
- **Alert Candidate**: 발송 전 알림 후보. type(`NEWS_SURGE`, `PRICE_MOVEMENT`,
  `DISCLOSURE`, `PORTFOLIO_CONCENTRATION`, `BUY_CHECKLIST_REQUIRED`), importance, status.
- **Portfolio / Position**: 포트폴리오와 보유 종목(수량·평균 매입가·집중도 기준·현금).
- **Buy Checklist**: 매수 전 점검 항목 묶음과 완료 판정.
- **Job Run**: 백그라운드 잡 실행 기록(상태·시각·에러).
- **Provider**: market/news/disclosure/portfolio 외부 연동 어댑터. `mock` 또는 `real`.

## Forbidden Misunderstandings

- 자동매매 시스템이 아니다. 주문 실행, 브로커 연동, 실거래 자동화, 포지션 자동
  조정을 제공하지 않는다.
- Alert와 Alert Candidate는 별개 도메인이다. Candidate는 발송 전 검토 단계이고
  기존 `alerts` 도메인을 대체하지 않는다.
- provider `real` 값은 설정 타입상 허용되지만 현재 실제 구현이 없는 provider는
  `NotImplementedError`로 실패한다. 로컬·테스트 기본값은 deterministic mock이다.
- 집중도 비중은 시세 기반이다. 원가 기준 비중(`cost_weight`)과 혼동하지 않는다.
- 패키지 버전(`pyproject.toml`의 `0.1.0`)과 문서상 마일스톤(v0.2)은 별개다.

## Edge Cases

- 포트폴리오 `total_value`는 현금을 포함하므로 비중 분모가 시가평가액 합과 다르다.
- 섹터 정보가 없는 종목은 섹터 비중 집계에서 `UNKNOWN`으로 묶인다.
- 시그널 `expires_at`이 null이면 만료 없이 항상 유효로 취급한다.

## Policy Decisions

ADR 수준이 아닌 프로젝트 정책 결정만 기록한다.

- **Alert Candidate 상태 전이 비강제**: `read`/`confirm` API는 현재 상태와 무관하게
  목표 상태(`READ`/`CONFIRMED`)로 표시한다. 단방향 전이 가드가 필요한 도메인 규칙이
  아니다. (`docs/designs/035-alert-candidate-api.md` Decisions, PR #77)
- **집중도 신호 기준 시세 비중 통일**: 집중도 신호 생성과 점수 산정 기준을 원가
  비중에서 시세 비중(`positions[].weight`)으로 통일하고, 원가 기준은
  `cost_weight`/evidence로 추적한다. (`docs/designs/034-portfolio-summary-api.md`
  Decisions, PR #76)
- **Health 응답 envelope 미사용**: `/health`, `/api/v1/health`,
  `/api/v1/health/readiness`는 모니터링 호환을 위해 공통 envelope를 쓰지 않는다.
