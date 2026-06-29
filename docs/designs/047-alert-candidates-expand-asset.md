# BE 확장: alert_candidates 목록 `?expand=asset`

상태: **계약 확정(Frozen)** — 2026-06-29(Opus). FE Dashboard Priority Queue 페어.
FE Dashboard "우선 확인 큐"에서 각 항목을 research 화면으로 딥링크하려면 종목 심볼이 필요하다.
`signals-expand-asset`(BE#112)에서 검증된 watchlist G5 패턴을 alert_candidates 목록에 그대로 이식한다.
**구현은 §3 계약 확정을 정본으로 따른다.**

## 배경

`AlertCandidateResponse`는 `asset_id`만 포함하고 `symbol`이 없어 FE Dashboard Priority Queue에서
각 후보 항목을 research 화면(종목별 딥링크)으로 연결할 수 없다. signals가 BE#112에서 watchlist G5
패턴(`?expand=asset`)으로 해결한 것과 갭·해법이 완전히 동일하다.

스키마 변경(마이그레이션)·인증 변경·신규 결정 없음. 기존 패턴 재사용이므로 ADR 불요.

## 1. 변경 범위

| Method · Path | 변경 |
| --- | --- |
| `GET /api/v1/alert-candidates?...&expand=asset` | `expand=asset` 지정 시 각 항목에 `asset` 객체 추가. 미지정/타값이면 기존 응답 그대로(하위호환) |

`POST /api/v1/alert-candidates` 및 단건 조회·수정 엔드포인트는 변경 없음.

## 2. FE 매핑

FE는 `asset.symbol`로 research 화면 딥링크를 구성한다. `price`/`change_percent`는 문자열
Decimal(C5), `get_market_provider()` 시세를 합친 값이다. watchlist expand·signals expand와
동일 형태.

`asset_id`가 없는 후보(매크로·시장 전체 경보 등)는 `asset: null`로 응답한다.

## 3. 계약 확정 (2026-06-29, Opus — 정본)

와이어 컨벤션은 기존과 동일: snake_case, 금액=Decimal **문자열**(C5), 시각=`UtcDatetime`,
공통 엔벨로프 `app/core/response.py`의 `paginated`. watchlist G5·signals G9와 **응답 형태·동작 일치**.

### 3.1 엔드포인트

| Method · Path | 책임 | meta |
| --- | --- | --- |
| `GET /api/v1/alert-candidates?page=&size=&sort=&candidate_type=&importance=&status=&expand=` | 후보 목록 조회 | 페이지 meta |

- Auth Required(`get_current_user`). 기존 쿼리(`pagination`, `sort`(허용값: `created_at`,`id` / 기본 `-created_at`),
  `candidate_type?`, `importance?`, `status?`) 그대로 유지.
- `expand`: 콤마 구분 문자열, 지원값 `asset`. 파싱은 signals·watchlist 라우터와 동일하게
  `[e.strip() for e in expand.split(",")]`에 `"asset"` 포함 여부로 판정.
- 미지정/지원 외 값이면 기존 `AlertCandidateResponse` 목록(하위호환). `asset` 키 자체가 없다.
- `response_model`은 signals와 동일하게 `ApiResponse[list[Any]]`로 완화.

### 3.2 응답 스키마

`expand=asset` 미지정 — 기존 `AlertCandidateResponse` 배열(변경 없음).

`expand=asset` 지정 — `AlertCandidateExpandedResponse` 배열:
- 기존 `AlertCandidateResponse` 전 필드(id, user_id, candidate_type, importance, status, title,
  message, asset_id, evidence, created_at) + `asset: AssetBriefResponse | None`.
- `asset`은 `{ symbol, name, price, change_percent, sector? }`. asset 미존재 또는 asset_id가
  None인 항목은 `null`.

`AssetBriefResponse`는 watchlist에서 이미 정의된 계약 객체를 **단일 정의로 재사용**한다
(`app/domains/watchlists/schema.py`에서 import). 중복 정의·assets로의 승격 리팩터는
불필요한 변경이므로 하지 않는다(향후 공용화는 follow-up).

### 3.3 서비스 동작

`list_candidates_expanded` — signals `list_signals_expanded` 패턴 미러:

1. 기존 `list_candidates`로 후보 목록 조회(기존 필터·정렬·페이지네이션 인자 동일).
2. 항목들의 `asset_id` 집합(None 제외)으로 `AssetRepository.get_by_id` 조회 → id→asset 맵.
3. 존재하는 asset symbol들로 `get_market_provider().get_quote(symbols)` 1회 호출 → symbol→quote 맵.
4. 항목별로 `AlertCandidateExpandedResponse`(기존 필드 + asset_brief) 구성.
   asset 미존재 시 `asset=None`, quote 미존재 시 `price`/`change_percent`는 `"0"`(watchlist·signals와 동일).
5. `count_candidates`로 total 산출(기존과 동일).

`app/domains/alert_candidates/service.py`에 `AssetRepository`·`get_market_provider()` 의존 추가.
signals 서비스(`app/domains/signals/service.py`)의 동일 의존 패턴을 그대로 따른다.

**다종목 영향 없음**: alert_candidates 목록은 서로 다른 asset_id를 가진 항목이 혼재할 수 있다.
그러나 구현이 이미 asset_id 집합 기반 배치 조회(step 2–3)로 설계되어 있어, 단일 종목과 다종목
모두 동일 코드 경로를 따른다. 페이지당 항목 수 한도 내에서 추가 영향 없음.

### 3.4 에러

신규 에러 코드 없음. 기존 인증/검증 에러만.

## 4. 범위 밖(후속)

- `AssetBriefResponse`의 공용 모듈(assets) 승격.
- expand 다중 필드 확장.
- FE 어댑터 매핑은 FE 트랙 별도 PR(FE Dashboard Priority Queue).
