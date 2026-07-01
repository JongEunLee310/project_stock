# Codex Handoff Task

## Source Issue

BE #153 (watchlist AI 관찰 메모 endpoint), FE #86(watchlist AI 관찰 메모 패널). 설계:
`docs/designs/060-watchlist-observations.md`.

## Task Summary

Watchlist 화면의 "AI 관찰 메모" 패널에 실데이터를 공급하기 위해 특정 관심 목록의 종목
현황·유의 사항을 LLM으로 생성해 반환하는 `GET /watchlists/{watchlist_id}/observations`
endpoint를 추가한다. 기존 LLM 게이트웨이(057/058 구현)와 `WATCHLIST_NOTE` 라우트, 059의
`WatchlistHighlight`·`active_signal_types_by_asset` 해소 경로를 재사용하며, 대시보드 브리핑
(`DashboardBriefingService`) 패턴을 watchlist 스코프로 좁혀 재현한다. on-demand 생성이며
결과를 영속화하지 않는다.

## Goal

완료 시 다음이 참이어야 한다.

- `GET /api/v1/watchlists/{watchlist_id}/observations`가 인증 사용자 기준으로 200과 공통
  envelope(`ApiResponse[WatchlistObservationsResponse]`)로 관찰 메모를 반환한다.
- watchlist 미존재 시 404(`WATCHLIST_NOT_FOUND`), 소유자 불일치 시 403
  (`WATCHLIST_FORBIDDEN`), 미인증 시 401.
- CloudSafe projection `WatchlistObservationSnapshot`(sensitivity `AGGREGATED`)만 게이트웨이에
  전달되고 `PrivacyGate.guard`를 통과한다. 금액 필드는 포함하지 않는다.
- `gateway.complete_json(LLMTaskType.WATCHLIST_NOTE, ...)` 경유로 `ObservationsResult`를 받아
  `WatchlistObservationsResponse`로 매핑한다.
- ruff·mypy·pytest 전부 통과한다.

## Background

- 설계 확정본 `docs/designs/060-watchlist-observations.md`를 그대로 따른다. 열린 결정은 설계
  §1.1에서 이미 확정됐다:
  - **A**: projection 항목 타입은 059의 `WatchlistHighlight`를 재사용한다(신규 item 타입
    신설 금지).
  - **B**: 항목 수 상한 `OBSERVATION_ITEM_LIMIT = 30`, asset_id dedup 후 priority 순서 상위
    30개.
  - **C**: LLM 출력 스키마(`ObservationsResult`)는 adapter, API 응답 스키마
    (`WatchlistObservationsResponse`)는 domain에 각각 둔다(domain이 adapter 스키마에 의존
    금지).
  - **D**: 소유권 에러는 미존재 404 / 비소유 403으로 구분한다.
- 참조 구현(반드시 패턴 준수): `app/domains/dashboard/briefing_service.py`의
  `DashboardBriefingService`. 종목 해소(`active_signal_types_by_asset` +
  `resolve_watchlist_status` + market quote → `WatchlistHighlight`), dedup, `complete_json`
  호출, `Result.model_validate(...)` → `*Response(**result.model_dump(), generated_at=...)`
  흐름을 동일하게 따른다. 차이는 (a) user 전체가 아니라 watchlist 스코프, (b) 소유권 검증,
  (c) 출력이 `ObservationsResult`인 점이다.
- 소유권 검증은 `app/domains/watchlists/service.py`의 `_get_owned_watchlist` 규칙과 동일하게
  한다(미존재 404 `WATCHLIST_NOT_FOUND`, 비소유 403 `WATCHLIST_FORBIDDEN`).
- watchlist 항목 조회는 `WatchlistItemRepository.list_by_watchlist(watchlist_id, sort="priority")`
  를 사용한다(user 전체 조회 `list_by_user`가 아니라 watchlist 스코프).
