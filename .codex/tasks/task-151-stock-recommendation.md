# Codex Handoff Task

## Source Issue

https://github.com/JongEunLee310/project_stock/issues/222

## Task Summary

`GET /api/v1/watchlists/{watchlist_id}/recommendations` 엔드포인트를 신설한다. 등록 종목 중 해당 watchlist에 없는 종목을 후보로 구성하고, 기존 LLM 게이트웨이로 추천 목록과 근거를 생성한다.

## Goal

- 인증된 소유자가 자신의 watchlist에 대해 추천을 조회할 수 있다.
- `LLM_PROVIDER=mock`에서 결정적 추천 응답이 반환된다.
- LLM이 후보에 없는 심볼을 반환하면 서비스가 걸러낸다.

## Background

설계 문서 `docs/designs/222-stock-recommendation.md`를 따른다. 구조·타입·시그니처·처리 순서는 설계 문서가 우선이며, 이 핸드오프는 설계의 가정(Assumption)에 대한 결정과 수용 기준을 확정한다.

설계 가정에 대한 결정:

- 가정 A: `reference_metrics`는 `list[str]` 자유 텍스트로 확정 (MVP).
- 가정 B: `RECOMMENDATION_CANDIDATE_LIMIT = 20`으로 확정.
- 가정 C: `TaskRoute(launch="cloud", future_primary="local")`로 확정 — `WATCHLIST_NOTE`와 동일.
- 가정 D: mock 응답과 테스트 픽스처의 심볼은 하드코딩 `"AAPL"`을 그대로 쓰지 말고, 구현 시 테스트에서 실제로 등록하는 active 종목 심볼과 일치시킨다 (Real-Contract Fixtures 규율). mock 응답 심볼이 테스트 후보 집합에 포함되도록 픽스처를 구성한다.
- 가정 E: 추천 수 상한은 서비스에서 상수 `RECOMMENDATION_MAX_ITEMS = 5`로 cap한다 (프롬프트에도 5개 이하를 지시하되, 스키마 강제는 하지 않는다).
- 열린 질문 2(후보 정렬): MVP는 `list_all` 결과 순서(id 순)를 그대로 자른다. 시그널 우선 정렬은 후속.
- 열린 질문 5(에스컬레이션): 적용하지 않는다 — 기존 단순 cloud 라우팅과 동일.

## Implementation Scope

설계 문서 §2 "포함" 목록의 파일들:

- `app/adapters/llm/types.py`, `router.py` — `LLMTaskType.STOCK_RECOMMENDATION` 등록
- `app/adapters/llm/privacy.py` — `StockRecommendationCandidate`, `StockRecommendationSnapshot`, `to_stock_recommendation_snapshot`
- `app/adapters/llm/schema.py` — `RecommendationItem`, `StockRecommendationResult`
- `app/adapters/llm/prompts/stock_recommendation.py` — 시스템 프롬프트 상수
- `app/adapters/llm/mock.py` — `DEFAULT_MOCK_RESPONSES` 항목 추가
- `app/domains/watchlists/schema.py` — `StockRecommendationProjection`, `WatchlistRecommendationsResponse`
- `app/domains/watchlists/recommendations_service.py` — `WatchlistRecommendationsService` (신규 파일)
- `app/api/v1/endpoints/watchlists.py` — GET recommendations 라우트 추가
- 테스트 파일 (아래 Test Requirements)

## Out of Scope

- 추천 결과 영속화, DB 테이블 추가 (설계 §11: 신규 테이블 없음).
- 캐시·예산 어댑터 변경 (게이트웨이가 자동 적용).
- 후보 선정 고도화(정렬·외부 스크리너), 에스컬레이션 정책.
- FE 화면.
- 기존 observations·이외 도메인 로직 변경.

## Protected Files

없음. 보호 파일을 수정하지 않는다.

## Requirements

- 설계 문서 §8의 `generate` 처리 순서 10단계를 따른다.
- 소유권 검증은 기존 watchlists 서비스의 `_get_owned_watchlist` 관례와 동일한 에러 계약(404 `WATCHLIST_NOT_FOUND`, 403 `WATCHLIST_FORBIDDEN`)을 쓴다 — 구현 전 실제 에러 코드 리터럴을 `watchlists/service.py`에서 확인해 일치시킨다.
- 설계 문서에 인용된 행 번호·메서드명(`gateway.py` 행 105·123, `mock.py:67`, `AssetRepository.list_all`, `active_signal_types_by_asset` 등)은 가정이므로 구현 전 실제 코드에서 확인하고, 다르면 실제 계약을 따르고 보고한다.
- 후보가 없으면(모든 active 종목이 이미 포함) LLM을 호출하지 않고 빈 `recommendations`를 반환한다.

## Test Requirements

- 서비스 테스트: mock provider로 결정적 추천 반환, 후보 제외 로직(watchlist 포함 종목 제외), LLM 반환 심볼 교차 검증(후보 외 심볼 필터링), 빈 후보 시 빈 응답 + LLM 미호출.
- 라우트 테스트: 정상 200, 미존재 404, 비소유 403 (기존 watchlists 라우트 테스트 패턴).
- 픽스처는 실계약 기반: 테스트에서 등록한 실제 종목 심볼과 mock 응답 심볼이 일치해야 한다.
- 기존 테스트를 약화하거나 삭제하지 않는다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

설계 문서 `docs/designs/222-stock-recommendation.md`의 Status를 구현 완료 시 실제 결정 반영과 함께 유지한다(가정 표의 확정 값이 본문과 어긋나면 표를 갱신). README 갱신은 불요.

## ADR Need

불필요. 기존 LLM 게이트웨이·CloudSafe projection 패턴(ADR-009)의 적용이며 새 아키텍처 결정이 없다.

## Failure Record Need

불필요. 반복 실패 이력이 없다.

## Risk Level

Medium — 신규 엔드포인트와 LLM 태스크 등록이 여러 어댑터 파일에 걸치지만, 모두 기존 패턴의 반복이고 기존 경로 변경은 없다.

## Expected Output

- 변경 파일 목록 보고
- 검증 3종 실행 결과 보고
- 설계 인용(행 번호·메서드명)과 실제 코드가 달랐던 항목 보고
- 가정·잔여 위험 보고

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치(feat/222-stock-recommendation)에서 그대로 작업한다. 새 브랜치를 만들지 않는다.
