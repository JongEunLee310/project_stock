# 060 · Watchlist AI 관찰 메모 (Watchlist Observations)

Status: Accepted
작성: Claude Code (orchestrator)
관련: BE #153, FE #86, ADR-009(CloudSafe 경계), 설계 057(포트폴리오 브리핑)·058(대시보드 브리핑)·059(watchlist highlight status)

## 1. 배경

Watchlist 화면의 "AI 관찰 메모" 패널은 특정 관심 목록의 종목들을 가로지르는 현황 관찰과
종목별 유의 사항을 보여줍니다(FE 이슈 #86). 현재 `watchlists.py` 라우터에는
`create`·`list`·`list_items`·`summary`·`add_item`·`remove_item`만 있고 관찰 메모 라우트는
없습니다.

LLM 게이트웨이 골격은 설계 057/058로 이미 구현되어 있습니다. `LLMTaskType.WATCHLIST_NOTE`는
라우팅 표에 `TaskRoute(launch="cloud", future_primary="local")`로 등록되어 있고(router.py
확인), `LLMGateway.complete_json`·`PrivacyGate`·`WatchlistHighlight`·
`active_signal_types_by_asset`·`resolve_watchlist_status`가 모두 존재합니다. 따라서 본
작업은 새 인프라가 아니라 게이트웨이의 신규 소비처를 붙이는 일이며, 대시보드 브리핑
(`DashboardBriefingService`)과 동일한 패턴을 특정 watchlist 스코프로 좁혀 재사용합니다.

## 1.1 확정 결정 (orchestrator)

핸드오프 전에 설계의 열린 항목을 아래와 같이 확정합니다.

- **A. projection 항목 타입 = 059의 `WatchlistHighlight` 재사용.** 필드
  (`symbol`·`status`·`per`·`peg`·`daily_change_percent`)가 059 계약과 동일하고 화이트리스트
  기준도 같습니다. 별도 `WatchlistObservationItem`을 신설하지 않습니다 — 관찰 메모라는 용도
  의미는 상위 snapshot 타입(`WatchlistObservationSnapshot`)이 담당하며, 동일 필드의 병렬
  타입은 유지 비용만 늘립니다.
- **B. 항목 수 상한 = 30(`OBSERVATION_ITEM_LIMIT`).** asset_id 기준 dedup 후 repository의
  priority 정렬 순서로 상위 30개까지만 projection에 담습니다. cloud 단일 호출 payload를
  bounding하기 위한 방어값입니다(ADR-009 §3.1 검토 결과).
- **C. 응답 타입 경계 = domain 독립 정의.** LLM 출력 스키마(`ObservationsResult`)는 adapter
  계층에 두고, API 응답 스키마(`WatchlistObservationsResponse`)는 domain 계층에서 독립
  정의합니다. 대시보드가 `BriefingResult`를 `DashboardBriefingResponse`로 재정의한 관례와
  동일하게, domain 응답이 adapter 출력 스키마에 의존하지 않도록 합니다.
- **D. 소유권 에러 = 기존 `_get_owned_watchlist` 관례.** watchlist 미존재 시 404
  (`WATCHLIST_NOT_FOUND`), 소유자 불일치 시 403(`WATCHLIST_FORBIDDEN`). 둘을 404로 뭉개지
  않습니다(기존 watchlist API와 일관).

## 2. 범위

포함:

- CloudSafe projection 타입 `WatchlistObservationSnapshot` + 빌더
  `to_watchlist_observation_snapshot`.
- LLM 출력 스키마 `ObservationsResult`(+ `ObservationItem`).
- `WATCHLIST_OBSERVATION_SYSTEM_PROMPT`.
- API 응답 스키마 `WatchlistObservationsResponse`(+ `WatchlistObservationItemResponse`).
- 관찰 메모 생성 서비스 `WatchlistObservationsService`(on-demand, 영속화 없음).
- 조회 API 엔드포인트 `GET /watchlists/{watchlist_id}/observations`.
- mock LLM 클라이언트에 `ObservationsResult` 기본 응답 추가.

비포함(분리):

- 캐시(ADR-011)·출력 검증 강화와 safe template(ADR-010/012)·결과 영속화.
- `future_primary = local` 전환(ADR-010 확정 후). 본 설계의 projection·출력 계약은 로컬
  경로에서 그대로 재사용됩니다.
- FE adapter 연동·화면 mock 제거 — FE repo 별도 이슈(#86).
- 대시보드 브리핑의 종목 해소 로직(`_build_watchlist_highlights`)과의 공통 helper 추출 —
  본 범위는 동일 패턴을 watchlist 스코프로 재현하는 데 그칩니다. 중복 해소 로직의 공통화는
  후속 개선 여지로 둡니다(S-note).

## 3. 입력 — CloudSafe projection

ADR-009에 따라 원본 watchlist entity는 클라우드로 보내지 않고, 화이트리스트 전용
projection만 보냅니다. 059의 `WatchlistHighlight` 계약과 동일한 화이트리스트 기준을 따릅니다.

신규 타입 `WatchlistObservationSnapshot(CloudSafePayload)`, `sensitivity = AGGREGATED`
(위치: `app/adapters/llm/privacy.py`):

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| watchlist_id | int | 대상 watchlist 식별자(공개 키 — 금액 정보 아님) |
| item_count | int | projection에 담긴 종목 수(dedup·cap 이후) |
| items | list[WatchlistHighlight] | 종목별 공개 지표·신호 상태(결정 A) |

`WatchlistHighlight`(059, privacy.py 기존): `symbol: str`, `status: str`, `per: Decimal | None`,
`peg: Decimal | None`, `daily_change_percent: Decimal`. 보유 수량·평가액 없음.

빌더 시그니처(위치: `app/adapters/llm/privacy.py`):

```
def to_watchlist_observation_snapshot(
    watchlist_id: int,
    items: Sequence[WatchlistHighlight],
) -> WatchlistObservationSnapshot
```

책임: watchlist 식별자와 해소된 종목 항목 목록을 받아 화이트리스트 필드만 담은
projection을 구성합니다. 금액 필드는 포함하지 않으며, `item_count`는 전달된 항목 수로
설정합니다. cap·dedup은 서비스가 빌더 호출 전에 적용합니다.

status·PER·PEG·일간변화 해소는 059/058에서 설계·구현한 `active_signal_types_by_asset` +
`resolve_watchlist_status` + market provider quote 경로를 재사용합니다(신규 repository
메서드 불요).

### 3.1 프라이버시 판단 (ADR-009)

- 금액(보유 수량·평가액)을 제외하므로 계좌 규모는 노출되지 않습니다.
- `symbol`은 공개 티커, `status`는 signals 도메인이 이미 계산한 활성 신호 종류입니다.
  "이 사용자가 해당 종목을 관심 목록에 두고 특정 신호 상태에 있다"는 사실 노출은 059/058에서
  정렬한 trade-off와 동일하며 금액을 더하지 않습니다.
- `per`·`peg`·`daily_change_percent`는 공개 시장 데이터입니다.
- payload 전체 등급은 `AGGREGATED`이고 `PrivacyGate.guard`를 통과합니다(코드 변경 불요).
- 항목 수 상한(결정 B, 30)으로 단일 cloud 호출 payload를 bounding합니다.

## 4. 출력 — 관찰 스키마 (LLM)

LLM 출력은 종목별 관찰 항목 리스트를 담는 전용 `ObservationsResult`로 확정합니다
(위치: `app/adapters/llm/schema.py`, `BriefingResult`와 나란히):

```
class ObservationItem(BaseModel):
    symbol: str
    note: str

class ObservationsResult(BaseModel):
    summary: str
    items: list[ObservationItem]
```

`summary`는 관심 목록 전체를 가로지르는 종합 관찰, `items`는 종목별 유의 사항입니다.

`BriefingResult`(057·058) 재사용도 검토했으나 채택하지 않았습니다. FE 관찰 메모 카드는
`{id, text}` 항목 리스트를 렌더링하는 구조라 브리핑의 `risk_checks: list[str]`에 항목을
우겨넣으면 의미가 흐려집니다. 전용 스키마가 카드 형태와 정합합니다.

## 5. 응답 스키마 (domain)

결정 C에 따라 domain 계층이 응답 스키마를 독립 정의합니다
(위치: `app/domains/watchlists/schema.py`):

```
class WatchlistObservationItemResponse(BaseModel):
    symbol: str
    note: str

class WatchlistObservationsResponse(BaseModel):
    summary: str
    items: list[WatchlistObservationItemResponse]
    generated_at: UtcDatetime
```

API 응답: `ApiResponse[WatchlistObservationsResponse]` — 공통 envelope 준수.

## 6. 서비스

신규 `app/domains/watchlists/observations_service.py`:

```
class WatchlistObservationsService:
    def __init__(self, db: Session, gateway: LLMGateway) -> None
    def generate(self, watchlist_id: int, user_id: int) -> WatchlistObservationsResponse
```

`generate` 책임(순서):

1. `_get_owned_watchlist` 관례로 소유권을 검증한다(미존재 404 `WATCHLIST_NOT_FOUND`,
   비소유 403 `WATCHLIST_FORBIDDEN`). `WatchlistService`의 기존 메서드를 재사용하거나 동일
   규칙을 따른다.
2. watchlist 항목을 조회하고 asset_id 기준 dedup 후 상위 `OBSERVATION_ITEM_LIMIT`(30)개를
   선택한다. 각 항목의 `symbol`·PER·PEG·일간변화·status를 해소해 `WatchlistHighlight`
   리스트를 만든다(대시보드 브리핑의 해소 경로와 동일 로직, watchlist 스코프).
3. `to_watchlist_observation_snapshot(watchlist_id, highlights)`으로 CloudSafe projection을
   만든다.
4. `gateway.complete_json(LLMTaskType.WATCHLIST_NOTE, snapshot, ObservationsResult,
   WATCHLIST_OBSERVATION_SYSTEM_PROMPT)`를 호출하고 `ObservationsResult.model_validate(...)`로
   구조화한다(대시보드 브리핑 패턴과 동일).
5. 결과를 `WatchlistObservationsResponse`로 매핑하고 `generated_at=utc_now()`를 붙여
   반환한다.

영속화하지 않습니다. 게이트웨이가 라우팅·프라이버시 가드를 책임집니다. 빈 watchlist는
빈 `items`로 projection을 만들어 게이트웨이에 전달합니다(정상 경로).

## 7. API

신규 라우트를 기존 `app/api/v1/endpoints/watchlists.py`에 추가합니다(신규 라우터 파일 불요):

| Method | Path | 응답 | 비고 |
| --- | --- | --- | --- |
| GET | `/watchlists/{watchlist_id}/observations` | `WatchlistObservationsResponse` | on-demand 생성, 공통 envelope |

- 인증: 기존 watchlist API와 동일하게 `get_current_user` 의존, 소유자 검증.
- 파라미터: 없음.
- 에러: 미존재 404(`WATCHLIST_NOT_FOUND`)·비소유 403(`WATCHLIST_FORBIDDEN`). LLM 실패 시
  예외 전파(safe template 폴백은 ADR-010 분리). 게이트웨이의
  `CloudBoundaryViolationError`·`LLMRoutingError`는 시스템 경계에서 처리.
- 서비스 조립: `WatchlistObservationsService(db, get_llm_gateway())`(대시보드 브리핑
  endpoint 관례와 동일).

## 8. 프롬프트

신규 `app/adapters/llm/prompts/watchlist_observation.py`:

- `WATCHLIST_OBSERVATION_SYSTEM_PROMPT: str` — 역할(관심 종목 현황 관찰 보조), 출력
  형식(`ObservationsResult` JSON), 톤(권고이며 자동매매 지시가 아님), 입력 해석 지침
  (종목별 신호 상태·PER·PEG·일간변화를 근거로 각 종목의 유의 사항과 전체 요약 제시)을
  담습니다. 기존 `dashboard_briefing.py`·`portfolio_briefing.py` 프롬프트 모듈과 동일한
  형식(system prompt 문자열 상수만 제공)을 따릅니다.

게이트웨이가 projection을 user 메시지로 직렬화하므로, 프롬프트 모듈은 system prompt
문자열만 제공합니다.

## 9. 의존성

- `app/adapters/llm/gateway.py`(`LLMGateway.complete_json`) — 그대로 사용.
- `app/adapters/llm/router.py` — `WATCHLIST_NOTE` 라우트 기등록(변경 불요).
- `app/adapters/llm/privacy.py` — `WatchlistObservationSnapshot` 신규 projection 타입·빌더
  추가. `WatchlistHighlight`·`PrivacyGate` 변경 없음(재사용).
- `app/adapters/llm/schema.py` — `ObservationItem`·`ObservationsResult` 신규 추가.
- `app/adapters/llm/mock.py` — `DEFAULT_MOCK_RESPONSES`에 `ObservationsResult` 항목 추가.
- `app/adapters/llm/__init__.py` — 신규 스키마 export(기존 관례 따름).
- `app/domains/signals/repository.py`(`active_signal_types_by_asset`)·`types.py`
  (`resolve_watchlist_status`) — 재사용.
- `app/domains/watchlists`(repository·service·model) — 조회·소유권 재사용.
- `app/domains/assets`·market provider quote — `symbol`·PER/PEG/변화율 해소에 재사용.
- `app/adapters/factory.py`(`get_llm_gateway`·`get_market_provider`) — 서비스 조립 seam.
- `app/core/schema.py`(`UtcDatetime`)·`app/core/response.py`(`ApiResponse`·`success`) — 재사용.

## 10. 테스트

- projection 단위: `to_watchlist_observation_snapshot`이 금액 필드 부재·`symbol`·`status`
  포함·`sensitivity == AGGREGATED`·`item_count` 일치를 만족함을 단언.
- 프라이버시 경계: `WatchlistObservationSnapshot`이 `PrivacyGate.guard` 통과, 원본 watchlist
  entity 거부를 단언(ADR-009 회귀 방지).
- 서비스: gateway mock 주입 시 `generate`가 `WatchlistObservationsResponse`로 매핑,
  미존재 404·비소유 403·빈 watchlist(빈 items) 처리를 단언. cap(30) 초과 시 상위 30개로
  제한됨을 단언.
- API: `GET /watchlists/{id}/observations` 응답 형태(필드·envelope)·200, 401(미인증),
  404/403 케이스.
- 계약 스냅샷: `WatchlistObservationsResponse` 스키마·OpenAPI 경로/컴포넌트를
  `tests/test_api_contract.py`에 반영.

## 11. 문서·ADR 영향

- ADR 불요: 기존 게이트웨이·`WATCHLIST_NOTE` 라우트·`PrivacyGate`·`WatchlistHighlight`
  재사용으로 신규 외부 의존성·아키텍처 경계 변경 없음. cloud 경계 원칙은 ADR-009가 이미
  커버. `future_primary = local` 전환·캐시·safe template은 각기 ADR-010/011/012로 분리.
- 실패기록 불요: 국소 신규 endpoint, 소유권/LLM 실패는 표준 예외 경로로 커버.
