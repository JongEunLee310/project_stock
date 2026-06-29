# Codex Handoff Task

## Source Issue

설계: `docs/designs/051-alert-response-signal-context.md` (Frozen)

## Task Summary

`AlertResponse`에 연결된 시그널의 진실된 맥락(`asset_id`, `symbol`, `alert_type`, `message`)을
additive로 추가합니다. 목록(`GET /alerts`)과 단건(read/dismiss) 응답 모두에 적용합니다.

## Goal

- `AlertResponse`가 기존 필드에 더해 `asset_id`, `symbol`, `alert_type`, `message`를 포함한다.
- 값은 연결된 `Signal`(및 `Asset`)에서 진실되게 파생된다.
- 기존 필드·정렬·필터·페이지네이션·dedup·상태 전이 동작은 불변(하위호환).

## Background — 오케스트레이터가 확정한 사실

- 설계 051이 정본이며 계약은 동결됨. 아래대로 구현할 것.
- 필드 출처: `asset_id` ← `signal.asset_id`, `symbol` ← `signal.asset.symbol`,
  `alert_type` ← `signal.signal_type`, `message` ← `signal.reason`.
- `title`은 BE에서 만들지 않는다(FE가 `alert_type` 라벨로 파생). 임의 텍스트·의미 분류를 합성하지 않는다.
- **시세 호출 없음**: 가격을 노출하지 않으므로 `get_market_provider`/quote를 호출하지 않는다
  (alert-candidates expand와 달리 `asset` 전체 객체·price 미포함).
- 추가 필드는 모두 기본값(`None`)을 가져 하위호환. 시그널/자산 미조회 시 해당 필드 `None`.
- enrichment은 `expand`로 게이팅하지 않고 항상 포함한다(FE가 항상 맥락을 필요로 함).

## Implementation Scope

- `app/domains/alerts/schema.py`
  - `AlertResponse`에 `asset_id: int | None = None`, `symbol: str | None = None`,
    `alert_type: str | None = None`, `message: str | None = None` 추가.
- `app/domains/alerts/service.py`
  - 응답 조립 메서드 추가: 알림 목록/단건을 받아 연결 시그널·자산 맥락을 채운 `AlertResponse`를 구성.
  - 목록은 항목들의 `signal_id` 집합으로 시그널을, 그 `asset_id` 집합으로 자산을 조회해 맵을 만든 뒤
    항목별로 합친다(설계 047 패턴: id 집합에 `get_by_id` 반복으로 충분, N+1 회피).
  - `SignalRepository`/`AssetRepository` 의존을 서비스에 추가.
- `app/api/v1/endpoints/alerts.py`
  - `list_alerts`, `mark_alert_read`, `dismiss_alert`가 위 조립 결과를 반환하도록 조정.
  - `response_model`은 기존 `ApiResponse[list[AlertResponse]]` / `ApiResponse[AlertResponse]` 유지.

## Out of Scope

- 마이그레이션, alerts 테이블/모델 변경.
- `asset` 전체 객체·price/change_percent, 시세 호출.
- `title`의 BE 합성, `expand` 파라미터 도입.
- alerts 생성·dedup·상태 전이 로직 변경.
- signals/assets 도메인의 쓰기 로직 변경.

## Protected Files

없음.

## Requirements

- 추가 필드는 하위호환(기본값 None). 기존 응답 소비자에 영향 없음.
- 시세 호출 0회. 외부 provider 의존 추가 금지.
- mypy strict 통과(테스트 함수 파라미터 포함 타입 주석 필수).

## Test Requirements

`tests/test_alerts.py`(또는 해당 파일)에 추가/갱신:
- 목록 응답에 `symbol`/`alert_type`/`message`/`asset_id`가 연결 시그널 값으로 채워짐.
- read/dismiss 단건 응답도 동일 필드를 채움.
- 서로 다른 asset의 알림이 혼재해도 각 항목이 올바른 종목 맥락을 가짐(배치 조회 정확성).
- 시세 provider를 호출하지 않음(기존 테스트가 quote mock에 의존하지 않는지 확인).

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest -q`

## Documentation Impact

- `docs/designs/051-alert-response-signal-context.md` 추가됨(정본).
- 이 핸드오프 문서 추가.

## ADR Need

불요. 기존 패턴(expand 류) 재사용, 응답 additive 확장, 신규 아키텍처 결정 없음.

## Failure Record Need

불요. 국소 변경, 회귀는 테스트로 커버.

## Risk Level

Low. additive 응답 확장, 기존 동작·외부 호출 횟수 불변.

## Expected Output

- 위 3개 파일 변경 + 테스트 추가/갱신.
- 브랜치 `feat/alert-response-signal-context`에 커밋(한국어 메시지).

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
