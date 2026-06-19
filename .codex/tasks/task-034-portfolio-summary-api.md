# Codex Handoff Task

## Source Issue

Issue #54 (제목 Issue 34): `[BE] 포트폴리오 요약 API 추가`

## Task Summary

대시보드에서 보유 종목과 비중을 확인할 수 있도록 포트폴리오 요약 API를 확장한다. 기존 `PortfolioService.get_summary`(원가 기준 비중)에 시세 기반 평가금액, 섹터별 비중, 현금 비중, 섹터 쏠림 여부를 추가한다. 현금은 신규 `Portfolio.cash_balance` 필드로 영속한다.

## Goal

- 포트폴리오 요약 응답에 다음이 포함된다.
  - 총 평가 금액(시세 기반 평가금액 + 현금)
  - 종목별 비중(기존)
  - 섹터별 비중(신규)
  - 현금 비중(신규)
  - 특정 종목 과다 비중 여부(기존 `exceeds_threshold`)
  - 특정 섹터 쏠림 여부(신규)
- `Portfolio.cash_balance` 필드 추가 + alembic 마이그레이션.
- mock 포트폴리오 데이터로 요약 API 동작을 검증할 수 있다.

## Background

- **설계문서 우선 확인**: `docs/designs/034-portfolio-summary-api.md`(Claude Code 작성, 스켈레톤)를 먼저 읽고 그 Data Model/API/Decisions를 따른다. 구현 중 설계와 달라지면 설계문서를 함께 갱신한다.
- 기존 도메인 확장. 신규 도메인 아님.
- 기존 요약 로직: `app/domains/portfolios/service.py`의 `get_summary` / `_build_summary` / `_calculate_weights`. 현재는 **원가 기준**(`quantity * avg_buy_price`)으로 `total_cost_value`와 종목별 `weight`, `exceeds_threshold`를 계산한다.
- 평가금액(시세) 산출은 #51 패턴을 그대로 따른다: `app/domains/assets/service.py:47`처럼 `from app.adapters.factory import get_market_provider`로 시세를 받아 `quantity * price`로 평가금액을 만든다. 외부 키 없이 `MockMarketDataProvider`(`app/adapters/market/mock.py`)로 동작.
- 섹터 비중: `Asset.sector`(`app/domains/assets/model.py:17`, nullable). sector가 없으면 `"UNKNOWN"` 등으로 묶는다.
- 현금: 사용자 결정에 따라 `Portfolio` 모델에 `cash_balance` 컬럼을 추가하고 마이그레이션한다(기존 `concentration_threshold` 마이그레이션 `b2c3d4e5f607_add_concentration_threshold.py` 참조).
- 섹터 쏠림 임계치: 기존 종목 임계치(`concentration_threshold`)를 재사용할지 별도 상수를 둘지 결정해 PR에 명시. 과확장 금지(별도 컬럼 추가는 지양, 상수 또는 기존 threshold 재사용 권장).
- 응답 envelope: `app/core/response.py` `success`.
- 시세 합성은 mock이므로 평가금액은 결정적(deterministic)이어야 테스트가 안정적이다.

## Implementation Scope

- `app/domains/portfolios/model.py` — `cash_balance` 컬럼 추가(Decimal, default 0, server_default).
- `app/domains/portfolios/schema.py` — `PortfolioSummaryResponse`에 평가금액/섹터 비중/현금 비중/섹터 쏠림 필드 추가. 섹터 비중 표현용 신규 스키마(`SectorWeight` 등) 최소 추가. `PositionWeight`에 `market_value`/시세 기반 `weight` 필요 시 추가(원가 비중과 혼동되지 않게 명명).
- `app/domains/portfolios/service.py` — `_build_summary`/비중 계산에 시세 평가금액, 섹터 집계, 현금 비중, 섹터 쏠림 판정 추가. `get_market_provider()` 사용.
- `app/domains/portfolios/repository.py` — 필요 시 cash_balance 반영(생성/조회). `PortfolioCreate`에 cash_balance 입력 허용 여부 결정(권장: optional, default 0).
- `alembic/versions/` — `cash_balance` 컬럼 마이그레이션(upgrade/downgrade).
- mock 포트폴리오 데이터 — 테스트 fixture 또는 기존 mock 경로 활용(신규 영구 시드 추가는 지양, 테스트 내 구성 권장).
- `docs/designs/034-portfolio-summary-api.md` — 기존 스켈레톤 설계문서. 설계와 구현이 달라지면 갱신.
- `docs/api/frontend-api-spec.md` — 포트폴리오 요약 응답 필드 갱신.

## Out of Scope

- 실시간 외부 시세 연동(mock provider만 사용).
- 손익(P&L)/수익률 등 이슈에 없는 지표 추가.
- 자동 매매/리밸런싱 동작.
- alerts/signals 도메인 수정(집중도 신호 생성은 기존 `check_concentration` 유지, 본 태스크에서 손대지 않음).

## Protected Files

변경하지 않는다:

- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`, `docs/decisions/`

## Requirements

- 요약 응답에 총 평가금액, 종목별 비중, 섹터별 비중, 현금 비중, 종목 과다 비중 여부, 섹터 쏠림 여부가 모두 포함된다.
- 평가금액 = Σ(quantity × mock 시세 price) + cash_balance. 비중은 이 총액 기준.
- 비중 합(종목 비중 + 현금 비중)은 반올림 오차 범위 내에서 1에 수렴.
- sector가 null인 종목은 누락 없이 단일 그룹으로 집계.
- `cash_balance` 마이그레이션 upgrade/downgrade 작성, 기존 데이터에 default 적용.
- 본인 포트폴리오만 접근(기존 `_get_owned_portfolio` 유지).
- 시세는 mock으로 결정적 — 외부 키 불필요.

## Test Requirements

- 평가금액이 시세 기반으로 계산되는 테스트(mock 시세 검증).
- 섹터별 비중 집계 테스트(다중 섹터 + sector null 포함).
- 현금 비중 테스트(cash_balance 반영, 비중 합 ≈ 1).
- 섹터 쏠림 여부 / 종목 과다 비중 여부 판정 테스트.
- 기존 `tests/test_portfolios.py` 회귀 통과 + 신규 케이스 추가.
- `uv run pytest` 전체 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/designs/034-portfolio-summary-api.md` 참고 및 필요 시 갱신(Claude Code가 스켈레톤 작성 완료).
- `docs/api/frontend-api-spec.md` 포트폴리오 요약 섹션 갱신(신규 필드 반영).

## ADR Need

불요 — 기존 도메인 확장이며 mock provider/기존 패턴(#51) 재사용. 현금 모델링이 향후 손익 계산 등으로 확장될 경우 후속 ADR 검토.

## Failure Record Need

없음.

## Risk Level

Medium — 모델 컬럼 추가 + 마이그레이션, 기존 요약 응답 스키마 변경(프론트 연동 영향). 동작은 조회 한정으로 부수효과 작음.

## Expected Output

- portfolios 도메인 확장(model/schema/service/repository) + 마이그레이션 + 테스트.
- `uv run pytest`/lint/typecheck 통과.
- PR body에 `Closes #54`.

## Rules

- 기존 요약/집중도 신호 동작을 깨지 않는다(회귀 테스트 유지).
- 시세는 mock provider만 사용, 외부 호출 금지.
- 보호 파일 변경 금지.
- 가정(섹터 쏠림 임계치 정의, cash 입력 방식)과 검증 결과 보고.
