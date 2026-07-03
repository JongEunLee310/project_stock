# Codex Handoff Task

## Source Issue

BE #183 (Epic BE #174 4단계). 설계 `docs/designs/070-validator.md`. 기준 문서
`docs/knowledge/llm-data-pipeline.md` §6.4·§11(4단계).

## Task Summary

LLM 데이터 파이프라인 4단계. 정규화된 데이터의 품질을 검증하는 Validator를 신설한다. 공용
검증 어휘(`DataQualityStatus`/`ValidationErrorReason`)를 도입하고, `NewsValidator`를 신설해
뉴스 수집 잡에 배선하며, 기존 가격 인라인 검증을 `PriceValidator`로 behavior-preserving 추출한다.

## Goal

- `app/domains/ingestion/schema.py`에 `DataQualityStatus`·`ValidationErrorReason` enum이
  존재한다(기존 `ProcessingStatus`·`RawProviderResponse` 정의는 불변).
- `NewsValidator`(순수·무상태)가 필수 필드·미래 시각·stale을 판정한다.
- `PriceValidator`가 기존 `_validate_bars` 판정을 동일하게 수행한다(drop/warn 카운트 불변).
- 뉴스 수집 경로에서 검증 INVALID인 raw 행이 `processing_status='failed'`로 전이되고 해당
  `NewsItem`은 생성되지 않는다. VALID/STALE은 기존대로 `NewsItem` 생성 + `normalized` 전이.
- CI 3종(ruff + mypy + pytest) 통과, alembic 단일 head `c3d4e5f60058` 유지(마이그레이션 없음).

## Background

