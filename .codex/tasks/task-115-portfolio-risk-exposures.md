# Codex Handoff Task

## Source Issue

- 설계 기록(정본): `docs/designs/049-portfolio-risk-exposures.md`
- 대상 코드: `app/domains/portfolios/{schema,service}.py`
- 테스트 선례: `tests/test_portfolios.py`(summary 계산·monkeypatch market provider 패턴, day change 케이스)

## Task Summary

`GET /api/v1/portfolios/{id}/summary` 응답에 `risk_exposures: list[RiskExposure]`를 추가한다. 모든 판정은
summary가 **이미 계산한 값**(섹터 비중·종목 비중·현금 비중·임계값)에서 파생하므로 **추가 외부 호출이
없다**. 임계값 기반 데이터 규칙만 사용하며, 의미 범주 분류(반도체/성장주 등) 하드코딩은 도입하지 않는다.

## Goal

- 신규 스키마 `RiskExposure` + `PortfolioSummaryResponse`에 `risk_exposures: list[RiskExposure]` 추가.
- 규칙 3종(섹터 쏠림·단일 종목 쏠림·현금 부족)으로 노출 목록 산출(§Background 정본).
- `get_quote` 호출 횟수 불변. 검증(ruff/mypy/pytest) 통과 + 신규 테스트.

## Background — 오케스트레이터가 확정한 사실 (추측 금지, 그대로 따를 것)

설계 §3을 정본으로 따른다. summary 계산부(`_calculate_weights`)는 이미 `sector_weights`(섹터별
weight·exceeds_threshold), `positions`(종목별 weight·exceeds_threshold), `cash_weight`를 산출한다.

1. **스키마**(`app/domains/portfolios/schema.py`):
   - 신규 `RiskExposure(BaseModel)`: `code: str`, `label: str`, `level: str`, `description: str`.
   - `PortfolioSummaryResponse`에 `risk_exposures: list[RiskExposure]` 추가(끝에 추가, 기존 필드·순서 변경 금지).

2. **판정 상수**(`app/domains/portfolios/service.py` 모듈 상단, 조정 가능하게):
   - `RISK_LEVEL_HIGH_MULTIPLIER = Decimal("1.5")`
   - `CASH_FLOOR_HIGH = Decimal("0.05")`, `CASH_FLOOR_MEDIUM = Decimal("0.15")`

3. **판정 규칙**(신규 헬퍼 `_calculate_risk_exposures(...)`, 이미 계산된 값 입력으로 받음 — 추가 시세 호출 금지):
   - **SECTOR_CONCENTRATION**: `sector_weights` 중 `exceeds_threshold`이고 `sector != "UNKNOWN"`인 섹터마다 1건.
     - `level` = `"HIGH"` if `weight >= concentration_threshold * RISK_LEVEL_HIGH_MULTIPLIER` else `"MEDIUM"`.
     - `code` = `f"SECTOR_CONCENTRATION:{sector}"`, `label` = `f"{sector} 섹터 쏠림"`.
     - `description` = 섹터 비중·임계값을 언급하는 한국어 문장(정중·담백 `~합니다` 톤).
   - **SINGLE_NAME_CONCENTRATION**: `positions` 중 `exceeds_threshold`인 종목마다 1건. symbol은 `assets_by_id`에서 얻는다.
     - `level` 동일 규칙(`weight` 기준).
     - `code` = `f"SINGLE_NAME_CONCENTRATION:{symbol}"`, `label` = `f"{symbol} 단일 종목 쏠림"`.
     - `description` = 종목 비중·임계값 언급 한국어 문장.
   - **CASH_SHORTAGE**: `cash_weight` 기준 최대 1건.
     - `cash_weight < CASH_FLOOR_HIGH` → `"HIGH"`; 아니고 `cash_weight < CASH_FLOOR_MEDIUM` → `"MEDIUM"`; 그 외 미발생.
     - **단**, `total_value == 0`(보유·현금 모두 없음)이면 발생시키지 않는다(빈 포트폴리오는 노출 없음).
     - `code` = `"CASH_SHORTAGE"`, `label` = `"현금 비중 부족"`, `description` = 현금 비중 언급 한국어 문장.

