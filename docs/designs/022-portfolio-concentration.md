# Design: 포트폴리오 비중 점검 (Issue #22)

Issue #21에서 구축한 보유 종목(수량·평균 매수가) 기반으로, 포트폴리오 내 종목별 비중과 집중도를 계산하고 단일 종목 비중 초과 시 경고 Signal을 생성한다. 현재가/시세 소스는 도입하지 않으며 비중은 **매수원가 기준**으로 산출한다.

## 비중 정책

- 종목 평가금액(원가) = `quantity × avg_buy_price`
- 총 평가금액 = `Σ(quantity × avg_buy_price)`
- 종목별 비중 = `종목 원가 / 총 원가` (총 원가가 0이면 비중 0)
- 단일 종목 비중이 포트폴리오 임계치를 초과하면 경고 대상

## 스키마 변경: portfolios 테이블 (컬럼 추가)

| 필드 | 타입 | 제약 |
|------|------|------|
| concentration_threshold | Numeric(5, 4) | NOT NULL, server_default 0.4 |

- 비중 임계치를 0~1 비율로 저장(예: 0.4 = 40%). 기존 행은 server_default로 채운다.
- Human Gate: 2026-06-19 사용자 명시적 승인(포트폴리오별 설정 컬럼 방식 선택).

## 스키마 (Pydantic)

- `PortfolioCreate`: name, concentration_threshold(선택, 미지정 시 기본 0.4, 0 < x ≤ 1)
- `PortfolioResponse`: 기존 필드 + concentration_threshold
- `PositionWeight`: asset_id, quantity, avg_buy_price, cost_value, weight, exceeds_threshold
- `PortfolioSummaryResponse`: portfolio_id, concentration_threshold, total_cost_value, positions(list[PositionWeight])
- `PortfolioCheckResponse`: summary(PortfolioSummaryResponse), created_signals(list[SignalResponse])

## 비중 계산 헬퍼

- `calculate_weights(positions, threshold) -> tuple[total_cost_value, list[PositionWeight]]`
  - 원가·총원가·비중·초과 여부 계산만 담당(읽기 전용, 사이드이펙트 없음). Decimal 정밀도 유지.

## Service (PortfolioService 확장)

- `get_summary(portfolio_id, user_id) -> PortfolioSummaryResponse`
  - 소유권 검증 → 보유 종목 조회 → 비중 계산 후 요약 반환(읽기 전용).
- `check_concentration(portfolio_id, user_id) -> PortfolioCheckResponse`
  - 소유권 검증 → 비중 계산 → 임계치 초과 종목마다 RISK_ALERT Signal 생성(중복 방지) → 요약 + 생성 Signal 반환.

## Signal 생성 정책

- 초과 종목에 대해 `SignalType.RISK_ALERT` Signal 생성.
- `news_item_id=None`, `thesis_id=None`. evidence에 weight·threshold·cost_value 기록.
- 중복 방지: 기존 `SignalRepository.exists_active(asset_id, "RISK_ALERT", None)`로 활성 신호 존재 시 재생성하지 않음.
- score는 비중에 비례해 산정(상세 산식은 구현에서 결정, 0~100 범위).

## API (인증 필요)

| Method | Path | 요청 | 응답 |
|--------|------|------|------|
| GET | /api/v1/portfolios/{id}/summary | — | PortfolioSummaryResponse |
| POST | /api/v1/portfolios/{id}/check | — | PortfolioCheckResponse |

- 소유권: 다른 사용자의 portfolio 접근 시 403, 미존재 시 404.
- GET summary는 읽기 전용(Signal 생성 없음). POST check만 Signal을 생성한다.

## 의존성

- Issue #21 (Portfolio 도메인) — portfolios/positions 테이블, PortfolioService
- signals 도메인 — SignalRepository/SignalCreate/SignalType 재사용 (신규 Signal 테이블 없음)

## Alembic 마이그레이션

신규 파일: `alembic/versions/<rev>_add_concentration_threshold.py`
`down_revision`은 현재 head revision `a1b2c3d4e5f6`(create_portfolios_tables)를 참조.
portfolios 테이블에 concentration_threshold 컬럼 추가(server_default 0.4, NOT NULL).