- `WATCHLIST_NOTE` 라우트는 `app/adapters/llm/router.py`에 이미 등록되어 있다(변경 불요).
- `WATCHLIST_NOT_FOUND`·`WATCHLIST_FORBIDDEN`은 `app/core/error_codes.py`에 이미 존재한다.

## Implementation Scope

Codex가 변경할 수 있는 파일·동작:

- `app/adapters/llm/privacy.py` — `WatchlistObservationSnapshot(CloudSafePayload)` +
  `to_watchlist_observation_snapshot(watchlist_id, items)` 빌더 추가. `WatchlistHighlight`·
  `PrivacyGate`는 변경하지 않고 재사용.
- `app/adapters/llm/schema.py` — `ObservationItem`·`ObservationsResult` 추가.
- `app/adapters/llm/mock.py` — `DEFAULT_MOCK_RESPONSES`에 `"ObservationsResult"` 항목 추가
  (`summary` + `items`[{symbol, note}] 구조).
- `app/adapters/llm/__init__.py` — 신규 스키마 export(기존 export 관례 따름).
- `app/adapters/llm/prompts/watchlist_observation.py` — `WATCHLIST_OBSERVATION_SYSTEM_PROMPT`
  문자열 상수(기존 `dashboard_briefing.py` 형식과 동일).
- `app/domains/watchlists/schema.py` — `WatchlistObservationItemResponse`·
  `WatchlistObservationsResponse` 추가.
- `app/domains/watchlists/observations_service.py` — 신규 `WatchlistObservationsService`.
- `app/api/v1/endpoints/watchlists.py` — `GET /{watchlist_id}/observations` 라우트 추가.
- `tests/` — 아래 Test Requirements 참고.

## Out of Scope

- 캐시(TTL)·출력 검증 강화·safe template 폴백·결과 영속화 — 각기 ADR-010/011/012로 분리.
- `future_primary = local` 전환 — ADR-010 확정 후.
- 대시보드 브리핑 해소 로직과의 공통 helper 추출 — 동일 패턴을 재현하되 공통화는 하지 않는다
  (후속 개선 여지). `_build_watchlist_highlights`를 억지로 공유 함수로 리팩터하지 말 것.
- `WatchlistHighlight`·`PrivacyGate`·`router.py`·기존 briefing 서비스 변경.
- FE adapter·화면 mock 제거 — FE repo 별도 이슈.

## Protected Files

없음. 위 Implementation Scope 밖 파일은 변경하지 않는다. 특히 `privacy.py`의
`WatchlistHighlight`·`PrivacyGate`, `router.py`의 라우팅 표는 건드리지 않는다.

## Requirements

- `WatchlistObservationSnapshot(CloudSafePayload)`: `sensitivity: ClassVar = AGGREGATED`,
  필드 `watchlist_id: int`, `item_count: int`, `items: list[WatchlistHighlight]`.
- 빌더 `to_watchlist_observation_snapshot(watchlist_id: int, items: Sequence[WatchlistHighlight])
  -> WatchlistObservationSnapshot`. `item_count`는 전달된 항목 수. cap·dedup은 서비스가
  빌더 호출 전에 적용(빌더는 받은 목록을 그대로 담는다).
- `ObservationItem(BaseModel)`: `symbol: str`, `note: str`. `ObservationsResult(BaseModel)`:
  `summary: str`, `items: list[ObservationItem]`.
- `WatchlistObservationItemResponse(BaseModel)`: `symbol: str`, `note: str`.
  `WatchlistObservationsResponse(BaseModel)`: `summary: str`,
  `items: list[WatchlistObservationItemResponse]`, `generated_at: UtcDatetime`.