4. **출력 순서(결정적)**: 그룹 순서 → 그룹 내 정렬.
   1. SECTOR_CONCENTRATION — `weight` 내림차순, 동률 `sector` 오름차순.
   2. SINGLE_NAME_CONCENTRATION — `weight` 내림차순, 동률 `symbol` 오름차순.
   3. CASH_SHORTAGE — 0/1건.

5. **반환 연결**: `_build_summary`가 `risk_exposures`를 채워 `PortfolioSummaryResponse`에 전달한다.
   `_calculate_weights` 반환을 확장하거나, `_build_summary`에서 이미 가진 sector_weights·positions·cash_weight·
   assets_by_id·threshold·total_value로 `_calculate_risk_exposures`를 호출해 산출한다(추가 시세 호출 금지).
   `check_concentration`은 `_build_summary` 재사용이라 자동 반영(별도 작업 없음).

## Implementation Scope

- `app/domains/portfolios/schema.py` — `RiskExposure` 추가, `PortfolioSummaryResponse`에 `risk_exposures` 추가.
- `app/domains/portfolios/service.py` — 판정 상수, `_calculate_risk_exposures` 헬퍼, `_build_summary` 연결.

## Out of Scope

- `aiBriefing`(정성 브리핑 — 후속 AI Briefing 작업).
- 의미 범주 분류(반도체/성장주/대형주) 하드코딩 — 도입 금지.
- 리스크 점수화·시계열 추세. FE 레포 변경(별도 트랙). DB 마이그레이션·모델 변경.
- 엔드포인트 시그니처/쿼리/인증 변경. 무관 파일 리팩터.

## Protected Files

`.codex/*`, `docs/designs/*`, `docs/harness/*`, `docs/decisions/*` 수정 금지(설계 문서는 작성됨, 참조만).

## Requirements

- 기존 summary 필드·동작 **완전 보존**(추가 필드뿐). 기존 테스트 약화 금지.
- `get_quote`는 호출당 최대 1회(기존과 동일). `_calculate_risk_exposures`는 외부 호출 없이 인메모리 계산만.
- 모든 비교·산술은 `Decimal`.

## Test Requirements

`tests/test_portfolios.py`에 risk exposures 케이스 추가(기존 market provider monkeypatch 패턴 재사용):
- 한 섹터가 임계 초과하도록 포지션 구성 → 해당 `SECTOR_CONCENTRATION` 노출 1건, `level` 임계×1.5 경계 단언.
- 단일 종목이 임계 초과 → `SINGLE_NAME_CONCENTRATION` 노출, `code`에 symbol 포함 단언.
- 현금 비중이 `CASH_FLOOR_HIGH` 미만/그 사이/이상 각각 → HIGH/MEDIUM/미발생 단언.
- 빈 포트폴리오(`total_value == 0`) → `risk_exposures == []`(현금 부족도 미발생) 단언.
- 출력 순서가 §Background 4의 결정적 순서와 일치 단언.
- **테스트 함수 파라미터에 타입 어노테이션 필수**(`monkeypatch: pytest.MonkeyPatch`). mypy `no-untyped-def` 통과해야 함.

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest -q
```

(세 가지 모두 필수 — mypy 누락 시 CI Typecheck 단계에서 실패한다.)

## Documentation Impact

- 설계 `docs/designs/049-portfolio-risk-exposures.md` 참조(Frozen).
- API spec에 portfolio summary 응답 예시가 있으면 `risk_exposures` 1줄 추가(선택).

## ADR Need

불요. 기존 계산값 파생·필드 추가, 신규 의존성/아키텍처 변경 없음.

## Failure Record Need

불요(국소 변경·회귀 테스트로 방지).

## Risk Level

Low. 외부 호출 불변, 추가 필드뿐. 임계 경계·빈 포트폴리오 현금 부족 가드가 주의점.

## Expected Output

- 전용 브랜치 `feat/portfolio-risk-exposures`(최신 `main` 기준)에서 구현.
- 위 2개 파일 + 테스트 변경 커밋(한국어 메시지).
- 검증(ruff/mypy/pytest) 전부 통과 로그.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
