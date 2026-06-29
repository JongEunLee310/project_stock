# Codex Handoff Task

## Source Issue

- 설계 기록(정본): `docs/designs/048-portfolio-day-change.md`
- 대상 코드: `app/domains/portfolios/{schema,service}.py`, `app/adapters/market/base.py`(QuoteResult 참조)
- 테스트 선례: `tests/test_portfolio*.py`(summary 계산·monkeypatch market provider 패턴)

## Task Summary

`GET /api/v1/portfolios/{id}/summary` 응답에 일간 변동 `day_change_value`/`day_change_percent`를 추가한다.
summary 계산이 이미 `get_market_provider().get_quote`로 현재가를 조회하므로, **동일 quote의 `change_percent`를
재사용**해 추가 외부 호출 없이 일간 변동을 산출한다. expand 패턴 불필요 — 항상 포함하는 하위호환 필드 추가다.

## Goal

- `PortfolioSummaryResponse`에 `day_change_value: Decimal`, `day_change_percent: Decimal` 추가.
- 포지션 일간 변동 합으로 두 값 계산(§Background 규칙 정본).
- `get_quote` 호출 횟수 불변(1회). quote 누락 포지션 기여 0.
- 검증(pytest/ruff) 통과 + day change 신규 테스트.

## Background — 오케스트레이터가 확정한 사실 (추측 금지, 그대로 따를 것)

설계 §3은 `QuoteResult`(`app/adapters/market/base.py`: `price`, `change_percent` 모두 Decimal) 확인으로 확정됐다.

1. **스키마**(`app/domains/portfolios/schema.py` `PortfolioSummaryResponse`): 필드 두 개 추가 — `day_change_value: Decimal`, `day_change_percent: Decimal`. 기존 필드·순서 변경 금지(끝에 추가).
2. **quote 데이터 경로**(`app/domains/portfolios/service.py`): 현재 `_get_quotes_by_symbol`이 `{symbol_upper: price}`만 반환한다. `change_percent`도 필요하므로 `{symbol_upper: QuoteResult}`를 반환하도록 바꾸고, 기존 `price` 사용처(`_calculate_weights`의 `quotes_by_symbol.get(...)`)를 `quote.price`로 맞춘다. 누락 symbol은 기존처럼 fallback(price 0 / 기여 0). 외부 호출은 동일하게 `get_quote(symbols)` 1회.
3. **계산 규칙**(`_calculate_weights` 또는 인접 헬퍼, total_value 산출 직후):
   - 포지션별 `market_value = quantity * price`(기존 그대로).
   - 포지션별 `prev_value = market_value / (Decimal("1") + change_percent / Decimal("100"))`.
   - 가드: `price == 0`(quote 없음)이거나 분모 `(1 + change_percent/100) == 0`이면 그 포지션 day change 기여 0(`prev_value = market_value`로 두어 차이 0).
   - `day_change_value = Σ (market_value - prev_value)`.
   - `prev_total_value = total_value - day_change_value`(현금은 일간 변동 없음 — total_value는 기존 정의 그대로 market+cash).
   - `day_change_percent = (day_change_value / prev_total_value) * Decimal("100")` ; `prev_total_value == 0`이면 `Decimal("0")`.
   - 모든 산술은 `Decimal`. `change_percent`는 퍼센트 단위(예 `1.26` = +1.26%).
4. **반환 연결**: `_build_summary`가 `PortfolioSummaryResponse(...)` 생성 시 두 값을 채운다. `_calculate_weights` 반환 튜플을 확장하거나 별도 헬퍼로 산출해 전달 — signature 변경 시 호출부(`_build_summary`)만 맞추면 됨. `check_concentration`은 `_build_summary`를 재사용하므로 자동 반영(별도 작업 없음).

## Implementation Scope

- `app/domains/portfolios/schema.py` — `PortfolioSummaryResponse` 필드 2개 추가.
- `app/domains/portfolios/service.py` — `_get_quotes_by_symbol` 반환형 확장, day change 계산, `_build_summary` 연결.

## Out of Scope

- `riskExposures`, `aiBriefing`(정성 분석 — 후속 AI Briefing 작업).
- 포지션별 일간 변동률 노출, 전일 종가 스냅샷 영속화/신규 테이블.
- FE 레포 변경(별도 트랙). DB 마이그레이션·모델 변경.
- 엔드포인트 시그니처/쿼리/인증 변경. 무관 파일 리팩터.

## Protected Files

`.codex/*`, `docs/designs/*`, `docs/harness/*`, `docs/decisions/*` 수정 금지(설계 문서는 작성됨, 참조만).

## Requirements

- 기존 summary 필드·동작 **완전 보존**(추가 필드뿐). 기존 테스트 약화 금지.
- `get_quote`는 호출당 최대 1회(기존과 동일).
- 모든 금액·비율은 Decimal. 0 분모 가드 필수.

## Test Requirements

`tests/`의 기존 portfolio summary 테스트 파일에 day change 케이스 추가(기존 market provider monkeypatch 패턴 재사용):
- 알려진 `change_percent`를 주는 mock quote로 다종목 포지션 구성 → `day_change_value`가 포지션별 `market_value - market_value/(1+cp/100)` 합과 일치(Decimal 비교) 단언.
- `day_change_percent == day_change_value / (total_value - day_change_value) * 100` 단언.
- quote 누락(또는 price 0) 포지션은 day change 기여 0 단언.
- 포지션 없음/전일 평가액 0 → `day_change_value == 0`, `day_change_percent == 0`.
- `get_quote` 호출 1회 단언(가능하면 RecordingMarketProvider 패턴).

## Verification Commands

```
uv run ruff check .
uv run pytest tests/ -q -k portfolio
uv run pytest -q
```

## Documentation Impact

- 설계 `docs/designs/048-portfolio-day-change.md` 참조(Frozen).
- API spec(`docs/api/frontend-api-spec.md`)에 portfolio summary 응답 예시가 있으면 두 필드 1줄 추가(선택).

## ADR Need

불요. 기존 quote 재사용·파생 필드 추가, 신규 의존성/아키텍처 변경 없음.

## Failure Record Need

불요(국소 변경·회귀 테스트로 방지).

## Risk Level

Low. 외부 호출 불변, 추가 필드뿐. 분모 0/quote 누락 가드가 유일한 주의점.

## Expected Output

- 전용 브랜치 `feat/portfolio-day-change`(최신 `main` 기준, 이미 생성)에서 구현.
- 위 2개 파일 + 테스트 변경 커밋(한국어 메시지).
- 검증 전부 통과 로그.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
