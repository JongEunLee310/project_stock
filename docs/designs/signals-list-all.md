# BE 확장: signals 목록 전체 조회 — `asset_id` 선택 파라미터화

상태: **설계 확정(Frozen)** — 2026-07-09(Sonnet). `docs/designs/signals-expand-asset.md`
계약의 전체 조회 확장건. **구현은 §3 계약 확정을 정본으로 따른다.**

## 배경

FE `SignalsPage`는 `useSignals()`를 인자 없이 호출하여 `GET /api/v1/signals?expand=asset`을
전송한다. 그러나 BE `list_signals` 엔드포인트(`app/api/v1/endpoints/signals.py:46`)는
`asset_id: int`를 기본값 없는 필수 쿼리 파라미터로 선언하고 있어 FastAPI 검증 단계에서
422 "Field required"가 반환되고 시그널 페이지가 목록을 불러오지 못한다.

기존 계약(`docs/designs/signals-expand-asset.md` §3.1)은 `asset_id` 필수를 전제로
확정된 것이므로, 이번 작업은 해당 계약을 `asset_id` 미지정 시의 전체 조회로 확장한다.
서비스(`SignalService.list_signals` / `list_signals_expanded` / `count_signals`)와
리포지토리(`SignalRepository`)에도 전체 조회 경로가 없으므로 해당 계층까지 함께 확장한다.

스키마 변경(마이그레이션)·인증 변경·신규 결정 없음. 기존 패턴 확장이므로 ADR 불요.

## 1. 변경 범위

| 레이어 | 파일 | 변경 |
| --- | --- | --- |
| Endpoint | `app/api/v1/endpoints/signals.py` | `asset_id: int` → `asset_id: int \| None = None` |
| Service | `app/domains/signals/service.py` | `list_signals` / `list_signals_expanded` / `count_signals`의 `asset_id` 선택화 |
| Repository | `app/domains/signals/repository.py` | `list_all` / `count_all` 신규 메서드 추가 |
| Tests | `tests/test_signals.py` | `test_list_signals_requires_asset_id` 제거, 전체 조회·expand 조합 케이스 추가 |

`POST /api/v1/signals`, `GET /api/v1/signals/{signal_id}`는 변경 없음.

## 2. 기존 계약과의 차이

`signals-expand-asset.md` §3.1에서 `asset_id`는 필수 쿼리 파라미터였다. 이번 확장에서
달라지는 지점만 기술한다.

| 항목 | 기존 (`signals-expand-asset.md` §3.1) | 이번 확장 |
| --- | --- | --- |
| `asset_id` 파라미터 | 필수(`int`) | 선택(`int \| None = None`) |
| 미지정 시 엔드포인트 동작 | FastAPI 422 | 전체 시그널 페이지네이션 반환 |
| 서비스 `asset_id` 타입 | `int` 고정 | `int \| None` |
| 리포지토리 WHERE 조건 | `Signal.asset_id == asset_id` 항상 적용 | `asset_id` 지정 시에만 적용 |

`expand=asset` 동작, `include_expired`, `PaginationParams`, 응답 엔벨로프(`paginated`),
인증 요구(`get_current_user`)는 `signals-expand-asset.md` §3.2–3.3과 동일하다.

## 3. 계약 확정 (2026-07-09, Sonnet — 정본)

와이어 컨벤션, 응답 형태는 `signals-expand-asset.md` §3과 동일하게 유지한다.

### 3.1 엔드포인트

| Method · Path | 책임 | meta |
| --- | --- | --- |
| `GET /api/v1/signals?asset_id=&include_expired=&page=&size=&expand=` | 시그널 목록 (`asset_id` 미지정 시 전체, 지정 시 특정 종목) | 페이지 meta |

- Auth Required(`get_current_user`). 기존과 동일.
- `asset_id: int | None = None`. 지정하면 해당 종목으로 필터링(하위호환). 미지정이면 전체 조회.
- `expand`, `include_expired`, 페이지네이션 파싱은 기존 규약 그대로.

### 3.2 서비스 시그니처 (변경 대상만 기술)

```
SignalService.list_signals(
    asset_id: int | None,
    include_expired: bool,
    offset: int,
    limit: int | None,
) -> list[Signal]
```
책임: `asset_id` 지정 시 `repo.list_by_asset` 위임, 미지정 시 `repo.list_all` 위임.

```
SignalService.list_signals_expanded(
    asset_id: int | None,
    include_expired: bool,
    offset: int,
    limit: int | None,
) -> list[SignalExpandedResponse]
```
책임: `list_signals` 호출 후 asset 조인·시세 조합. `signals-expand-asset.md` §3.3 동작 그대로.

```
SignalService.count_signals(
    asset_id: int | None,
    include_expired: bool,
) -> int
```
책임: `asset_id` 지정 시 `repo.count_by_asset` 위임, 미지정 시 `repo.count_all` 위임.

### 3.3 리포지토리 시그니처 (신규 메서드)

```
SignalRepository.list_all(
    include_expired: bool,
    offset: int,
    limit: int | None,
) -> list[Signal]
```
책임: `asset_id` 필터 없이 전체 시그널 페이지네이션 조회. 정렬은 `list_by_asset`과 동일(`created_at DESC, id DESC`).
출처: `app/domains/signals/repository.py:38-50` 정렬 규약 참조.

```
SignalRepository.count_all(
    include_expired: bool,
) -> int
```
책임: `asset_id` 필터 없이 전체 시그널 수 반환.

기존 `list_by_asset` / `count_by_asset`은 시그니처 변경 없이 유지한다(하위호환).

### 3.4 에러

신규 에러 코드 없음. 기존 인증/검증 에러만.

## 4. 범위 밖

- FE 변경 (FE는 이미 `asset_id` 없이 호출하도록 구현되어 있음)
- 시그널 정렬·필터 확장, expand 다중 필드 지원
- `AssetBriefResponse` 공용 모듈(assets) 승격
