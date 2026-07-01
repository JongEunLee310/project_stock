# 059 · 대시보드 브리핑 watchlist_highlights 채움 (status 계약)

Status: Draft
작성: Claude Code (orchestrator)
관련: 설계 058(대시보드 브리핑), Epic #141, ADR-008·ADR-009, signals 도메인(`SignalType`)

## 1. 배경

설계 058의 대시보드 브리핑은 1차 구현에서 `watchlist_highlights`를 빈 배열로 두었다.
이유는 관심 종목의 표시 상태(`status`)를 표현할 계약이 watchlist 도메인에 없었기
때문이다(058 §3 구현 현황, §10 후속). 본 설계는 그 후속을 다룬다. 신규 테이블·도메인을
만들지 않고, 이미 존재하는 signals 도메인의 활성 신호에서 종목별 상태를 파생해 highlight를
채운다.

핵심 결정은 사용자와 정렬했다.

- **status 의미**: 자산의 활성 `SignalType` 중 우선순위가 가장 높은 하나를 status로 노출한다
  (활성 신호 우선순위 라벨). 활성 신호가 없으면 `NORMAL`이다.
- **신규 저장소 없음**: 상태를 위한 테이블·컬럼을 추가하지 않는다. signals의 활성 신호를
  자산 단위로 조회하는 read 경로만 추가한다.

## 2. 범위

포함:

- signals repository에 자산별 활성 신호 타입 조회 read 메서드 추가.
- watchlist 종목 → `WatchlistHighlight` 해소 로직(`DashboardBriefingService` 내부).
- status 파생 규칙(우선순위 라벨)과 상수.
- 대시보드 브리핑이 실제 highlight를 담아 projection을 구성.

비포함(분리):

- `WatchlistHighlight` 계약 자체 변경 — 이미 존재하는 필드(`symbol`·`status`·`per`·`peg`·
  `daily_change_percent`)를 그대로 채운다. 계약 스키마는 바꾸지 않는다.
- signals 생성·판정 로직 — 기존 규칙을 그대로 읽기만 한다.
- watchlist 도메인 스키마·테이블 변경 — 없음.
- FE 연동 — 별도(설계 074). 본 변경은 브리핑 *입력* projection만 바꾸므로 FE-facing 응답
  형태(`DashboardBriefingResponse`)는 불변이다.
- 캐시·검증·폴백 — 058과 동일하게 ADR-010/011/012 분리.

## 3. status 계약 — 활성 신호 우선순위 라벨

status 문자열은 자산의 활성 `SignalType` 값 중 하나이거나 `NORMAL`이다. 별도 enum을 새로
만들지 않고 기존 `SignalType` 값 + `NORMAL` sentinel을 사용한다.

우선순위(높음 → 낮음):

| 순위 | SignalType | 의미 |
| --- | --- | --- |
| 1 | RISK_ALERT | 위험 경보 |
| 2 | THESIS_BROKEN | 투자 논거 훼손 |
| 3 | SELL_REVIEW | 매도 검토 |
| 4 | OVERHEATED | 과열 |
| 5 | BUY_CANDIDATE | 매수 후보 |
| 6 | WATCH | 관찰 |
| — | (활성 신호 없음) | NORMAL |

한 자산에 여러 활성 신호가 있으면 위 순위상 가장 높은 하나를 status로 택한다.
우선순위 상수는 signals 도메인(`app/domains/signals/types.py` 인접) 또는 브리핑 조립부에
둔다(핸드오프에서 위치 확정). 위험 우선 노출을 위해 RISK_ALERT를 최상위로 둔다.

## 4. signals repository — read 메서드 추가

기존 `count_assets_with_active_signal(asset_ids, signal_type)`은 단일 타입의 자산 수만
센다. highlight는 자산별로 어떤 활성 신호가 있는지 알아야 하므로, 자산 단위 조회를 추가한다.

시그니처(위치: `app/domains/signals/repository.py`):

```
def active_signal_types_by_asset(
    self,
    asset_ids: list[int],
) -> dict[int, set[str]]
```

책임: 주어진 자산들에 대해 활성 신호(`_active_clause`)의 `signal_type` 집합을 자산 id별로
반환한다. 빈 입력이면 빈 dict. 기존 `_active_clause`를 재사용해 활성 판정 기준을 일치시킨다.

## 5. status 파생 헬퍼

