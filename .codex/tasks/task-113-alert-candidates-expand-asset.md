# Codex Handoff Task

## Source Issue

- 설계 기록(정본): `docs/designs/047-alert-candidates-expand-asset.md`
- 이식 선례(정본 패턴): `docs/designs/signals-expand-asset.md`, `app/api/v1/endpoints/signals.py`, `app/domains/signals/service.py`, `app/domains/signals/schema.py`
- 테스트 선례: `tests/test_signals.py`(expand 케이스), `tests/test_watchlist_expand.py`

## Task Summary

`GET /api/v1/alert-candidates` 목록에 `?expand=asset`를 추가한다. signals BE#112(`?expand=asset`)에서 검증된 watchlist G5 패턴의 **기계적 이식**이다. expand=asset 지정 시 각 후보 항목에 `asset` 객체(symbol/name/price/change_percent/sector)를 합쳐 반환하고, 미지정 시 기존 응답을 그대로 유지(하위호환)한다.

## Goal

- `expand=asset` 지정 시 `AlertCandidateExpandedResponse` 배열(기존 필드 + `asset`) 반환.
- 미지정/지원 외 값이면 기존 `AlertCandidateResponse` 배열 그대로(asset 키 없음).
- `asset_id`가 없거나 asset 미존재 항목은 `asset: null`.
- 검증(pytest/ruff) 통과 + expand 신규 테스트.

## Background — 오케스트레이터가 확정한 사실 (추측 금지, 그대로 따를 것)

설계 §3은 signals 코드 확인으로 모두 확정됐다. signals 구현을 정본으로 미러한다:

1. **엔드포인트**(`app/api/v1/endpoints/alert_candidates.py` `list_alert_candidates`): signals와 동일하게 `expand: str | None = Query(default=None, description="Comma-separated expand fields. Supported: asset")` 파라미터 추가. `expand is not None and "asset" in [e.strip() for e in expand.split(",")]` 이면 `service.list_candidates_expanded(...)`(기존과 **동일한 필터·정렬·페이지네이션 인자**) 호출 → `paginated(...)`. 아니면 기존 인라인 경로 그대로. `response_model`은 signals처럼 `ApiResponse[list[Any]]`로 완화하고 반환 타입 애너테이션은 `Any`.
2. **스키마**(`app/domains/alert_candidates/schema.py`): `AlertCandidateExpandedResponse(AlertCandidateResponse)` 신설 — `asset: AssetBriefResponse | None = None` 한 필드만 추가. `AssetBriefResponse`는 `from app.domains.watchlists.schema import AssetBriefResponse`로 **재사용**(중복 정의·assets 승격 금지).
3. **서비스**(`app/domains/alert_candidates/service.py`): `list_candidates_expanded(...)` 신설 — signals `list_signals_expanded` 미러. 인자 시그니처는 `list_candidates`와 동일(user_id, candidate_type?, importance?, status?, offset, limit, sort). 동작: ①`list_candidates`로 목록 조회 ②항목 `asset_id` 집합(None 제외)으로 `AssetRepository.get_by_id` 조회해 id→asset 맵 ③존재 asset symbol들로 `get_market_provider().get_quote(symbols)` **1회** 호출(빈 목록이면 호출 생략)해 symbol→quote 맵 ④항목별 `AlertCandidateExpandedResponse`(기존 필드 + asset_brief) 구성. asset 미존재/asset_id None → `asset=None`. quote 미존재 → `price`/`change_percent`는 `"0"`. import 추가: `from app.adapters.factory import get_market_provider`, `from app.domains.assets.repository import AssetRepository`, `from app.domains.watchlists.schema import AssetBriefResponse`, schema에 `AlertCandidateExpandedResponse`. `__init__`에 `self.asset_repo = AssetRepository(db)` 추가(signals 패턴 동일).
4. **기존 필드 직렬화 보존**: 항목 dump는 signals처럼 `AlertCandidateResponse.model_validate(candidate).model_dump()` 후 `AlertCandidateExpandedResponse(**data, asset=asset_brief)`로 구성. evidence(JSON)·created_at(UtcDatetime) 등 기존 동작 보존.
5. **total**: 기존 `count_candidates`로 산출(변경 없음).

## Implementation Scope

- `app/domains/alert_candidates/schema.py` — `AlertCandidateExpandedResponse` 추가, `AssetBriefResponse` import.
- `app/domains/alert_candidates/service.py` — `list_candidates_expanded` 추가, 의존(`AssetRepository`/`get_market_provider`) 추가.
- `app/api/v1/endpoints/alert_candidates.py` — `expand` 쿼리 파라미터 + 분기, `response_model` 완화, import 추가.

## Out of Scope

- `AssetBriefResponse`의 공용 모듈(assets) 승격·중복 정의.
- expand 다중 필드, 신규 필터/정렬.
- 단건 조회·`mark_read`·`confirm`·`POST` 등 다른 엔드포인트.
- FE 레포 변경(별도 트랙). DB 마이그레이션·모델 변경.
- signals/watchlist 등 무관 파일 리팩터.

## Protected Files

`.codex/*`, `docs/designs/*`, `docs/harness/*`, `docs/decisions/*` 수정 금지(설계 문서는 이미 작성됨, 참조만).

## Requirements

- 미지정 시 기존 응답 **완전 동일**(하위호환). asset 키 자체 부재.
- `AssetBriefResponse`는 watchlist 정의 재사용(단일 정의 원칙).
- `get_market_provider().get_quote`는 페이지당 최대 1회.
- 기존 통과 테스트를 약화하지 말 것.

## Test Requirements

`tests/test_alert_candidates.py`에 expand 케이스 추가(signals `tests/test_signals.py:170~257` 패턴 미러):
- `expand` 미지정 → 항목에 `asset` 키 없음.
- `expand=asset`(asset_id 있는 후보 + asset 존재) → `asset` 객체 포함, `symbol`/`name`/`price`(str)/`change_percent`(str) 단언, `get_quote` 1회 호출 단언(RecordingMarketProvider monkeypatch — patch 대상 `app.domains.alert_candidates.service.get_market_provider`), meta total 단언.
- `expand=asset`인데 asset_id가 존재하지 않는 후보 → `asset` is None.
- (선택) asset_id=None 후보 → `asset` is None.
- 헬퍼: 기존 `create_alert_candidate_for_user(..., asset_id=)` 재사용. asset 생성은 signals 테스트의 `create_asset` 헬퍼/패턴 참고(필요 시 동일 방식으로 asset row 생성).

## Verification Commands

```
uv run ruff check .
uv run pytest tests/test_alert_candidates.py -q
uv run pytest -q
```

## Documentation Impact

- 설계 `docs/designs/047-alert-candidates-expand-asset.md` 참조(이미 Frozen).
- API spec(`docs/api/frontend-api-spec.md`)에 alert-candidates expand 항목이 있으면 1줄 갱신(선택). 없으면 생략.

## ADR Need

불요. 기존 검증된 패턴(watchlist G5 → signals G9) 이식, 신규 의존성/아키텍처 변경 없음.

## Failure Record Need

불요(국소 변경·회귀 테스트로 방지).

## Risk Level

Low. signals expand의 기계적 이식. 다종목 asset_id 혼재가 유일한 차이지만 집합 기반 배치 조회로 동일 경로 처리.

## Expected Output

- 전용 브랜치 `feat/alert-candidates-expand-asset`(최신 `main` 기준, 이미 생성)에서 구현.
- 위 3개 파일 + 테스트 변경 커밋.
- 검증 전부 통과 로그.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
