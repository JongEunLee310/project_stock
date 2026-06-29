# BE 확장: portfolio summary 리스크 노출(risk exposures)

상태: **계약 확정(Frozen)** — 2026-06-29(Opus). FE Portfolio 화면 riskExposures mock 제거 페어([[70-portfolio-risk-exposures-wiring]]).
FE Portfolio 화면의 "리스크 노출 분석" 카드가 `mockPortfolio.riskExposures`로 남아 있다.
summary 계산이 이미 섹터 비중·종목 비중·현금 비중을 산출하므로, 이 값들로 리스크 노출을 BE에서
파생한다. **구현은 §3 계약 확정을 정본으로 따른다.**

## 배경

`PortfolioSummaryResponse`는 `sector_weights`(섹터별 비중·임계 초과 여부), `positions`(종목별 비중·임계
초과 여부), `cash_weight`까지 이미 계산해 제공한다. 그러나 화면이 보여주는 "리스크 노출" 카드는 BE
응답에 없어 FE가 `mockPortfolio.riskExposures`(고정 4개 카드)로 유지하고 있다.

mock의 4개 카드(반도체 쏠림·대형주 의존·성장주 편중)는 섹터를 "반도체/성장주" 같은 **의미 범주**로
해석한 결과인데, BE에는 그 분류 데이터가 없다. 이 프로젝트의 기존 원칙(BE가 진실되게 계산할 수 있는
값만 노출, 출처 없는 값은 숨김 — ResearchPage catalysts·Portfolio aiBriefing 사례)에 따라 **임계값으로
판정 가능한 데이터 기반 규칙**으로만 리스크 노출을 산출한다. 의미 분류 하드코딩은 도입하지 않는다.

이미 계산된 summary 값에서 파생하므로 **추가 외부 호출이 없고**, 새 필드 추가일 뿐이라 마이그레이션·
인증 변경·신규 결정 없음 → ADR 불요.

## 1. 변경 범위

| Method · Path | 변경 |
| --- | --- |
| `GET /api/v1/portfolios/{id}/summary` | 응답에 `risk_exposures` 필드 추가 |
| `GET /api/v1/portfolios/{id}/check` | `summary`가 위 필드를 포함(파생 — 별도 작업 없음) |

엔드포인트 시그니처·쿼리·인증 변경 없음. 신규 엔드포인트 없음.

## 2. FE 매핑

FE는 `risk_exposures[]`를 "리스크 노출 분석" 카드 목록에 바인딩한다(현재 mock). `aiBriefing` mock은
이번 범위 밖으로 그대로 유지한다(후속 AI Briefing 작업). 빈 배열이면 FE는 빈 상태를 처리한다(§3.4).

## 3. 계약 확정 (2026-06-29, Opus — 정본)

와이어 컨벤션은 기존 portfolio summary와 동일: snake_case.

### 3.1 응답 스키마

`PortfolioSummaryResponse`에 필드 추가:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `risk_exposures` | `list[RiskExposure]` | 판정된 리스크 노출 목록. 없으면 빈 배열 |

신규 스키마 `RiskExposure`:

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `code` | `str` | 안정적 식별자(FE 키). 규칙+대상 조합(§3.2). 예: `SECTOR_CONCENTRATION:정보기술` |
| `label` | `str` | 한국어 카드 제목 |
| `level` | `str` | `"HIGH"` 또는 `"MEDIUM"` (FE가 높음/중간으로 매핑) |
| `description` | `str` | 한국어 설명 문장 |

기존 필드는 변경 없음. 추가 필드뿐이라 FE는 미반영 시 무시 가능(하위호환).

### 3.2 판정 규칙

모두 `_calculate_weights`가 이미 산출한 값(섹터 비중·종목 비중·현금 비중·임계값)에서 파생한다.
추가 시세 호출 없음. 판정 상수는 모듈 상단에 두어 조정 가능하게 한다.

판정 상수:

- `RISK_LEVEL_HIGH_MULTIPLIER = Decimal("1.5")` — 임계값의 1.5배 이상이면 HIGH, 그 미만 초과면 MEDIUM.
- `CASH_FLOOR_HIGH = Decimal("0.05")`, `CASH_FLOOR_MEDIUM = Decimal("0.15")` — 현금 비중 하한.

규칙 3종:

1. **SECTOR_CONCENTRATION** — `sector_weights` 중 `exceeds_threshold`인 섹터마다 1건.
   `sector == "UNKNOWN"`은 제외(의미 없는 분류).
   - `level`: `weight >= concentration_threshold * RISK_LEVEL_HIGH_MULTIPLIER`이면 HIGH, 아니면 MEDIUM.
   - `code`: `f"SECTOR_CONCENTRATION:{sector}"`.
   - `label`: `f"{sector} 섹터 쏠림"`.
   - `description`: 섹터 비중과 임계값을 언급하는 한국어 문장(정중·담백 톤).

2. **SINGLE_NAME_CONCENTRATION** — `positions` 중 `exceeds_threshold`인 종목마다 1건.
   종목 식별자(symbol)는 `assets_by_id`에서 얻는다.
   - `level`: `weight >= concentration_threshold * RISK_LEVEL_HIGH_MULTIPLIER`이면 HIGH, 아니면 MEDIUM.
   - `code`: `f"SINGLE_NAME_CONCENTRATION:{symbol}"`.
   - `label`: `f"{symbol} 단일 종목 쏠림"`.
   - `description`: 종목 비중과 임계값을 언급하는 한국어 문장.

3. **CASH_SHORTAGE** — `cash_weight` 기준 최대 1건.
   - `cash_weight < CASH_FLOOR_HIGH` → HIGH.
   - 아니고 `cash_weight < CASH_FLOOR_MEDIUM` → MEDIUM.
   - 그 외 → 미발생.
   - `code`: `"CASH_SHORTAGE"`.
   - `label`: `"현금 비중 부족"`.
   - `description`: 현금 비중을 언급하는 한국어 문장.

### 3.3 출력 순서(결정적)

테스트 안정성을 위해 결정적으로 정렬한다. 그룹 순서 → 그룹 내 정렬:

1. `SECTOR_CONCENTRATION` — `weight` 내림차순, 동률 시 `sector` 오름차순.
2. `SINGLE_NAME_CONCENTRATION` — `weight` 내림차순, 동률 시 `symbol` 오름차순.
3. `CASH_SHORTAGE` — 0건 또는 1건.

### 3.4 경계 동작

- 빈 포트폴리오(포지션 없음): 섹터·종목 노출 없음. `total_value == 0`이면 `cash_weight == 0`이라
  CASH_SHORTAGE가 HIGH로 잡힐 수 있으므로, `total_value == 0`(보유·현금 모두 없음)일 때는
  현금 부족도 발생시키지 않는다(노출 없음 = 빈 배열).
- quote 누락 포지션은 기존대로 `price=0` → market_value 0 → 임계 초과 아님(노출 없음).

## 4. 범위 밖

- `aiBriefing`(정성 브리핑·권고) — 후속 AI Briefing 작업.
- 의미 범주 분류(반도체/성장주/대형주 등) — BE 출처 없음, 도입하지 않음.
- 리스크 점수화·시계열 추세 — 이번엔 임계 기반 단발 판정만.