시그니처(위치: signals 도메인 또는 브리핑 조립부):

```
def resolve_watchlist_status(active_types: set[str]) -> str
```

책임: 활성 신호 타입 집합을 받아 §3 우선순위상 최상위 하나를 반환한다. 집합이 비면
`NORMAL`을 반환한다.

## 6. DashboardBriefingService 변경

현재 `generate(user_id)`는 `to_dashboard_snapshot(summary, highlights=[])`로 highlight를
비운다. 이를 실제 highlight 해소로 바꾼다.

`generate` 책임(변경분):

1. 사용자의 관심 종목을 조회한다(기존 watchlist repository 재사용). 여러 watchlist가 있으면
   사용자 전체를 대상으로 하되, 상위 N개만 highlight로 추린다(정렬·N은 핸드오프에서 확정,
   기본은 `priority` 우선·최근순, N은 소수).
2. 대상 자산의 `symbol`·`per`·`peg`·`daily_change_percent`를 market provider quote와 asset
   조회로 해소한다(포트폴리오 브리핑이 quote로 일간변화를 해소하는 것과 동일 경로).
3. `active_signal_types_by_asset(asset_ids)`로 자산별 활성 신호를 조회하고,
   `resolve_watchlist_status`로 각 종목의 status를 파생한다.
4. `WatchlistHighlight` 리스트를 만들어 `to_dashboard_snapshot(summary, highlights)`에
   전달한다.

`to_dashboard_snapshot` 시그니처는 이미 `highlights: Sequence[WatchlistHighlight]`를 받으므로
빌더 자체는 바꾸지 않는다. per/peg/quote를 구하지 못하는 종목은 `None`으로 두고(계약이 이미
`per`·`peg`를 Optional로 둠) status만 파생한다. 관심 종목이 없으면 빈 리스트로 두어 기존
동작과 호환한다.

## 7. 프라이버시 판단 (ADR-009)

- `symbol`·PER/PEG·일간변화는 공개 시장 데이터이며 보유 금액을 포함하지 않는다(058 §3.1과
  동일 정렬).
- status는 signals 도메인이 이미 계산한 활성 신호의 종류일 뿐 사용자 금액·수량이 아니다.
  "이 사용자가 해당 종목을 관심 목록에 두고, 그 종목에 위험 신호가 있다"는 사실 노출은
  058에서 정렬한 관심 종목 노출 trade-off의 연장선이며 금액을 더하지 않는다.
- payload 등급은 여전히 `AGGREGATED`이고 `PrivacyGate` 통과에 코드 변경이 없다. highlight를
  채워도 projection 화이트리스트에 금액 필드는 추가되지 않는다.

## 8. 의존성

- `app/domains/signals/repository.py` — read 메서드 추가.
- `app/domains/signals/types.py` — 우선순위 상수(또는 조립부).
- `app/domains/watchlists`(관심 종목 조회) — 재사용.
- `app/domains/assets`·market provider quote — `symbol`·per/peg/change 해소에 재사용.
- `app/domains/dashboard/briefing_service.py` — highlight 해소로 변경.
- `app/adapters/llm/privacy.py`(`to_dashboard_snapshot`·`WatchlistHighlight`) — 시그니처 불변,
  실제 값만 채움.

## 9. 테스트

- signals repository: `active_signal_types_by_asset` — 활성/비활성 신호 구분, 다중 타입 집합,
  빈 입력.
- status 파생: 우선순위 규칙(RISK_ALERT 최상위), 빈 집합 → `NORMAL`.
- projection: highlight가 채워져도 금액 필드 부재·`sensitivity == AGGREGATED` 유지, 원본
  entity `PrivacyGate.guard` 거부(058 회귀 방지 확장).
- 서비스: 활성 신호가 있는 관심 종목이 highlight로 반영되고 status가 기대대로 파생, 관심
  종목 없음/quote 결측 시 graceful.
- API: `GET /dashboard/briefing` 응답 형태 불변 확인(highlight는 입력 전용이라 응답에
  나타나지 않음).

## 10. 비범위 / 후속

- highlight 정렬·상위 N 정책 정교화(가중치·리스크 우선 등)는 후속 조정 여지.
- signals 활성 판정 기준 변경은 본 설계 범위 밖(기존 `_active_clause`를 그대로 신뢰).
- future_primary=local 전환 시 본 projection·status가 로컬 경로에서 그대로 재사용된다(058 §10).