- 3단계(PR #182, 설계 069)에서 뉴스 정규화를 수집 잡에 배선하고 raw 행을 `normalized`로
  전이시켰다. `processing_status='failed'`는 아직 어떤 writer도 쓰지 않는다 — 이번 단계가 첫
  failed writer다.
- 가격 검증은 `app/domains/prices/ingestion_service.py._validate_bars`에 인라인 존재한다(필수
  OHLC 누락·미래 시각 bar drop, 통화 불일치·이상치 warning). 이 판정을 그대로 옮긴다.
- `ProcessingStatus`(raw 행 진행 상태)와 `DataQualityStatus`(정규화 산출물 품질)는 축이 다르다.
  이번 단계는 후자를 영속하지 않고 Validator 반환값·텔레메트리로만 쓴다(설계 Decision Q, 사용자
  승인 안 A).
- 참조 메서드: `NewsItemRepository.exists_by_url`/`create`, `AssetRepository.get_by_symbol_market`,
  `RawNewsEventRepository.mark_normalized`(대칭으로 `mark_failed` 추가).

## Implementation Scope

신규:

- `app/domains/ingestion/schema.py`: `DataQualityStatus(str, Enum)`(`VALID`/`INVALID`/`STALE`/
  `DUPLICATE`/`LOW_TRUST`), `ValidationErrorReason(str, Enum)`(`MISSING_REQUIRED_FIELD`/
  `FUTURE_TIMESTAMP`/`STALE`/`NEGATIVE_PRICE`/`HIGH_LOW_INVERTED`/`CURRENCY_MISMATCH`/
  `OUTLIER_RETURN`) 추가. 기존 정의는 수정 금지.
- `app/domains/news/validator.py`: `NewsValidator`(순수). `validate(data, *, now)`가 필수
  필드(title/url/source) 존재, `published_at` 미래→INVALID, stale 임계 초과→STALE 판정 후
  `DataQualityStatus` + 사유 목록을 담은 경량 결과(frozen dataclass 또는 Pydantic)를 반환.
  stale 임계는 모듈 상수(`_STALE_AFTER_DAYS`)로 보수적으로 둔다.
- `app/domains/prices/validator.py`: `PriceValidator`. `_validate_bars`의 판정·상수
  (`_OUTLIER_THRESHOLD`·`_EXPECTED_CURRENCY_BY_MARKET`·`_has_missing_required_price`)를 이관하고
  drop/warn 판정·카운트를 동일하게 유지. 공유 `DataQualityStatus`/사유 어휘로 표기.

수정:

- `app/domains/raw_news/repository.py`: `mark_failed(event_id)` 추가(`mark_normalized`와 대칭,
  `processing_status='failed'` 전이·commit·refresh).
- `app/domains/news/normalization_service.py`: asset 해소 후 `NewsValidator` 실행. INVALID면
  `mark_failed` + `NewsItem` 미생성·None 반환. VALID/STALE/LOW_TRUST면 기존 URL dedup·생성·
  `mark_normalized` 흐름 유지.
- `app/domains/prices/ingestion_service.py`: `_validate_bars` 인라인 대신 `PriceValidator`에
  위임. 수집 결과(`dropped_bar_count`/`warning_count`) 의미·카운트 불변.

## Out of Scope

- `DataQualityStatus`의 `NewsItem`/`PriceBar` 컬럼 영속화, 신규 alembic revision(Decision Q).
- 가격 raw 행 `processing_status` 전이(`normalized`/`failed`) — price는 미배선 유지.
- 분석 플로우 `app/domains/analysis/service.py` 수렴(069 Decision K).
- symbol universe 존재 검증 신설(정규화 asset 해소가 이미 소유).
- Feature Builder(5단계)·ContextBuilder(6단계)·LLM Gateway(7단계), LLM 파생 필드.
- `ProcessingStatus`/`RawProviderResponse`/`RawDataType` 기존 정의 변경.

## Protected Files

- `app/domains/analysis/*` — 069 Decision K, 손대지 않는다.
- `app/domains/ingestion/schema.py` — enum **추가만** 허용, 기존 정의 수정 금지.
- `app/domains/llm_context/*`·`app/domains/llm_analysis/*`·`app/domains/decision_logs/*`·
  `app/adapters/llm/*`·`app/domains/raw_prices/*` — 변경 금지.
- `alembic/versions/*` — 신규 revision 금지.

## Requirements

- Validator는 DB·세션 비의존 순수 컴포넌트. 부수효과(raw 행 전이·NewsItem skip)는 service에만 둔다.
- 뉴스 INVALID 판정 시에만 `failed` 전이. asset 미해소는 `fetched` 유지(069 Decision J).
- 가격 추출은 behavior-preserving. 기존 테스트가 수정 없이 통과해야 한다(불가피한 경우 최소 조정).
- 타입 주석 완전화(mypy `no-untyped-def` 회피).

## Test Requirements

- `tests/test_news_validator.py`(신규): 필수 필드 누락→INVALID, 미래 published_at→INVALID
  (사유 FUTURE_TIMESTAMP), 임계 초과→STALE, 정상→VALID.
- `tests/test_news_ingestion.py`(수정): INVALID 뉴스→raw 행 `failed` + NewsItem 미생성,
  VALID→NewsItem 생성 + `normalized`.
- `tests/test_price_ingestion.py` 또는 `tests/test_price_validator.py`: PriceValidator
  behavior-preserving(누락·미래 drop, 통화·이상치 warn 카운트 동일).

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`
- `uv run alembic heads`  # 단일 head c3d4e5f60058 확인(마이그레이션 없음)

## Documentation Impact

설계 `docs/designs/070-validator.md`·본 핸드오프가 같은 PR에 포함된다. 지침서 §11 4단계 서술의
완료 갱신은 Epic 마무리 시점에 함께 한다(지금 별도 갱신 불필요).

## ADR Need

불필요. 검증 로직 추출·뉴스 검증 신설로, 1·2·3단계 합의(enum 재사용·순수/부수효과 분리·상태
컬럼 정책)의 연장선이다. Decision Q는 6단계 ContextBuilder 설계 시 재검토한다.

## Failure Record Need

불필요. 신규 기능 구현이며 알려진 실패 패턴 대응이 아니다.

## Risk Level

Medium. 첫 `failed` writer 도입과 가격 검증 추출이 기존 수집 잡 동작에 영향을 줄 수 있어,
behavior-preserving 확인과 failed/normalized 전이 경계 테스트가 관건이다.

## Expected Output

신규 3개 파일 + 수정 3개 파일 + 테스트. 검증 명령 4종 결과와 함께 요약.
