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
- **Provider**: market/news/disclosure/portfolio 외부 연동 어댑터. `market`은 `mock` /
  `yfinance` / `real`, `news`는 `mock` / `rss` / `real`, 나머지는 `mock` / `real`.
- **Universe**: 데이터 수집 대상 종목 집합. 관심종목(watchlist) + 보유종목(portfolio)의
  `(symbol, market)` 합집합이며, 가격·뉴스 수집 잡이 공통으로 쓴다. 뉴스 수집은 회사명 쿼리를
  위해 대상별 `name`을 함께 싣는다.
- **Price Bar / Raw Price**: `prices`는 정규화된 일봉(OHLCV), `raw_prices`는 정규화 전 원본
  payload 아카이브(`payload_hash`로 중복 스킵). 원본은 재처리·감사용으로 분리 저장한다.
- **Raw News Event**: `raw_news_events`는 정규화 전 원본 뉴스 아카이브(`url` unique로 중복
  스킵). 수집 잡이 붙인 `symbol`·`market` 태그(nullable)로 종목에 귀속되며, 정규화(News Item)
  전 단계다. 분석 파이프라인 경로에서 저장되는 이벤트는 태그가 null이다.

## Forbidden Misunderstandings

- 자동매매 시스템이 아니다. 주문 실행, 브로커 연동, 실거래 자동화, 포지션 자동
  조정을 제공하지 않는다.
- Alert와 Alert Candidate는 별개 도메인이다. Candidate는 발송 전 검토 단계이고
  기존 `alerts` 도메인을 대체하지 않는다.
- provider `real` 값은 설정 타입상 허용되지만 현재 실제 구현이 없는 provider는
  `NotImplementedError`로 실패한다. 로컬·테스트 기본값은 deterministic mock이다. 예외로
  `market`은 `yfinance`, `news`는 `rss` 실 구현이 있어 각각 일봉·원시 뉴스를 실수집한다.
- LLM은 수집 데이터를 직접 뒤지지 않는다. 백엔드가 수집·정규화·검증한 데이터를 재료로
  삼으며, Feature 계산·Context 조립을 거쳐 마지막 단계에서만 LLM 입력이 만들어진다(후속 범위).
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
- **가격 수집 원본 분리·검증·fail-closed 매핑**: 정규화 전 원본을 `raw_prices`에 아카이브해
  재처리·감사 가능성을 확보하고, 정규화 데이터는 `prices`에 upsert(멱등)한다. 검증은
  결측·미래 날짜 bar를 drop하고 통화 불일치·이상치는 경고하되 유지한다. 심볼→시장 매핑은
  화이트리스트 기반이라 미지 market은 조용히 통과시키지 않고 fail-closed로 건너뛴다.
  종목 단위 실패는 격리해 잡 전체를 중단시키지 않는다. 데이터 신뢰도 등급·자동 차단·스케줄
  주기 확정은 후속 정책이다. (`docs/designs/065-price-ingestion-pipeline.md`, PR #169)
- **뉴스 수집 회사명 쿼리·종목 태깅·fail-open locale**: 심볼로 직접 거를 수 없는 뉴스는 회사명
  (`assets.name`)을 쿼리로 삼아 종목별로 RSS를 호출하고, 반환 기사를 대상 `(symbol, market)`에
  귀속시켜 `raw_news_events`에 태깅 저장한다. market별 locale로 한국·미국을 커버하되 미지
  market은 fail-open(기본 locale + 경고)으로 수집을 계속한다 — 가격 수집의 fail-closed와
  대비된다(뉴스는 누락보다 과수집을 허용). 멀티종목 기사는 `url` unique로 first-writer-wins이며
  다중 귀속은 후속 범위다. (`docs/designs/066-news-ingestion-pipeline.md`, PR #171)
