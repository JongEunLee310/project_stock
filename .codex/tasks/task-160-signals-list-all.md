# Codex Handoff Task

## Source Issue

#241 — signals 목록 전체 조회 지원: `asset_id` 선택 파라미터화 (FE 시그널 페이지 422 해소)

## Task Summary

`GET /api/v1/signals`의 `asset_id`를 필수에서 선택으로 완화하고, 미지정 시 전체 시그널을
페이지네이션으로 반환한다. 서비스·리포지토리 계층에 전체 조회 경로를 추가한다.

## Goal

- `GET /api/v1/signals`(`asset_id` 미지정)가 422 대신 전체 시그널 목록을 200으로 반환한다.
- `GET /api/v1/signals?expand=asset`(`asset_id` 미지정)이 각 항목에 `asset` 객체를 포함하여 반환한다.
- `GET /api/v1/signals?asset_id={id}` 기존 동작이 하위호환으로 유지된다.

## Background

FE `SignalsPage`는 `useSignals()`를 인자 없이 호출하여 `GET /api/v1/signals?expand=asset`을
전송한다. BE `list_signals`(`app/api/v1/endpoints/signals.py:46`)는 `asset_id: int`가
기본값 없는 필수 파라미터여서 FastAPI 검증 단계에서 422가 반환된다.

설계 문서: `docs/designs/signals-list-all.md` — 이 문서를 구현의 정본으로 따른다.

기존 계약: `docs/designs/signals-expand-asset.md` — `asset_id` 필수를 전제로 확정된 계약.
이번 작업은 해당 계약의 전체 조회 확장이며, §3.2–3.3 `expand=asset` 동작·응답 형태는 그대로 유지한다.

watchlist `list_items_expanded` 패턴(`app/domains/watchlists/service.py`)이 레퍼런스 구현이다.

## Implementation Scope

Codex가 변경해도 되는 파일:

- `app/api/v1/endpoints/signals.py` — `asset_id: int | None = None`으로 완화
- `app/domains/signals/service.py` — `list_signals` / `list_signals_expanded` / `count_signals`의 `asset_id` 타입을 `int | None`으로 선택화
- `app/domains/signals/repository.py` — `list_all(include_expired, offset, limit)` / `count_all(include_expired)` 신규 메서드 추가
- `tests/test_signals.py` — 기존 테스트 수정 및 신규 케이스 추가

## Out of Scope

- FE 변경 (FE는 이미 `asset_id` 없이 호출하도록 구현되어 있음)
- 시그널 정렬·필터 확장, `expand` 다중 필드 지원
- `AssetBriefResponse` 공용 모듈(assets) 승격
- `POST /api/v1/signals`, `GET /api/v1/signals/{signal_id}` 변경

## Protected Files

변경할 보호 파일 없음. `app/core/`, `app/db/`, `alembic/`, `docs/harness/` 등 하니스 파일은 변경하지 않는다.

## Requirements

1. `GET /api/v1/signals`(`asset_id` 미지정)는 전체 시그널을 `PaginationParams` 규약에 따라 페이지네이션으로 반환한다.
2. `GET /api/v1/signals?expand=asset`(`asset_id` 미지정)은 각 항목에 `asset: AssetBriefResponse | null` 객체를 포함하여 반환한다. `signals-expand-asset.md` §3.2–3.3 동작과 동일하다.
3. `GET /api/v1/signals?asset_id={id}` 기존 동작(특정 종목 필터링)은 하위호환으로 유지된다.
4. `include_expired`, `page`, `size` 파라미터는 기존 규약 그대로 동작한다.
5. `SignalRepository.list_all` / `count_all`의 정렬 규약은 `list_by_asset`과 동일하게 `created_at DESC, id DESC`를 유지한다(출처: `app/domains/signals/repository.py:46`).
6. 기존 `list_by_asset` / `count_by_asset` 시그니처는 변경하지 않는다.
7. 스키마 마이그레이션 없음. 인증 변경 없음.

## Test Requirements

다음 케이스를 `tests/test_signals.py`에 추가 또는 수정한다.

- **삭제**: `test_list_signals_requires_asset_id` — `asset_id` 미지정 시 200을 반환하므로 422를 기대하는 이 테스트는 제거한다(`tests/test_signals.py:287-291`).
- **신규**: `test_list_signals_without_asset_id_returns_all` — `asset_id` 미지정 시 여러 종목의 시그널이 모두 반환되는지 확인.
- **신규**: `test_list_signals_without_asset_id_expand_asset_includes_asset_object` — `asset_id` 미지정 + `expand=asset` 조합 시 각 항목에 `asset` 객체가 포함되는지 확인.
- **신규**: `test_list_signals_without_asset_id_respects_include_expired` — `asset_id` 미지정 + `include_expired=true` 조합 시 만료 시그널 포함 여부 확인.
- **유지**: `asset_id` 지정 시 기존 동작 테스트(`test_list_signals_excludes_expired_by_default` 등) — 수정 없이 하위호환 보증.

픽스처 규율: 테스트에 사용하는 `signal_type` 값은 `SignalType` enum에서 `.value`로 가져오고 문자열 리터럴 직접 입력을 피한다(출처: `tests/test_signals.py:33`의 `SignalType.RISK_ALERT.value` 패턴).

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

세 명령 모두 오류 없이 통과해야 한다. `pytest`는 기존 테스트의 하위호환 보증을 포함한다.

## Documentation Impact

- `docs/designs/signals-list-all.md` — 이미 작성됨. 구현 후 상태 라벨 변경 불필요(구현 완료 시 PR에서 함께 전달).
- `docs/designs/signals-expand-asset.md` — 변경 불필요. 이번 작업은 해당 계약의 확장이며, 기존 문서는 원본 계약의 정본으로 유지한다.
- 그 외 문서 변경 없음.

## ADR Need

불필요. 기존 패턴(`signals-expand-asset.md`, watchlist G5) 확장이며 신규 아키텍처 결정이 없다.

## Failure Record Need

불필요. 이번 변경은 신규 버그 수정이 아니라 FE 계약 정렬 확장이다.

## Risk Level

낮음(Low). 스키마·인증 변경 없음. 기존 `list_by_asset` / `count_by_asset`을 그대로 두고
신규 메서드를 추가하는 방식이므로 하위호환 위험이 최소화된다. 단, 기존 테스트
`test_list_signals_requires_asset_id`가 삭제 대상이므로 해당 케이스 삭제 후 동등한 전체
조회 테스트가 반드시 추가되어야 한다.

## Expected Output

- 변경 파일 4개(`signals.py`, `service.py`, `repository.py`, `test_signals.py`)
- `uv run ruff check .` / `uv run mypy .` / `uv run pytest` 모두 통과
- PR 설명에 `#241` close 링크 포함

## Rules

- 현재 브랜치(`feat/241-signals-list-all`)를 유지한다. 새 브랜치를 만들지 않는다.
- 구현 범위 안에 있는 파일만 변경한다. drive-by 리팩터링·이름 변경·파일 분리 금지.
- `docs/harness/` 등 하니스 파일과 보호 파일은 변경하지 않는다.
- 가정이 생기면 구현 노트에 기록하고 계속 진행한다(Deviations Log 규율).
- 검증을 약화시키지 않는다. 기존 passing 테스트를 무작위로 삭제하거나 skip 처리하지 않는다.
- 완료 보고 전에 세 가지 검증 명령을 실행하고 결과를 첨부한다.
