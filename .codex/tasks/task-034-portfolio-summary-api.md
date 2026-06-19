# Codex Handoff Task

## Source Issue

Issue #54 (제목 Issue 34): `[BE] 포트폴리오 요약 API 추가`

## Task Summary

대시보드에서 보유 종목과 비중을 확인할 수 있도록 포트폴리오 요약 응답을 확장한다. 총 평가 금액·종목별 비중·섹터별 비중·현금 비중을 제공하고, 특정 종목/섹터 쏠림 여부를 판단한다.

## Goal

- 포트폴리오 요약(`GET /api/v1/portfolios/{portfolio_id}/summary`)이 다음을 포함하도록 확장된다:
  - 총 평가 금액(기존 `total_cost_value` 유지/확장)
  - 종목별 비중(기존 `positions[].weight` + `exceeds_threshold` 유지)
  - 섹터별 비중
  - 현금 비중
  - 특정 종목 과다 비중 여부(기존)
  - 특정 섹터 쏠림 여부(신규)
- Mock 포트폴리오 데이터로 외부 키 없이 동작한다.

## Background

- 기존 요약: `app/domains/portfolios/service.py::_build_summary` → `PortfolioSummaryResponse(portfolio_id, concentration_threshold, total_cost_value, positions[PositionWeight])`. 종목별 비중·임계 초과는 이미 구현됨.
- **선행 의존: Issue #51(task-031)** — 섹터별 비중은 `Asset.sector`가 필요. #51 머지 후 시작. 미머지 시 중단·보고.
- 현금 비중: 현재 포지션은 종목만 보유(현금 개념 없음). 권고: Portfolio Provider(mock)의 현금/평가금액을 활용하거나, 요약 계산에 현금 입력을 옵션으로 추가(과확장 금지 — 최소 구조). 접근을 PR에 명시.
- Portfolio Provider: `app/adapters/factory.py::get_portfolio_provider()` → `MockPortfolioProvider.fetch_holdings(account_ref)` → `HoldingResult(symbol, quantity, average_cost, market_value, currency, payload)`. market_value 기반 평가금액 산출에 사용 가능.
- 응답 envelope: `success`(단건).
- 비중 계산은 `Decimal`, 직렬화는 문자열(기존 컨벤션).

## Implementation Scope

- `app/domains/portfolios/schema.py` — `PortfolioSummaryResponse`에 `sector_weights: list[{sector, weight, exceeds_threshold?}]`, `cash_weight`, `has_sector_concentration` 등 추가. 기존 필드 유지(additive).
- `app/domains/portfolios/service.py` — 섹터별 집계(포지션→`Asset.sector` 매핑), 현금 비중, 섹터 쏠림 판정 로직 추가. 기존 `_build_summary`/`_calculate_weights` 확장.
- `app/domains/assets/repository.py`(읽기) — 포지션의 asset 섹터 조회(필요 시 배치 조회).
- (선택) Portfolio Provider 연동으로 mock 평가금액/현금 — 사용 시 factory 경유.
- `docs/designs/034-portfolio-summary-api.md` — 스켈레톤 설계문서.

## Out of Scope

- 실시간 평가금액(real market provider) — mock/원가 기반.
- 포지션 CRUD·집중도 점검(`/check`) 동작 변경.
- 섹터 마스터 테이블 등 추가 추상화(섹터는 `Asset.sector` 문자열 기준 그룹핑).

## Protected Files

변경하지 않는다:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`, `docs/decisions/`

## Requirements

- 섹터별 비중은 `Asset.sector`로 그룹핑. `sector`가 없는 종목은 `"UNKNOWN"`(또는 명시 라벨)으로 집계.
- 섹터 쏠림 임계치는 기존 `concentration_threshold` 재사용 또는 별도 상수(택1, PR 명시).
- 현금 비중 포함 시 전체 비중 합이 일관(종목+섹터+현금 정의 명확).
- 외부 키 없이 동작(mock).
- 기존 `summary` 응답 소비자가 깨지지 않도록 additive 확장.

## Test Requirements

- 섹터가 다른 다종목 포트폴리오의 섹터별 비중 합 검증.
- 섹터 쏠림 임계 초과/미만 케이스.
- 현금 비중 포함 시 합계 일관성.
- 섹터 미상(`sector=None`) 종목 처리.
- 기존 summary 필드 회귀 없음.
- `uv run pytest` 전체 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/designs/034-portfolio-summary-api.md` 신규(스켈레톤).
- `docs/api/frontend-api-spec.md` 포트폴리오요약 섹션의 summary 응답 예시 갱신.

## ADR Need

없음 — 기존 요약의 집계 확장.

## Failure Record Need

없음.

## Risk Level

Medium — 기존 summary 확장 + #51 의존. 계산 변경이 기존 소비자에 영향 가능 → additive 유지로 완화.

## Expected Output

- 스키마/서비스 확장 + 테스트.
- `uv run pytest`/lint/typecheck 통과.
- PR body에 `Closes #54`.

## Rules

- Issue #51(task-031) 머지 후 시작. 미머지 시 중단·보고.
- 기존 summary 필드/포지션 CRUD 동작 불변(additive).
- 섹터/현금 정의를 PR에 명시.
- 보호 파일 변경 금지. 가정과 검증 결과 보고.