- `WatchlistObservationsService.generate(watchlist_id, user_id)`:
  1. 소유권 검증(미존재 404 `WATCHLIST_NOT_FOUND`, 비소유 403 `WATCHLIST_FORBIDDEN`).
  2. `list_by_watchlist`로 항목 조회 → asset_id dedup → priority 순 상위
     `OBSERVATION_ITEM_LIMIT`(30)개 선택 → `WatchlistHighlight` 리스트 해소
     (`active_signal_types_by_asset`·`resolve_watchlist_status`·market quote,
     대시보드 브리핑과 동일 로직).
  3. `to_watchlist_observation_snapshot(...)`으로 projection 생성.
  4. `gateway.complete_json(LLMTaskType.WATCHLIST_NOTE, snapshot, ObservationsResult,
     WATCHLIST_OBSERVATION_SYSTEM_PROMPT)` → `ObservationsResult.model_validate(...)`.
  5. `WatchlistObservationsResponse(**result.model_dump(), generated_at=utc_now())` 반환.
- 빈 watchlist는 빈 `items`로 projection을 만들어 정상 경로로 처리(예외 아님).
- 엔드포인트는 `success(...)`로 envelope을 감싸고 `WatchlistObservationsService(db,
  get_llm_gateway())`로 조립한다.

## Test Requirements

- projection 단위: 금액 필드(`quantity`·`market_value` 등) 부재, `symbol`·`status` 포함,
  `sensitivity == AGGREGATED`, `item_count`가 전달 항목 수와 일치.
- 프라이버시 경계: `WatchlistObservationSnapshot`이 `PrivacyGate.guard` 통과, 원본 watchlist
  entity(또는 CloudSafe 아닌 객체) 거부를 단언.
- 서비스: gateway를 mock으로 두고 `generate`가 `WatchlistObservationsResponse`로 매핑,
  미존재 404·비소유 403·빈 watchlist(빈 items) 처리, cap 초과 시 상위 30개 제한 단언.
- API: `GET /api/v1/watchlists/{id}/observations` 200·envelope·필드, 401(미인증), 404/403.
- 계약 스냅샷: `tests/test_api_contract.py`에 `WatchlistObservationsResponse` contract·
  OpenAPI 경로(`/api/v1/watchlists/{watchlist_id}/observations`)·컴포넌트 반영
  (기존 `MARKET_INDEX_QUOTE_CONTRACT`·`test_market_index_quote_response_contract` 형식 참고).

## Verification Commands

```
uv run ruff check .
uv run mypy app
uv run pytest
```

세 검사 모두 통과해야 한다. mypy 누락 금지.

## Documentation Impact

- `docs/designs/060-watchlist-observations.md` — 설계 확정본(이미 브랜치에 포함). 구현이
  설계와 어긋나면 구현이 아니라 보고로 처리.
- `.codex/tasks/task-125-watchlist-observations.md` — 본 핸드오프 기록.

## ADR Need

불요. 기존 게이트웨이·`WATCHLIST_NOTE` 라우트·`PrivacyGate`·`WatchlistHighlight` 재사용으로
신규 외부 의존성·아키텍처 경계 변경 없음. cloud 경계 원칙은 ADR-009가 이미 커버.

## Failure Record Need

불요. 국소 신규 endpoint, 소유권·LLM 실패는 표준 예외 경로로 커버.

## Risk Level

Low-Medium. 신규 파일 위주이나 CloudSafe 경계(ADR-009)를 다루므로 projection에 금액 필드가
새지 않도록 주의. DB·마이그레이션 없음. 기존 seam·에러 코드·envelope·해소 경로 재사용.

## Expected Output

- 위 Implementation Scope 파일 변경 + 테스트.
- 검증 3종 통과 로그.
- 설계와의 차이·가정이 있으면 보고. 특히 종목 해소 로직을 대시보드 브리핑과 어떻게
  재현했는지(공통화 없이) 명시.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files or the reused `WatchlistHighlight`/`PrivacyGate`/router.
- CloudSafe projection에 금액 필드를 넣지 말 것(ADR-009).
- Report assumptions and verification results.
