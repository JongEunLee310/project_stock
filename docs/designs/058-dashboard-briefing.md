# 058 · 대시보드 브리핑 기능 (생성·계약·projection)

Status: Draft
작성: Claude Code (orchestrator)
관련: Epic #141, ADR-007·ADR-008·ADR-009, ADR-010/011/012(Phase 2 deferred), 설계 057(포트폴리오 브리핑), FE `AiBriefing`

## 1. 배경

대시보드("AI 투자 관제실", FE 이슈 #7)의 "AI 브리핑" 카드는 시장 전체와 관심 종목을
가로지르는 관점을 보여준다. 현재 FE mock(`mockAiBriefing`)으로만 채워져 있다. 본 설계는
설계 057(포트폴리오 브리핑)과 같은 게이트웨이 경유 패턴을 따르되, 입력 projection이 다르다.

포트폴리오 브리핑과의 핵심 차이는 라우팅 귀착지다. ADR-008 §4 라우팅 표에서
`PORTFOLIO_BRIEFING`은 출시·미래 모두 cloud인 반면, `DASHBOARD_BRIEFING`은 출시 cloud,
**future_primary = local(+ cloud escalation)**이다(router.py에 기등록). 즉 대시보드 브리핑은
장기적으로 로컬 모델이 1차 처리하고 고위험 입력만 클라우드로 승격하는 첫 대상이며, 이는
ADR-010(Fallback/Escalation)의 escalation 시나리오와 직접 연결된다. 출시 시점에는 로컬이
stub뿐이라(ADR-008) 포트폴리오 브리핑과 동일하게 cloud로 동작한다.

본 설계의 결정은 057과 정렬한다.

- **입력 식별 수준**: 관심 종목 `symbol`과 지표(PER/PEG)·상태·변화율을 포함한다. 보유
  수량·평가액 등 금액은 제외한다.
- **범위**: 생성·출력 계약·입력 projection·API까지. 캐시·검증 강화·폴백은
  ADR-010/011/012(Phase 2 deferred)로 분리한다.

## 2. 범위

포함:

- 신규 CloudSafe projection 타입과 빌더(대시보드 집계 + 관심 종목 → projection).
- 공통 브리핑 출력 스키마(057과 공유, 아래 §4).
- `DASHBOARD_BRIEFING` system prompt.
- 브리핑 생성 서비스(on-demand, 영속화 없음).
- 조회 API 엔드포인트.

비포함(분리): 057 §2와 동일 — 캐시(ADR-011)·검증 강화와 safe template(ADR-010/012)·결과
영속화. 더해 대시보드 고유로, **future_primary=local 전환과 escalation 엔진(#139/#140)은
ADR-010 확정 후 별도**다. 본 설계는 출시 cloud 경로만 다룬다.

## 3. 입력 — CloudSafe projection

신규 타입 `DashboardBriefingSnapshot(CloudSafePayload)`, `sensitivity = AGGREGATED`:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| risk_alert_count | int | 위험 증가 종목 수 |
| important_news_count | int | 중요 뉴스 수 |
| review_signal_count | int | 검토 대상 시그널 수 |
| cash_weight | Decimal \| None | 현금 비중(포트폴리오 파생) |
| watchlist_highlights | list[WatchlistHighlight] | 상위 N개 관심 종목 상태 |

`WatchlistHighlight`: `symbol: str`, `status: str`, `per: Decimal | None`,
`peg: Decimal | None`, `daily_change_percent: Decimal`. (보유 수량·평가액 없음.)

**구현 현황(2026-06-30)**: 1차 구현은 `watchlist_highlights`를 빈 배열로 둔다. 기존
watchlist 도메인에 이 계약과 맞는 `status` 필드가 없어, 신규 도메인·테이블을 만들지 않는다는
범위 제약 안에서 highlight를 채울 수 없기 때문이다(핸드오프 task-057의 축소 분기). 따라서 출시
대시보드 브리핑은 집계 카운트와 현금 비중만을 근거로 생성한다. highlight 채움은 후속(§10)이다.

빌더 시그니처(위치: `app/adapters/llm/privacy.py`):

```
def to_dashboard_snapshot(
    summary: DashboardSummaryResponse,
    highlights: Sequence[WatchlistHighlight],
) -> DashboardBriefingSnapshot
```

책임: 기존 `DashboardSummaryResponse`의 집계 카운트·현금 비중과, 관심 종목의 공개 지표만
골라 projection을 구성한다.

### 3.1 프라이버시 판단 (ADR-009)

- 집계 카운트와 현금 비중은 ADR-009가 허용하는 익명 집계·파생값이다.
- 관심 종목 `symbol`·PER/PEG는 공개 시장 데이터이며, 보유 금액은 포함하지 않는다. "이
  사용자가 해당 종목을 관심 목록에 둔다"는 사실 노출은 057과 동일하게 정렬된 trade-off다.
- payload 전체 등급은 현금 비중을 포함하므로 `AGGREGATED`로 둔다. `PrivacyGate`가 이미
  통과시키며 코드 변경은 없다.
- future_primary=local 전환 시 이 projection은 로컬에서도 동일하게 쓰인다(전송이 없을 뿐
  같은 입력 계약). escalation으로 cloud 승격될 때 ADR-009 경계를 다시 통과해야 한다(ADR-010).

## 4. 출력 — 공통 브리핑 스키마

대시보드와 포트폴리오 브리핑의 출력 형태는 FE `AiBriefing`으로 동일하다. 따라서 출력 결과
스키마를 **공통 `BriefingResult(BaseModel)`** 로 통일한다(설계 057의 `PortfolioBriefingResult`를
이 공통 타입으로 대체).

`BriefingResult`: `headline: str`, `body: str`, `risk_headline: str | None`,
`risk_checks: list[str]`. 위치: `app/adapters/llm/` 또는 공통 schema 모듈(핸드오프 시 확정).

API 응답 스키마 `DashboardBriefingResponse(BaseModel)`: `BriefingResult` 4필드 +
`generated_at: UtcDatetime`. (포트폴리오의 `PortfolioBriefingResponse`와 형태 동일, 별도
응답 타입으로 둔다 — 화면 라우트가 다르고 계약 스냅샷을 분리 관리하기 위함.)

## 5. 서비스

신규 `app/domains/dashboard/briefing_service.py`:

```
class DashboardBriefingService:
    def __init__(self, db: Session, gateway: LLMGateway) -> None
    def generate(self, user_id: int) -> DashboardBriefingResponse
```

`generate` 책임(순서):

1. `DashboardService`로 사용자 집계 요약을 계산한다.
2. 관심 종목 상위 N개의 `symbol`·상태·PER/PEG·일간변화를 해소한다(watchlist/asset 조회).
3. `to_dashboard_snapshot(...)`으로 CloudSafe projection을 만든다.
4. `gateway.complete_json(LLMTaskType.DASHBOARD_BRIEFING, snapshot, BriefingResult,
   DASHBOARD_BRIEFING_SYSTEM_PROMPT)`를 호출한다.
5. 결과를 `DashboardBriefingResponse`로 매핑해 반환한다(`generated_at`은 호출 시각).

포트폴리오 브리핑과 달리 `portfolio_id`가 아니라 `user_id`로 동작한다(대시보드는 사용자
단위 집계). 영속화하지 않는다.

## 6. API

| Method | Path | 응답 | 비고 |
| --- | --- | --- | --- |
| GET | `/dashboard/briefing` | `DashboardBriefingResponse` | 현재 사용자 기준 on-demand 생성 |

- 인증: 기존 `/dashboard/summary`와 동일한 사용자 컨텍스트를 따른다.
- 에러: 포트폴리오·관심 종목이 비어 충분한 입력이 없을 때의 처리(빈 브리핑 vs 안내 메시지)는
  프롬프트·서비스에서 정하되, LLM 실패의 safe template 폴백은 ADR-010 분리.

## 7. 프롬프트

신규 `app/adapters/llm/prompts/dashboard_briefing.py`:

- `DASHBOARD_BRIEFING_SYSTEM_PROMPT: str` — 역할(시장·관심 종목 관점의 의사결정 보조), 출력
  형식(`BriefingResult` JSON), 톤(권고이며 자동매매 지시가 아님), 입력 해석 지침(집계
  카운트·현금 비중·관심 종목 지표를 근거로 오늘의 점검 항목 제시)을 담는다.

## 8. 의존성

- `app/adapters/llm`(gateway·privacy·router) — projection 타입·프롬프트 추가, 라우트 기등록.
- `app/domains/dashboard`(`DashboardService.get_summary`) — 재사용.
- 관심 종목 조회(watchlist/asset) — 상위 N개 highlight 해소에 사용.
- `app/adapters/factory.py`(`get_llm_gateway`) — 서비스 조립 seam.

## 9. 테스트

- projection 단위: 금액 필드 부재, `symbol`·지표 포함, `sensitivity == AGGREGATED`.
- 프라이버시 경계: `DashboardBriefingSnapshot`이 `PrivacyGate.guard` 통과, 원본 entity 거부.
- 서비스: gateway mock으로 `generate`가 `DashboardBriefingResponse`로 매핑하는지, 관심 종목·
  포트폴리오가 빈 경우 동작.
- API: `GET /dashboard/briefing` 응답 형태·인증 컨텍스트.
- 계약 스냅샷: 신규 응답 스키마를 계약 테스트에 반영.

## 10. 비범위 / 후속

- `watchlist_highlights` 채움 — 1차 구현에서 생략했다(위 §3 구현 현황). 관심 종목을 브리핑이
  구체적으로 언급하려면 watchlist 도메인에 표시용 `status`(또는 동급 상태) 계약을 추가하는
  선행 작업이 필요하다. 그 계약이 생기면 `to_dashboard_snapshot`에 highlight를 채운다.
- future_primary=local 전환과 위험도 escalation(#139/#140) — ADR-010 확정 후. 본 설계의
  projection·출력 계약은 그때 로컬 경로에서 그대로 재사용된다.
- 캐시(ADR-011, #138)·검증 강화·safe template(ADR-010/012)·영속화 — 057과 공통. 포트폴리오·
  대시보드 두 소비처가 살아나는 것이 ADR-010/011/012를 `Accepted`로 확정하는 트리거다.
- FE 연동: FE adapter가 `DashboardBriefingResponse` → `AiBriefing` 변환, `DashboardPage`의
  mock 제거(FE repo 별도 이슈).
