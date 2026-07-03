# 070 · LLM 데이터 파이프라인 4단계 — Validator (뉴스 검증·DataQualityStatus)

Status: Draft
작성: Claude Code (orchestrator)
관련: Epic BE #174(LLM 사전 데이터 수집·가공 파이프라인 v0.1), 구현 이슈 BE #183,
Milestone 데이터 수집 파이프라인 — 백엔드(#5). 기준 문서 `docs/knowledge/llm-data-pipeline.md`
(§6.4·§11 4단계). 선행 설계 `docs/designs/068-raw-processing-status.md`(상태 컬럼),
`docs/designs/069-news-normalizer.md`(정규화 배선).

## 1. 배경

3단계에서 뉴스 정규화를 수집 잡에 배선하고 raw 행을 `normalized`로 전이시켰다. 그러나 정규화된
데이터가 신뢰 가능한지 검증하는 계층은 아직 없다. 가격 쪽에는 `prices/ingestion_service.py`의
`_validate_bars`가 인라인 검증(필수 필드·미래 시각 drop, 통화 불일치·이상치 warning)을 이미
하지만, 뉴스에는 대응 검증이 없고 검증 결과를 표현하는 공용 어휘도 없다.

지침 §6.4는 정규화된 데이터의 검증 항목(필수 필드, 음수 가격, high>=low, 미래 시각, 중복,
오래된 데이터, symbol universe 존재)과 검증 결과 어휘(`valid`/`invalid`/`stale`/`duplicate`/
`low_trust`)를 정의한다. 4단계는 이 어휘를 도입하고, 뉴스 Validator를 신설하며, 가격 검증을
같은 어휘로 정합시킨다. 검증 실패 raw 행은 `processing_status='failed'`로 전이시켜(2단계 컬럼의
첫 failed writer) 재처리·역추적이 가능하게 한다.

## 2. 범위

포함:

- `DataQualityStatus`·`ValidationErrorReason` enum 신설(`app/domains/ingestion/schema.py`,
  `ProcessingStatus`와 공용 경계 어휘). 기존 enum 정의는 변경하지 않고 추가만 한다.
- `NewsValidator` 신설(`app/domains/news/validator.py`, 순수·무상태): 필수 필드 존재,
  `published_at` 미래 시각 아님, stale(오래된 데이터) 판정.
- `PriceValidator` 신설(`app/domains/prices/validator.py`): 기존 `_validate_bars` 판정 로직을
  behavior-preserving 추출하고 공유 `DataQualityStatus`/`ValidationErrorReason` 어휘로 표기.
- `NewsNormalizationService`에 `NewsValidator` 배선: INVALID 판정 시 raw 행
  `processing_status='failed'` 전이 + `NewsItem` 미생성. STALE/LOW_TRUST는 `NewsItem` 생성 유지.
- `RawNewsEventRepository.mark_failed` 추가(`mark_normalized`와 대칭).
- 검증 단위 테스트, 수집 잡 배선(failed 전이) 테스트, 가격 추출 behavior-preserving 테스트.

비포함(후속 단계):

- `DataQualityStatus`의 `NewsItem`/`PriceBar` 컬럼 영속화·마이그레이션 — Decision Q(안 A).
  종목별 품질 이력은 6단계 ContextBuilder `data_quality` 섹션에서 재구성.
- 가격 raw 행 status 전이(`normalized`/`failed`) — 3단계에서도 price는 미배선, 유지.
- 분석 플로우 `analysis/service.py._create_new_items` 수렴 — 069 Decision K 유지.
- symbol universe 존재 검증 — 정규화 단계 asset 해소가 이미 소유(069 Decision J).
- Feature Builder(5단계)·ContextBuilder(6단계)·LLM Gateway(7단계).

## 3. 구성 요소

### 3.1 검증 어휘 (`app/domains/ingestion/schema.py`)

| enum | 값 | 설명 |
| --- | --- | --- |
| `DataQualityStatus(str, Enum)` | `VALID`/`INVALID`/`STALE`/`DUPLICATE`/`LOW_TRUST` | 검증 결과 상태(지침 §6.4 어휘) |
| `ValidationErrorReason(str, Enum)` | `MISSING_REQUIRED_FIELD`/`FUTURE_TIMESTAMP`/`STALE`/`NEGATIVE_PRICE`/`HIGH_LOW_INVERTED`/`CURRENCY_MISMATCH`/`OUTLIER_RETURN` | 검증 실패·경고 사유 |

`ProcessingStatus`(raw 행의 파이프라인 진행 상태)와 `DataQualityStatus`(정규화 산출물의 품질
판정)는 축이 다르다. 전자는 raw 행에 영속되고, 후자는 이번 단계에서 Validator 반환값·텔레메트리로만
쓴다(Decision Q).

### 3.2 `NewsValidator` (`app/domains/news/validator.py`, 순수)

| 시그니처 | 책임 |
| --- | --- |
| `validate(data: NewsItemCreate, *, now: datetime) -> ValidationOutcome` | 정규화된 뉴스 projection의 품질 판정. 필수 필드(title/url/source) 존재, `published_at` 미래 시각(INVALID), stale 임계 초과(STALE) 검사 후 `DataQualityStatus`와 사유 목록 반환 |

- `ValidationOutcome`: `DataQualityStatus` + `list[ValidationErrorReason]`을 담는 경량
  projection(frozen dataclass 또는 Pydantic). DB·세션 비의존.
- stale 임계는 모듈 상수(`_STALE_AFTER_DAYS`)로 두고 보수적으로 설정한다. STALE은 품질 저하일
  뿐 거부가 아니다.
- 중복(DUPLICATE)은 정규화 단계 URL canonical dedup이 이미 소유하므로 enum에는 유지하되
  NewsValidator가 능동 판정하지 않는다(Decision O).

### 3.3 `PriceValidator` (`app/domains/prices/validator.py`, 순수)

| 시그니처 | 책임 |
| --- | --- |
| `validate_bars(bars, symbol, market) -> PriceValidationResult` | 기존 `_validate_bars` 판정을 옮긴다. 필수 OHLC 누락·미래 시각 bar drop, 통화 불일치·이상치(초과 수익률) warning. 결과를 `valid_bars`와 `DataQualityStatus`/사유로 표기 |

- `_OUTLIER_THRESHOLD`·`_EXPECTED_CURRENCY_BY_MARKET`·`_has_missing_required_price` 등 판정
  상수·헬퍼를 함께 이관한다. drop/warn 판정과 카운트는 기존과 동일(behavior-preserving).
- `PriceIngestionService._collect_target`은 이 Validator에 위임하고, 기존 `dropped_count`/
  `warning_count` 집계 의미를 유지한다.

### 3.4 서비스 배선

- `NewsNormalizationService.normalize_event`: asset 해소(069 Decision J) 후 `NewsValidator`를
  실행한다. INVALID면 `raw_news_repo.mark_failed(event.id)` 호출 + `NewsItem` 미생성·반환 None.
  VALID/STALE/LOW_TRUST면 기존대로 URL dedup 확인 후 `NewsItem` 생성·`mark_normalized`.
- `RawNewsEventRepository.mark_failed(event_id)`: `processing_status='failed'` 전이·commit·
  refresh. `mark_normalized`와 대칭.

## 4. Decisions

- **L. 검증 어휘 공용 위치**: `DataQualityStatus`·`ValidationErrorReason`는 `ingestion/schema.py`에
  `ProcessingStatus`와 함께 둔다(가격·뉴스 공용 경계 어휘). 도메인별 Validator는 각 도메인
  (`prices/validator.py`·`news/validator.py`)에 둔다(지침 매핑 "Validation → 도메인 내부").
- **M. 순수/부수효과 분리**: Validator는 순수·무상태(입력→판정). raw 행 `failed` 전이·`NewsItem`
  skip 같은 부수효과는 service에 응집한다(069 Decision H 연장).
- **N. 뉴스 실패 정책**: `published_at` 미래·필수 필드 누락 등 INVALID는 raw 행 `failed` 전이
  (첫 failed writer) + `NewsItem` 미생성. STALE/LOW_TRUST는 품질 저하로 보되 `NewsItem`은
  생성(normalized 유지)해 소비처(6단계 data_quality)가 재판단하게 한다. asset 미해소는 069
  Decision J대로 `fetched` 유지(검증 이전 단계라 failed 아님).
- **O. 중복은 검증 이전에 이미 처리**: URL canonical dedup이 정규화 단계에서 처리되므로
  `DataQualityStatus.DUPLICATE`는 enum에 유지하되 NewsValidator 능동 판정 대상이 아니다.
- **P. 가격 검증 behavior-preserving 추출**: `_validate_bars`를 `PriceValidator`로 추출하되
  drop/warn 판정·카운트는 동일. 가격 raw 행 status 전이는 이번 범위 밖(3단계에서도 미배선).
  PriceValidator는 공유 어휘로 결과를 표기해 뉴스 검증과 정합한다.
- **Q. 상태 컬럼 미신설**: `DataQualityStatus`를 `NewsItem`/`PriceBar`에 영속하지 않는다.
  마이그레이션 미추가, 단일 head `c3d4e5f60058` 유지. 종목별 품질 이력은 6단계 ContextBuilder
  `data_quality`에서 재구성한다.

## 5. 마이그레이션

없음. 스키마 변경이 없다(Decision Q). alembic 단일 head `c3d4e5f60058` 유지.

## 6. 테스트

- `NewsValidator`: 필수 필드 누락→INVALID, `published_at` 미래→INVALID(사유 FUTURE_TIMESTAMP),
  임계 초과 오래된 뉴스→STALE, 정상→VALID.
- `NewsNormalizationService`: INVALID 뉴스는 raw 행 `failed` 전이 + `NewsItem` 미생성,
  VALID/STALE는 `NewsItem` 생성 + raw 행 `normalized`.
- `PriceValidator`: 기존 `_validate_bars` 케이스(누락·미래 drop, 통화 불일치·이상치 warn)가
  동일 카운트로 재현(behavior-preserving).
- `PriceIngestionService`: 추출 후 수집 결과(dropped/warning 카운트) 불변.
- CI 3종(ruff + mypy + pytest) 통과. 신규 타입 주석 완전화(mypy).

## 7. ADR 판단

불필요. 기존 검증 로직을 컴포넌트로 추출하고 뉴스 검증을 신설하는 통상 작업이며, 1·2·3단계에서
합의한 enum 재사용·순수/부수효과 분리·상태 컬럼 정책의 연장선이다. Decision Q(상태 컬럼 미신설)는
사용자 승인 결정이고, 6단계 ContextBuilder 설계 시 품질 이력 소비 방식과 함께 재검토한다.
