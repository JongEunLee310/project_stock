# Codex Handoff Task

## Source Issue

신규 GH 이슈 미생성. Epic #141(로컬/클라우드 하이브리드 LLM) 하위, ADR-009 Follow-up의 "브리핑
기능 설계(Phase 2)"에 해당. 근거 설계: `docs/designs/057-portfolio-briefing.md`,
`docs/designs/058-dashboard-briefing.md`(둘 다 Claude Code 작성 스켈레톤).

## Task Summary

LLMGateway의 첫 사용자 대면 소비처로 포트폴리오·대시보드 AI 브리핑을 구현한다. 두 기능은
입력 CloudSafe projection만 다르고, 공통 출력 스키마 `BriefingResult`와 `gateway.complete_json`
경유 패턴을 공유한다. 출시는 클라우드 경로(`LLM_PROVIDER` 설정), 결과는 영속화하지 않는
on-demand 생성이다.

## Goal

작업 완료 시 다음이 참이다.

- `GET /portfolios/{portfolio_id}/briefing`이 `BriefingResult`(headline/body/risk_headline/
  risk_checks) + `generated_at`을 반환한다.
- `GET /dashboard/briefing`이 현재 사용자 기준으로 같은 형태를 반환한다.
- 두 입력 projection은 금액(수량·평가액·잔액)을 담지 않고, `symbol`·비중·공개 지표만 담으며
  `sensitivity = AGGREGATED`로 `PrivacyGate`를 통과한다.
- 원본 `Portfolio`/`Position` entity는 클라우드 경계에서 거부됨이 테스트로 확인된다(ADR-009 회귀).
- `LLM_PROVIDER=mock`(또는 `MockLLMClient`)에서 두 엔드포인트가 결정적으로 동작한다.

## Background

- **설계문서 우선**: `docs/designs/057-portfolio-briefing.md`·`058-dashboard-briefing.md`를 먼저
  읽고 그 입력/출력/서비스/API 정의를 따른다. 구현 중 달라지면 두 설계문서를 함께 갱신한다.
- **신규 인프라 없음.** `LLMGateway.complete_json(task_type, payload, schema, system_prompt)`
  (`app/adapters/llm/gateway.py`), `PrivacyGate`·`CloudSafePayload`(`app/adapters/llm/privacy.py`),
  라우팅(`app/adapters/llm/router.py`)이 모두 존재한다. `PORTFOLIO_BRIEFING`·`DASHBOARD_BRIEFING`
  라우트는 이미 등록되어 있다(launch=cloud). **router는 수정하지 않는다.**
- **기존 projection 선례**: `PortfolioConcentrationSnapshot`(privacy.py)이 `CloudSafePayload`를
  상속해 밴드만 담는 예시다. 신규 projection은 같은 패턴으로 추가하되 `symbol`·비중까지 담는다.
- **입력 재료**: 포트폴리오는 `PortfolioSummaryResponse`(`positions[].weight`, `sector_weights`,
  `risk_exposures`, `day_change_percent`, `cash_weight`)가 이미 계산해 준다. `symbol`/`sector`는
  `Position.asset_id`를 asset으로 해소해 얻는다.
- **대시보드 입력 불확실성(중요)**: 058의 `watchlist_highlights`(관심 종목 symbol·status·
  PER/PEG·일간변화)는 기존 watchlist/asset 데이터로 충족되어야 한다. 구현 전 `app/domains/
  watchlists`·`app/domains/assets`에 해당 필드 조회 경로가 있는지 확인하라. 부족하면 highlight를
  생략(집계 카운트+현금 비중만으로 projection 구성)하고 그 사실을 PR에 명시하라. 신규 도메인·
  테이블을 만들지 마라.
- **mock LLM 결정성**: 기존 뉴스 요약 테스트(`tests/`의 news 관련)와 `MockLLMClient`
  (`app/adapters/llm/mock.py`)가 `complete_json`으로 임의 스키마를 어떻게 채우는지 참조해, 두
  엔드포인트 테스트를 결정적으로 작성한다.
- **응답 envelope**: 기존 공통 응답 포맷(`app/core/response.py`)을 따른다.
- **구현 순서 권장**: 포트폴리오 브리핑(입력이 확실)을 먼저 완성하고, 공통 `BriefingResult`를
  추출한 뒤 대시보드 브리핑을 잇는다.

## Implementation Scope

- `app/adapters/llm/privacy.py` — `PortfolioBriefingSnapshot`, `DashboardBriefingSnapshot`,
  보조 타입(`PortfolioBriefingPosition`·`SectorWeightView`·`RiskExposureView`·`WatchlistHighlight`),
  빌더 `to_briefing_snapshot(...)`·`to_dashboard_snapshot(...)`. 모두 `CloudSafePayload` 상속,
  `sensitivity = AGGREGATED`.
- 공통 출력 스키마 `BriefingResult`(headline/body/risk_headline/risk_checks). 위치는 LLM 어댑터
  공통 schema 모듈 또는 적절한 공유 위치로 두되 도메인 간 순환 import를 피한다.
