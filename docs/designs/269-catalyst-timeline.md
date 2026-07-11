# Design — Issue 269: 촉매(이벤트) 타임라인 계약

리서치 상세의 촉매 타임라인 카드(FE #147, 현재 빈 자리 카드)를 위해 자산별
예정 이벤트 목록 계약을 정의한다. 촉매는 긍정 이벤트만이 아니라 상승·하락
변동을 유발할 수 있는 사건 전체를 포함하며, 목적은 "다음 판단 시점이
언제인지"를 보여주는 것이다. 에픽은 FE #152.

## Background — 데이터 지형

- 예정 이벤트를 저장하는 테이블·수집 잡이 없다. `next_earnings_date`는
  시장 어댑터 quote의 라이브 파생값뿐이다.
- 같은 상황의 선례를 따른다: research-summary(#267)는 결정적 mock 템플릿,
  disclosure(#268)는 mock adapter 파생으로 계약을 먼저 확정했다. 촉매도
  **결정적 mock 서비스로 계약을 확정**하고 실수집(테이블·잡·실 소스)은
  후속 이슈로 분리한다. 신규 테이블·마이그레이션 없음.

## CatalystEventType enum

`EARNINGS`(실적) / `PRODUCT`(제품 출시) / `SHAREHOLDER_MEETING`(주주총회) /
`DIVIDEND`(배당) / `REGULATORY`(규제 결정) / `CONTRACT`(계약 만료·갱신) /
`LOCKUP`(락업 해제) / `CONFERENCE`(콘퍼런스) / `ECONOMIC`(경제지표) /
`OTHER`. 한국어 라벨은 FE 소관.

## API

| 항목 | 값 |
|------|----|
| 경로 | `GET /api/v1/assets/{asset_id}/catalysts` |
| 쿼리 | `limit: int = 10` |
| 인증 | `get_current_user` |
| 응답 | `ApiResponse[CatalystTimelineResponse]` |
| 오류 | 자산 미존재 404 `ASSET_NOT_FOUND` |

자산 중심 계층(`research-summary`·`news-disclosure`와 동일)을 따른다.

## Response Projections

**`CatalystEventProjection`**

| 필드 | 타입 | 비고 |
|------|------|------|
| `event_date` | `date` | 오름차순 정렬 기준 |
| `title` | `str` | |
| `event_type` | `CatalystEventType` (str enum) | |
| `is_estimated` | `bool` | 확정 일정 false / 예상 일정 true |

**`CatalystTimelineResponse`** — `{ asset_id: int,
events: list[CatalystEventProjection] }`. `event_date` 오름차순, 오늘(UTC)
이후 이벤트만, limit 적용.

월 단위 미정 일정("9월 중")의 표현은 실수집 도입 시 재검토한다 — 이번
계약은 구체 일자 + `is_estimated`로 단순화한다.

## Service — `app/domains/catalysts/service.py` (신규 도메인)

```
class CatalystService:
    def __init__(self, db: Session) -> None: ...

    def get_timeline(self, asset_id: int, limit: int = 10) -> CatalystTimelineResponse
        # 책임: 자산 존재 검증(AssetRepository.get_by_id, 미존재 404) 후
        #        결정적 mock 이벤트를 조립해 반환
```

- mock 파생 규칙: research-summary와 같은 `asset.id % N` 템플릿 로테이션.
  템플릿은 오늘 기준 상대 일자(예: +18일 실적 발표(is_estimated=false),
  +33일 제품 출시(예상), +47일 콘퍼런스, +62일 배당 등)로 이벤트 4~5건을
  생성한다. 제목은 한국어, 톤은 기존 mock과 동일한 점검 유도형.
- 같은 asset_id·같은 날짜 기준으로 결정적이다 (시간 의존은 "오늘" 기준
  상대 일자뿐).

## Schema — `app/domains/catalysts/schema.py`

- `CatalystEventType(str, Enum)`, `CatalystEventProjection`,
  `CatalystTimelineResponse` (위 표 그대로).

## Out of Scope

- 촉매 실수집 (저장 테이블·수집 잡·실 소스 연동) — 후속 이슈.
- `next_earnings_date` 라이브 어댑터 연동 (목록형 계약에서 N+1 라이브
  호출 회피 — 실수집 설계에서 함께 다룬다).
- FE 렌더 (FE #147).
- 마이그레이션 (없음).

## Open Questions

- 없음. mock 선행·실수집 후속 분리는 #267·#268 선례를 따른 확정이다.
