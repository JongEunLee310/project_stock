# Codex Handoff Task

## Source Issue

Epic #141 (LLM 하이브리드 아키텍처), 설계 `docs/designs/059-watchlist-highlight-status.md`,
선행 설계 058(대시보드 브리핑)의 후속(§10).

## Task Summary

대시보드 브리핑의 `watchlist_highlights`를 실제 관심 종목으로 채운다. signals 도메인의 활성
신호에서 종목별 `status`를 파생하고, `symbol`·PER/PEG·일간변화를 해소해 highlight를 구성한다.
신규 테이블·도메인을 만들지 않는다.

## Goal

완료 시 참이어야 할 것:

- `GET /dashboard/briefing`이 관심 종목이 있을 때 실제 highlight를 담은 CloudSafe projection으로
  LLM을 호출한다(빈 배열 fallback 제거).
- 각 highlight의 `status`가 자산의 활성 `SignalType` 중 최우선 하나(없으면 `NORMAL`)로 파생된다.
- projection은 여전히 `AGGREGATED`이고 금액 필드를 포함하지 않으며, `DashboardBriefingResponse`
  응답 형태는 불변이다.

## Background

- 설계 058은 watchlist 도메인에 표시용 `status` 계약이 없어 highlight를 빈 배열로 두었다.
- `WatchlistHighlight` 계약(`app/adapters/llm/privacy.py`)은 이미 존재한다:
  `symbol: str`, `status: str`, `per: Decimal | None`, `peg: Decimal | None`,
  `daily_change_percent: Decimal`. 계약 자체는 바꾸지 않는다.
- `to_dashboard_snapshot(summary, highlights)`도 이미 `highlights: Sequence[WatchlistHighlight]`를
  받는다. 빌더 시그니처는 바꾸지 않고 서비스가 실제 highlight를 전달하도록 바꾼다.
- signals repository에 `count_assets_with_active_signal(asset_ids, signal_type)`가 있으나 단일
  타입의 자산 수만 센다. 자산별 활성 신호 타입 조회가 필요하다.
- `SignalType`(`app/domains/signals/types.py`): WATCH·RISK_ALERT·THESIS_BROKEN·BUY_CANDIDATE·
  SELL_REVIEW·OVERHEATED.
- PER/PEG/change_percent는 market provider `quote`에서 온다(asset service `get_detail`가
  `quote.per`·`quote.peg`·`quote.change_percent` 사용). 포트폴리오 브리핑 서비스가 이미 quote로
  일간변화를 해소하는 경로를 참고한다.

## Implementation Scope

- `app/domains/signals/repository.py` — `active_signal_types_by_asset(asset_ids) -> dict[int, set[str]]`
  추가. 기존 `_active_clause`를 재사용해 활성 판정 기준을 일치시킨다.
- status 우선순위 상수와 `resolve_watchlist_status(active_types: set[str]) -> str` 헬퍼 추가.
  위치는 signals 도메인(types 인접) 또는 대시보드 브리핑 조립부 중 응집도가 높은 쪽으로 둔다.
  우선순위(높음→낮음): RISK_ALERT > THESIS_BROKEN > SELL_REVIEW > OVERHEATED > BUY_CANDIDATE >
  WATCH, 없으면 `NORMAL`.
- `app/domains/dashboard/briefing_service.py` — `generate`에서 사용자 관심 종목 상위 N개를
  해소해 `WatchlistHighlight` 리스트를 만들고 `to_dashboard_snapshot`에 전달. 정렬은 `priority`
  우선·최근순, N은 소수(예: 5). quote/per/peg 결측은 `None`으로 두고 status만 파생. 관심 종목이
  없으면 빈 리스트(기존 동작 유지).
- watchlist/asset repository는 조회만 재사용한다.

## Out of Scope

- `WatchlistHighlight`·`DashboardBriefingSnapshot`·`DashboardBriefingResponse` 계약 스키마 변경.
- watchlist 도메인 스키마·모델·테이블 변경, 신규 도메인·마이그레이션.
- signals 생성·판정 규칙·`_active_clause` 정의 변경(읽기만).
- LLM 라우팅 표(`router.py`)·`PrivacyGate`·`complete_json` 변경.
- 캐시·출력 검증 강화·safe template 폴백(ADR-010/011/012), 결과 영속화.
- FE 연동(별도 repo, 설계 074).
- 포트폴리오 브리핑 관련 변경.

## Protected Files

없음(보호 파일 수정 없음). 보호 대상(AGENTS.md·CLAUDE.md·.github/workflows/·docs/harness/·
docs/decisions/)은 건드리지 않는다.

## Requirements

- 신규 조회는 N+1을 피하도록 자산 id 목록으로 배치 조회한다(`active_signal_types_by_asset`는
  단일 쿼리).
- status 문자열은 `SignalType` 값 또는 `NORMAL`만 사용한다(임의 문자열 금지).
- projection에 금액·수량·평가액·원가·절대 현금잔액을 추가하지 않는다(ADR-009 fail-closed 유지).
- 에러 처리는 시스템 경계에서만. 관심 종목·quote 결측은 예외가 아니라 graceful degradation.

## Test Requirements

- signals repository: `active_signal_types_by_asset` — 활성/비활성 구분, 다중 타입 집합, 빈 입력.
- status 파생: 우선순위(RISK_ALERT 최상위 등), 빈 집합 → `NORMAL`.
- projection 회귀: highlight가 채워져도 금액 필드 부재·`sensitivity == AGGREGATED`, 원본 entity가
  `PrivacyGate.guard`에서 거부(058 회귀 테스트 확장).
- 서비스: 활성 신호가 있는 관심 종목이 highlight로 반영되고 status가 기대대로 파생, 관심 종목
  없음/quote 결측 graceful.
- API: `GET /dashboard/briefing` 응답 형태 불변(highlight는 입력 전용).

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

설계 `docs/designs/059-watchlist-highlight-status.md`가 본 작업의 근거다. 058 §3 구현 현황·§10
후속 항목을 "채움 완료"로 갱신할 수 있으나, 문서 갱신은 orchestrator(Claude Code)가 리뷰 시
처리하므로 Codex는 코드·테스트에 집중한다.

## ADR Need

불필요. ADR-008/009의 기존 결정을 따르며 새 아키텍처 결정이 없다. status는 signals의 기존
활성 신호를 읽어 파생할 뿐 새로운 계약 레이어가 아니다.

## Failure Record Need

불필요. 알려진 실패 재발이 아니다.

## Risk Level

Medium. 클라우드로 나가는 projection에 종목 단위 정보를 추가하므로 ADR-009 경계 회귀가
핵심 위험이다. 금액 필드 부재·`AGGREGATED` 유지·원본 entity 거부를 테스트로 고정하고, 머지 전
사람 리뷰(ADR-009)를 거친다.

## Expected Output

- feature 브랜치(최신 main 기준)와 PR.
- 위 scope의 코드·테스트 변경.
- 가정(정렬 기준·N 값·헬퍼 위치)과 검증 결과 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.

## Stop Conditions

- signals의 활성 판정(`_active_clause`)이나 quote 소스가 highlight 요구와 맞지 않아 계약
  해석이 모호하면 멈추고 보고한다.
- projection에 금액 계열 필드를 넣어야만 요구가 충족된다고 판단되면 멈춘다(ADR-009 위반 신호).
- 신규 테이블·마이그레이션이 필요하다고 판단되면 멈춘다(범위상 금지).