- `app/adapters/llm/prompts/portfolio_briefing.py`·`dashboard_briefing.py` — system prompt 상수.
- `app/domains/portfolios/briefing_service.py` — `PortfolioBriefingService.generate(portfolio_id)`.
- `app/domains/dashboard/briefing_service.py` — `DashboardBriefingService.generate(user_id)`.
- `app/domains/portfolios/schema.py`·`app/domains/dashboard/schema.py` — 각 `*BriefingResponse`.
- 라우터(기존 portfolios·dashboard 라우터 파일) — 두 GET 엔드포인트 추가.
- `app/adapters/factory.py` — `get_llm_gateway()`로 서비스 조립(seam만, 새 설정 추가 지양).
- `docs/designs/057-portfolio-briefing.md`·`058-dashboard-briefing.md` — 구현과 달라지면 갱신.
- `docs/api/frontend-api-spec.md` — 신규 엔드포인트 두 개 반영.

## Out of Scope

- 캐시(snapshot hash 키·TTL) — ADR-011(#138).
- 출력 내용 검증 강화·safe template 폴백 — ADR-010/012. `complete_json`의 스키마(형태) 검증까지만.
- 결과 영속화(DB 저장).
- future_primary=local 전환·위험도 escalation 엔진 — ADR-010(#139/#140).
- ADR-010/011/012의 Status 변경(Accepted 승격) — 별도 후속. 본 작업은 deferred 항목을 구현하지 않는다.
- FE 연동(adapter 변환·mock 제거) — FE repo 별도 이슈.
- research_summary 필드 불일치(BE `positive_factors` ↔ FE `headline`/`body`/`key_risks`) 수정.
- `app/adapters/llm/router.py` 라우팅 표 수정.

## Protected Files

변경하지 않는다:

- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/` (CI 설정)
- `docs/harness/`, `docs/decisions/`

## Requirements

- projection은 금액 필드(`market_value`·`cost_value`·`quantity`·`avg_buy_price`·`cash_balance`
  절대액)를 담지 않는다. 비중(%)·집계·공개 지표·`symbol`만 담는다.
- 모든 LLM 호출은 `LLMGateway.complete_json` 경유. 호출부가 직접 `LLMClient`를 만들거나 경계를
  우회하지 않는다.
- 두 projection은 `sensitivity = AGGREGATED`로 `PrivacyGate`를 통과한다. 원본 entity는 거부된다.
- on-demand 생성, 영속화 없음. 소유자/사용자 컨텍스트 검증은 기존 portfolios·dashboard 경로를 따른다.
- 미존재 포트폴리오는 404(`PORTFOLIO_NOT_FOUND` 등 기존 ErrorCode 재사용).
- `LLM_PROVIDER=mock`에서 외부 키 없이 결정적으로 동작.

## Test Requirements

- projection 단위: 금액 필드 부재, `symbol`·비중/지표 포함, `sensitivity == AGGREGATED`.
- 프라이버시 경계: 두 snapshot이 `PrivacyGate.guard` 통과, 원본 `Portfolio` entity 거부(ADR-009 회귀).
- 서비스: gateway를 mock으로 두고 `generate`가 `*BriefingResponse`로 매핑, 404 케이스.
- API: 두 엔드포인트 응답 형태(필드·envelope)와 인증/소유자 컨텍스트.
- 대시보드 highlight 생략 분기(데이터 부재 시)를 택한 경우 그 동작도 테스트.
- 계약 스냅샷 테스트에 신규 응답 스키마 반영.
- `uv run pytest` 전체 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/designs/057-portfolio-briefing.md`·`058-dashboard-briefing.md` — 구현과 차이 시 갱신.
- `docs/api/frontend-api-spec.md` — 신규 엔드포인트 두 개 반영.

## ADR Need

불요. ADR-007(provider abstraction)·ADR-008(routing)·ADR-009(cloud boundary)의 기존 결정을
그대로 따른다. 본 구현이 ADR-010/011/012를 `Accepted`로 확정하는 트리거가 되지만, 그 확정은
별도 작업이며 본 핸드오프 범위 밖이다.

## Failure Record Need

없음.

## Risk Level

Medium-High — 신규 사용자 대면 LLM 경로이며 **클라우드로 데이터를 보내는 프라이버시 민감
경계**다(ADR-009). ADR-009 Consequences가 "프라이버시 민감 경계의 구현은 머지 전 명시적 사람
리뷰가 필요"하다고 못박았다. projection 화이트리스트(금액 제외, AGGREGATED 분류)가 정확한지
머지 전 사람 리뷰를 받아야 한다. 동작 자체는 조회 한정으로 부수효과는 작다.

## Expected Output

- llm 어댑터(projection·프롬프트·공통 `BriefingResult`) + portfolios·dashboard 브리핑 서비스·
  스키마·엔드포인트 + 테스트.
- `uv run ruff check .` / `uv run mypy .` / `uv run pytest` 전부 통과.
- PR body에 설계 057/058과 Epic #141 참조. 프라이버시 경계 변경이므로 사람 리뷰 요청 명시.

## Rules

- Stay within scope. 캐시·검증·폴백·영속화·escalation·ADR Status 변경은 건드리지 않는다.
- Do not weaken verification. 프라이버시 경계 테스트(원본 entity 거부)를 반드시 포함한다.
- Do not modify protected files. router 라우팅 표도 수정하지 않는다.
- 가정(대시보드 highlight 데이터 가용성, `BriefingResult` 위치, ErrorCode 선택)과 검증 결과를
  PR에 보고한다.
- Stop and ask: 대시보드 highlight를 기존 데이터로 구성할 수 없고 집계만으로도 부족하다고
  판단되면, 신규 도메인을 만들지 말고 중단해 사람에게 묻는다. projection에 금액·원본 entity를
  넣어야만 동작한다면 중단한다(ADR-009 위반).
