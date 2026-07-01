# BE 확장: AssetBriefResponse에 market 노출

Status: Draft
Track: BE
Source: BE #159
Related FE: FE #90(시그널 스파크라인), FE #95(리서치 가격 라인차트)
Risk: Low

## 배경

FE 가격 시계열 연동은 `GET /api/v1/stocks/{symbol}/prices`를 호출합니다. 이 엔드포인트는
`market`(`KRX|NASDAQ|NYSE`)이 **필수** 파라미터입니다(`app/api/v1/endpoints/prices.py`).

signals 목록의 `?expand=asset` 응답에 쓰이는 공유 계약 객체 `AssetBriefResponse`
(`app/domains/watchlists/schema.py`)는 `symbol/name/price/change_percent/sector`만
노출하고 `market`이 없습니다. 그 결과 FE는 각 시그널 심볼의 market을 알 수 없어 가격
시계열 호출을 구성하지 못합니다(FE #90의 "심볼→market 매핑 확정" 블로커).

`assets` 모델은 이미 `market` 컬럼을 보유하고(`app/domains/assets/model.py`), asset 상세
(`app/domains/assets/schema.py`)는 이미 market을 노출합니다. 따라서 이 작업은 스키마
마이그레이션 없이 기존 컬럼을 brief 응답에 노출하는 additive 계약 확장입니다.

`AssetBriefResponse`는 [[signals-expand-asset]] 계약에서 signals·watchlists·
alert_candidates가 **단일 정의로 공유**하는 객체입니다. 따라서 확장은 세 도메인 응답에
동시에 반영됩니다.

## 범위

### 포함

- `AssetBriefResponse`에 `market: str` 필드 추가.
- 이 객체를 구성하는 3개 서비스 생성부에서 `market=asset.market` 전달:
  `signals`·`watchlists`·`alert_candidates` service.
- 계약 테스트(`ASSET_BRIEF_CONTRACT`)·도메인 테스트 기대값 갱신.

### 제외 (Out of Scope)

- 스키마 마이그레이션(asset 모델은 이미 market 보유).
- 가격 시계열 엔드포인트·provider 변경.
- FE 변경(별도 repo, 본 BE PR 머지 후 FE #90에서 진행).
- `price`·`change_percent` 등 기존 필드 동작 변경.

## 변경

### schema (`app/domains/watchlists/schema.py`)

`AssetBriefResponse`에 `market: str`를 추가합니다. 필수 필드로 둡니다(모든 실 asset이
market을 가지며, 세 생성부 모두 asset 객체 접근이 보장됩니다). 필드 배치는 `symbol` 인접이
자연스럽습니다.

### service (3개 도메인)

각 도메인 서비스의 `AssetBriefResponse(...)` 생성부에 `market=asset.market`를 추가합니다.
세 곳 모두 asset 객체가 이미 스코프에 있으므로 조인·추가 조회가 불요합니다.

- `app/domains/signals/service.py`
- `app/domains/watchlists/service.py`
- `app/domains/alert_candidates/service.py`

## Risks / Notes

**후방호환**: 응답에 필드를 추가하는 additive 변경입니다. 기존 소비자는 영향을 받지 않고,
FE는 필요 시 `asset.market`을 읽습니다.

**공유 계약**: 단일 정의 객체이므로 세 도메인 응답이 함께 변경됩니다. 세 도메인의 계약
테스트가 모두 market을 확인하도록 갱신합니다.

## 테스트

- 계약 테스트(`tests/test_api_contract.py`)의 `ASSET_BRIEF_CONTRACT`에 `"market": str` 추가.
- signals·watchlists·alert_candidates의 expand 테스트에서 `asset["market"]` 값이 fixture의
  market(`NASDAQ` 등)과 일치함을 확인.

## 관련 링크

- [[signals-expand-asset]] — AssetBriefResponse 공유 계약 정의
- [[price-series-api]] — market 필수 가격 시계열 엔드포인트
- BE 이슈 #159 — 본 작업 이슈
- FE 이슈 #90 · #95 — 본 확장이 unblock하는 FE 작업
