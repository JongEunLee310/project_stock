# Codex Handoff Task

## Source Issue

Issue #22: 포트폴리오 비중 점검 기능 구현

## Task Summary

Issue #21의 보유 종목(수량·평균 매수가)을 기반으로 포트폴리오 내 종목별 비중을 계산하고, 단일 종목 비중이 포트폴리오 임계치를 초과하면 경고 Signal을 생성한다. 요약 조회 API와 점검 실행 API를 추가한다.

## Goal

- 포트폴리오 내 종목별 비중(매수원가 기준)을 조회할 수 있다.
- 포트폴리오 총 평가금액(원가)과 종목별 원가를 조회할 수 있다.
- 단일 종목 비중이 포트폴리오 임계치를 넘으면 RISK_ALERT Signal을 생성할 수 있다.
- 포트폴리오 요약 정보를 API로 조회할 수 있다.
- 임계치는 포트폴리오별 컬럼(`concentration_threshold`)으로 관리한다.

## Background

- 현재가/시세 소스는 도입하지 않는다. 비중은 **매수원가 기준**(`quantity × avg_buy_price`)으로 계산한다.
- 설계 문서: `docs/designs/022-portfolio-concentration.md`
- 기존 signals 도메인(`app/domains/signals/`)의 `SignalRepository`, `SignalCreate`, `SignalType`, `exists_active`를 재사용한다. 신규 Signal 테이블·신규 SignalType은 추가하지 않는다.
- 기존 Portfolio 도메인(`app/domains/portfolios/`)의 레이어 구조·패턴(소유권 검증 `_get_owned_portfolio` 등)을 그대로 따른다.
- 인증된 사용자만 접근 — `app/api/v1/deps.py`의 `get_current_user` 사용.

## Implementation Scope

- `app/domains/portfolios/model.py` — Portfolio에 `concentration_threshold` 컬럼 추가
- `app/domains/portfolios/schema.py` — PortfolioCreate/Response 확장, PositionWeight/PortfolioSummaryResponse/PortfolioCheckResponse 추가
- `app/domains/portfolios/service.py` — PortfolioService에 `get_summary`, `check_concentration` 추가 + 비중 계산 헬퍼
- `app/api/v1/endpoints/portfolios.py` — GET `/{id}/summary`, POST `/{id}/check` 추가
- `alembic/versions/<rev>_add_concentration_threshold.py` — 신규 마이그레이션

## Out of Scope

- 현재가/시세 연동, 평가손익(원가 외 평가) 계산
- 임계치 수정 전용 API (생성 시 지정 + 기본값으로 충분)
- 비중 점검의 Background Job/스케줄 연동 (별도 이슈)
- 포트폴리오 이름·임계치 PATCH 수정
- 페이지네이션, CSV/외부 임포트

## Protected Files

변경하지 않는 파일:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`
- `docs/decisions/`

## Requirements

- `portfolios` 테이블에 `concentration_threshold` 추가: Numeric(5, 4), NOT NULL, server_default `0.4`(= 40%). 비중을 0~1 비율로 저장.
- `PortfolioCreate.concentration_threshold`: 선택 필드. 미지정 시 기본 0.4. 범위 `0 < x ≤ 1`.
- 비중 계산: 종목 원가 = `quantity × avg_buy_price`, 총 원가 = 종목 원가 합, 비중 = 종목 원가 / 총 원가. 총 원가가 0이면 모든 비중 0. Decimal 정밀도 유지.
- `exceeds_threshold` = 비중 > `concentration_threshold`.
- `get_summary`는 읽기 전용 — Signal을 생성하지 않는다.
- `check_concentration`은 초과 종목마다 `SignalType.RISK_ALERT` Signal 생성:
  - `asset_id`=해당 종목, `news_item_id`=None, `thesis_id`=None
  - `score`는 0~100 범위에서 비중에 비례해 산정
  - `evidence`에 weight·threshold·cost_value 포함
  - 중복 방지: `SignalRepository.exists_active(asset_id, SignalType.RISK_ALERT.value, None)`가 True면 재생성하지 않음
  - 반환값에 요약(PortfolioSummaryResponse)과 생성된 Signal 목록(SignalResponse) 포함
- 소유권 검증: 다른 사용자 portfolio 접근 시 403, 미존재 시 404 (기존 `_get_owned_portfolio` 재사용).
- Alembic `down_revision`은 현재 head revision `a1b2c3d4e5f6`를 참조.

## Test Requirements

- `tests/test_portfolios.py` 확장 (신규 파일 가능):
  - 요약 조회: 종목별 비중·총 원가·exceeds_threshold 정확성 (Decimal 비교)
  - 총 원가 0(보유 종목 없음) 시 비중 0 처리
  - 점검 실행: 임계치 초과 종목에 RISK_ALERT Signal 생성 검증
  - 점검 재실행 시 활성 Signal 중복 미생성 검증
  - 임계치 미초과 시 Signal 미생성 검증
  - 소유권 403 / 미존재 404 경로
- 기존 테스트를 약화하지 않는다.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest tests/test_portfolios.py -v
```

## Documentation Impact

- `docs/designs/022-portfolio-concentration.md` 이미 작성됨 (변경 불필요)
- 포트폴리오 요약/점검 API의 README 반영은 Issue #25 범위

## ADR Need

없음. 가격 소스 미도입·매수원가 기준 비중 방침은 설계 021·022에 기록됨.

## Failure Record Need

없음.

## Risk Level

High — 기존 portfolios 테이블 스키마 변경(컬럼 추가) 및 Signal 생성 로직 포함. Human Gate 완료(2026-06-19 사용자 명시적 승인: 포트폴리오별 임계치 설정 컬럼 + 별도 점검 POST 엔드포인트 방식).

## Expected Output

- 위 scope 파일 변경 및 신규 마이그레이션 생성
- `uv run pytest tests/test_portfolios.py` 통과
- lint/typecheck 통과
- PR body에 closing keyword 포함 (`Closes #22`)

## Rules

- 스코프 외 파일 변경 금지.
- 테스트 약화 금지.
- 보호 파일 변경 금지.
- 가정과 검증 결과를 보고.
