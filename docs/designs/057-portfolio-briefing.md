# 057 · 포트폴리오 브리핑 기능 (생성·계약·projection)

Status: Draft
작성: Claude Code (orchestrator)
관련: Epic #141, ADR-007(Provider Abstraction)·ADR-008(Task Routing)·ADR-009(Cloud Data Boundary), ADR-010/011/012(Phase 2 deferred), FE `AiBriefing`(`project_stock_FE` `src/shared/model/domain.ts`)

## 1. 배경

포트폴리오 화면은 보유 자산의 비중·섹터 노출·집중도·리스크를 한눈에 보여주는 운영
화면이다(FE 이슈 #14). 그 화면의 "포트폴리오 AI 브리핑" 패널은 현재 FE mock
(`mockPortfolio.aiBriefing`)으로만 채워져 있고, 코드 주석이 "BE 출처가 없어 후속 API까지
mock을 유지한다"고 명시한다. 계약 정렬 문서도 포트폴리오 행에 "briefing은 BE 부재"로
기록해 두었다.

LLM 게이트웨이 골격은 Phase 1(#133–#136)에서 이미 갖춰졌다. `LLMGateway.complete_json`은
호출부로부터 `task_type`·CloudSafe payload·출력 스키마·system prompt를 받아 라우팅과
프라이버시 경계를 거쳐 모델을 호출한다. `PORTFOLIO_BRIEFING` task type은 라우팅 표에 이미
등록되어 있다(launch=cloud, future_primary=cloud — ADR-008 §4). 즉 본 작업은 새 인프라가
아니라, 이 게이트웨이의 첫 사용자 대면 소비처를 붙이는 일이다.

본 설계의 결정 두 가지는 사용자와 정렬했다.

- **입력 식별 수준**: CloudSafe projection에 개별 종목 `symbol`과 비중(`weight`)까지
  포함한다. 수량·평가액 등 금액은 제외한다.
- **범위**: 생성·출력 계약·입력 projection·API까지. 캐시·출력 검증 강화·폴백은
  ADR-010/011/012(Phase 2 deferred)로 분리한다.

## 2. 범위

포함:

- 신규 CloudSafe projection 타입과 빌더(포트폴리오 집계 → projection 변환).
- 포트폴리오 브리핑 출력 스키마(FE `AiBriefing`에 대응).
- `PORTFOLIO_BRIEFING` system prompt.
- 브리핑 생성 서비스(on-demand 생성, 영속화 없음).
- 조회 API 엔드포인트.

비포함(분리):

- 캐시(snapshot hash 키·TTL) — ADR-011, 이슈 #138.
- 출력 내용 검증 강화·safe template 폴백 — ADR-010/012. 본 설계는 `complete_json`의
  스키마(형태) 검증까지만 의존한다.
- 결과 영속화 — 본 설계는 stateless 생성이다. 저장이 필요해지면 별도 설계.
- 대시보드 브리핑 — 후속(같은 패턴, 입력 projection만 상이).
- FE adapter 연동·화면 교체 — FE repo 별도 작업.

## 3. 입력 — CloudSafe projection

ADR-009에 따라 원본 entity(`Portfolio`/`Position`)는 클라우드로 보내지 않고, 화이트리스트로
구성한 전용 projection만 보낸다. 기존 `PortfolioConcentrationSnapshot`(밴드만, 종목 비식별)
보다 풍부한 신규 projection을 추가한다.

신규 타입 `PortfolioBriefingSnapshot(CloudSafePayload)`, `sensitivity = AGGREGATED`:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| positions | list[PortfolioBriefingPosition] | 종목별 비중·섹터·일간변화 (금액 없음) |
| sector_weights | list[SectorWeightView] | 섹터별 비중 |
| largest_position_weight | Decimal | 최대 종목 비중 |
| is_concentrated | bool | 집중도 임계 초과 여부 |
| concentration_threshold | Decimal | 집중도 임계값 |
| cash_weight | Decimal | 현금 비중 |
| day_change_percent | Decimal | 포트폴리오 전체 일간 변화율 |
| risk_exposures | list[RiskExposureView] | 리스크 노출(코드·라벨·등급·설명) |

`PortfolioBriefingPosition`: `symbol: str`, `sector: str`, `weight: Decimal`,
`daily_change_percent: Decimal`. (수량·평균단가·평가액·원가 제외.)

`SectorWeightView`: `sector: str`, `weight: Decimal`.

`RiskExposureView`: `code: str`, `label: str`, `level: str`, `description: str`.

빌더 시그니처(위치: `app/adapters/llm/privacy.py` — 기존 projection과 같은 경계 모듈):

```
def to_briefing_snapshot(
    summary: PortfolioSummaryResponse,
    symbol_by_asset_id: Mapping[int, str],
    sector_by_asset_id: Mapping[int, str],
    daily_change_by_asset_id: Mapping[int, Decimal],
) -> PortfolioBriefingSnapshot
```

책임: 이미 계산된 `PortfolioSummaryResponse`의 집계값(`positions[].weight`,
`sector_weights`, `risk_exposures`, `day_change_percent`, `cash_weight`)에서 화이트리스트
필드만 골라 projection을 구성한다. 금액 필드(`market_value`·`cost_value`·`quantity`·
`avg_buy_price`)는 옮기지 않는다.

### 3.1 프라이버시 판단 (ADR-009)

`symbol` + 비중을 `AGGREGATED`로 분류하는 근거를 명시한다.

- 금액(수량·잔액·평가액)을 제외하므로 포지션 규모와 계좌 자산은 노출되지 않는다.
  비중(%)은 ADR-009가 명시적으로 허용한 파생값이다.
- `symbol`은 공개 티커이며 사용자 신원이 아니다. 다만 "이 사용자가 해당 종목을 보유한다"는
  사실은 노출된다. 이는 사용자와 정렬해 수용한 trade-off이며, 브리핑이 종목을 구체적으로
  언급하는 사용자 가치를 위해 받아들인다.
- 소규모 포트폴리오의 재식별 위험(ADR-009 Consequences)은 금액 부재로 완화되나 완전히
  사라지지는 않는다. projection은 화이트리스트 필드만 담으므로 fail-closed를 유지한다.
- `PrivacyGate`는 `AGGREGATED`를 클라우드 허용 등급으로 이미 통과시킨다(코드 변경 불요).

## 4. 출력 — 브리핑 스키마

FE `AiBriefing`(`headline`/`body`/`riskHeadline?`/`riskChecks?`)에 대응하는 Pydantic 스키마를
출력 계약으로 둔다.

`complete_json`에 넘기는 결과 스키마 `PortfolioBriefingResult(BaseModel)`:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| headline | str | 한 줄 제목 |
| body | str | 서술 문단 |
| risk_headline | str \| None | 리스크 섹션 제목 |
| risk_checks | list[str] | 신규 매수 전 점검 권고 목록 |

API 응답 스키마 `PortfolioBriefingResponse(BaseModel)`: 위 4필드 + `generated_at: UtcDatetime`
(FE `AiBriefing`에는 없으나 research 브리핑의 `createdAt` 선례와 일관되게 둔다). 와이어는
snake_case이며 FE adapter가 camelCase `AiBriefing`으로 변환한다(FE 별도 작업).

## 5. 서비스

신규 `app/domains/portfolios/briefing_service.py`:

```
class PortfolioBriefingService:
    def __init__(self, db: Session, gateway: LLMGateway) -> None
    def generate(self, portfolio_id: int) -> PortfolioBriefingResponse
```

`generate` 책임(순서):

1. 포트폴리오 요약 집계를 계산한다(기존 `PortfolioService`의 summary 산출 재사용).
   존재하지 않으면 `AppException`(`PORTFOLIO_NOT_FOUND`).
2. 포지션의 `asset_id`를 `symbol`·`sector`·일간변화로 해소한다(asset repository 조회).
3. `to_briefing_snapshot(...)`으로 CloudSafe projection을 만든다.
4. `gateway.complete_json(LLMTaskType.PORTFOLIO_BRIEFING, snapshot, PortfolioBriefingResult,
   PORTFOLIO_BRIEFING_SYSTEM_PROMPT)`를 호출한다.
5. 결과를 `PortfolioBriefingResponse`로 매핑해 반환한다(`generated_at`은 호출 시각).

영속화하지 않는다. 게이트웨이가 라우팅·프라이버시 가드를 책임지므로 서비스는 경계를 직접
다루지 않는다.

## 6. API

| Method | Path | 응답 | 비고 |
| --- | --- | --- | --- |
| GET | `/portfolios/{portfolio_id}/briefing` | `PortfolioBriefingResponse` | on-demand 생성, 공통 envelope |

- 인증: 기존 포트폴리오 API와 동일한 소유자 검증을 따른다.
- 에러: 미존재 시 404(`PORTFOLIO_NOT_FOUND`). LLM 실패 시 본 단계에서는 예외 전파
  (safe template 폴백은 ADR-010 분리). 게이트웨이의 `CloudBoundaryViolationError`·
  `LLMRoutingError`는 시스템 경계에서 처리.

## 7. 프롬프트

신규 `app/adapters/llm/prompts/portfolio_briefing.py`:

- `PORTFOLIO_BRIEFING_SYSTEM_PROMPT: str` — 역할(투자 의사결정 보조), 출력 형식
  (`PortfolioBriefingResult` JSON), 톤(권고이지 자동매매 지시가 아님), 입력 해석 지침
  (비중·집중도·섹터·리스크 노출을 근거로 신규 매수 전 점검 항목 제시)을 담는다.

게이트웨이가 projection을 user 메시지로 직렬화하므로, 프롬프트 모듈은 system prompt 문자열만
제공한다(기존 `news_summary`의 메시지 빌더 패턴과 달리 메시지 조립은 게이트웨이가 한다).

## 8. 의존성

- `app/adapters/llm/gateway.py`(`LLMGateway.complete_json`) — 그대로 사용.
- `app/adapters/llm/privacy.py`(`CloudSafePayload`·`PrivacyGate`) — projection 타입 추가.
- `app/adapters/llm/router.py` — `PORTFOLIO_BRIEFING` 라우트 기등록(변경 불요).
- `app/domains/portfolios`(summary 집계·asset 조회) — 재사용.
- `app/adapters/factory.py`(`get_llm_gateway`) — 서비스 조립 seam.

## 9. 테스트

- projection 단위: 금액 필드(`market_value`·`quantity` 등) 부재, `symbol`·`weight` 포함,
  `sensitivity == AGGREGATED` 단언.
- 프라이버시 경계: `PortfolioBriefingSnapshot`이 `PrivacyGate.guard`를 통과하고, 원본
  `Portfolio` entity는 거부됨을 단언(ADR-009 회귀 방지).
- 서비스: gateway를 mock(또는 `MockLLMClient` 경유)으로 두고 `generate`가 결과를
  `PortfolioBriefingResponse`로 매핑하는지, 미존재 포트폴리오 404를 단언.
- API: `GET /portfolios/{id}/briefing` 응답 형태(필드·envelope)와 404 케이스.
- 계약 스냅샷: 신규 응답 스키마를 `tests/test_api_contract.py` 계열에 반영.

## 10. 비범위 / 후속

- 대시보드 브리핑 — 동일 패턴, 입력 projection만 `DashboardSummary` 기반으로 상이.
- 캐시(ADR-011, #138)·출력 검증 강화와 safe template(ADR-010/012)·결과 영속화 — 본 기능이
  살아있는 소비처가 되므로, 이 설계가 곧 ADR-010/011/012를 `Accepted`로 확정하는 트리거다.
- FE 연동: FE adapter가 `PortfolioBriefingResponse` → `AiBriefing` 변환, `PortfolioPage`의
  mock 제거(FE repo 별도 이슈).
- research 브리핑 필드 불일치(BE `positive_factors`/`negative_factors` ↔ FE `headline`/
  `body`/`key_risks`)는 본 설계와 무관한 기존 계약 정렬 이슈로 별도 추적.
