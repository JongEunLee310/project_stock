# BE 확장: signals 목록 `?expand=asset` (G9 후속)

상태: **계약 확정(Frozen)** — 2026-06-26(Opus). `docs/api/contract-alignment.md` G9 후속.
FE Signal 뷰에서 종목 심볼 표시를 위해, watchlist G5(`?expand=asset`, BE#99/PR#106)의
검증된 패턴을 signals 목록에 그대로 이식한다. **구현은 §3 계약 확정을 정본으로 따른다.**

## 배경

`SignalResponse`는 `asset_id`만 포함하고 `symbol`이 없어 FE Signal 뷰에서 종목 심볼·시세
표시가 불가하다(FE#47 OQ-2). G9에서 Signal 모델은 BE 모델로 통일됐으나, FE 표시를 위한
심볼·시세 조인이 빠져 있다. watchlist에서 이미 쓰는 `?expand=asset` 패턴을 동일하게 적용한다.

스키마 변경(마이그레이션)·인증 변경·신규 결정 없음. 기존 패턴 재사용이므로 ADR 불요.

## 1. 변경 범위

| Method · Path | 변경 |
| --- | --- |
| `GET /api/v1/signals?asset_id=&...&expand=asset` | `expand=asset` 지정 시 각 항목에 `asset` 객체 추가. 미지정/타값이면 기존 응답 그대로(하위호환) |

`POST /api/v1/signals`, `GET /api/v1/signals/{signal_id}`는 변경 없음.

## 2. FE 매핑

FE는 `asset.symbol`로 심볼을 표시한다. `price`/`change_percent`는 문자열 Decimal(C5),
`get_market_provider()` 시세를 합친 값이다. watchlist expand와 동일 형태.

## 3. 계약 확정 (2026-06-26, Opus — 정본)

와이어 컨벤션은 기존과 동일: snake_case, 금액=Decimal **문자열**(C5), 시각=`UtcDatetime`,
공통 엔벨로프 `app/core/response.py`의 `paginated`. watchlist G5와 **응답 형태·동작 일치**.

### 3.1 엔드포인트

| Method · Path | 책임 | meta |
| --- | --- | --- |
| `GET /api/v1/signals?asset_id=&include_expired=&page=&size=&expand=` | asset 단위 시그널 목록 | 페이지 meta |

- Auth Required(`get_current_user`). 기존 쿼리(`asset_id` 필수, `include_expired` 기본 false,
  공통 `PaginationParams`) 그대로 유지.
- `expand`: 콤마 구분 문자열, 지원값 `asset`. 파싱은 watchlist 라우터와 동일하게
  `[e.strip() for e in expand.split(",")]`에 `"asset"` 포함 여부로 판정.
- 미지정/지원 외 값이면 기존 `SignalResponse` 목록(하위호환). `asset` 키 자체가 없다.

### 3.2 응답 스키마

`expand=asset` 미지정 — 기존 `SignalResponse` 배열(변경 없음).

`expand=asset` 지정 — `SignalExpandedResponse` 배열:
- 기존 `SignalResponse` 전 필드 + `asset: AssetBriefResponse | None`.
- `is_expired` 파생 계산·`evidence` JSON 파싱 등 기존 `SignalResponse` 동작 보존.
- `asset`은 `{ symbol, name, price, change_percent, sector? }`. asset 미존재 시 `null`.

`AssetBriefResponse`는 watchlist에서 이미 정의된 계약 객체를 **단일 정의로 재사용**한다
(`app/domains/watchlists/schema.py`에서 import). 중복 정의·assets로의 승격 리팩터는
불필요한 변경이므로 하지 않는다(향후 공용화는 follow-up).

### 3.3 서비스 동작

watchlist `list_items_expanded` 패턴 미러:
1. 기존 `list_signals`로 시그널 목록 조회(페이지네이션·include_expired 동일).
2. 항목들의 `asset_id` 집합으로 `AssetRepository.get_by_id` 조회.
3. 존재하는 asset symbol들로 `get_market_provider().get_quote(symbols)` 1회 호출, symbol→quote 맵.
4. 항목별로 `SignalExpandedResponse`(기존 SignalResponse 필드 + asset_brief) 구성.
   asset 미존재 시 `asset=None`, quote 미존재 시 `price`/`change_percent`는 `"0"`(watchlist와 동일).
5. `count_signals`로 total 산출(기존과 동일).

### 3.4 에러

신규 에러 코드 없음. 기존 인증/검증 에러만.

## 4. 범위 밖(후속)

- `AssetBriefResponse`의 공용 모듈(assets) 승격.
- expand 다중 필드 확장, signals 정렬/필터 확장.
- FE 어댑터 매핑은 FE 트랙(FE#47/#48 후속).
