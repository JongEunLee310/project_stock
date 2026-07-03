# 071 · LLM 데이터 파이프라인 5단계 — Feature Builder (PriceFeatureBuilder)

Status: Draft
작성: Claude Code (orchestrator)
관련: Epic BE #174(LLM 사전 데이터 수집·가공 파이프라인 v0.1), 구현 이슈 BE #185,
Milestone 데이터 수집 파이프라인 — 백엔드(#5). 기준 문서 `docs/knowledge/llm-data-pipeline.md`
(§5단계·§6.5). 선행 설계 `docs/designs/070-validator.md`(4단계 검증·Decision Q).

## 1. 배경

4단계까지 외부 데이터를 원본 저장→정규화→검증했다. 이제 LLM에 넣기 전에 계산 가능한 수치
지표를 만드는 계층이 필요하다. 지침 §6.5는 LLM이 해석할 수 있도록 수치 데이터를 요약 피처로
변환한다고 정의하고, §5단계는 초기 가격 피처 5종을 명시한다.

가격 bar는 이미 `StockPriceBar`(`stock_price_bars`)에 정규화·검증되어 저장돼 있고,
`PriceBarRepository.list_recent(symbol, market, interval, limit)`이 timestamp 오름차순으로
반환한다. 5단계는 이 시퀀스에서 가격 피처를 계산하는 `PriceFeatureBuilder`를 신규 도메인
`app/domains/features/`에 순수·무상태 컴포넌트로 신설한다. 소비 배선(어느 시점에 조회해 피처를
LLMContextBundle에 담을지)은 6단계 ContextBuilder의 몫이므로 이번 단계에는 포함하지 않는다.

## 2. 범위

포함:

- 신규 도메인 `app/domains/features/` 생성.
- `PriceFeatureSet` projection(`app/domains/features/schema.py`): 초기 가격 피처 5종을 담는
  경량 결과 타입. 각 피처는 `Decimal | None`.
- `PriceFeatureBuilder`(`app/domains/features/price_builder.py`, 순수·무상태):
  정규화된 가격 bar 시퀀스를 입력받아 `PriceFeatureSet`을 계산한다.
- 초기 가격 피처 5종: `return_1d`, `return_5d`, `return_20d`, `volume_vs_20d_avg`,
  `drawdown_from_52w_high`.
- 이력 부족·분모 0에 대한 graceful degradation(해당 피처 `None`).
- 빌더 단위 테스트.

비포함(후속 단계):

- `PortfolioFeatureBuilder`·`NewsFeatureBuilder` — 소비처·입력 계약(포트폴리오/뉴스 피처 예시)이
  확정되는 시점에 별도 단계로 분리. 이번 단계는 완료조건이 요구하는 가격 피처만 구현(YAGNI).
- 피처 조회·소비 배선(service/repository/job) — 6단계 ContextBuilder가 소유. 이번 단계는 순수
  빌더 + projection + 테스트만.
- 피처 영속 테이블·마이그레이션 — Decision V(4단계 Decision Q 계승). 단일 alembic head
  `c3d4e5f60058` 유지.
- Signal Detection Layer(§6.6), adjusted_close 기반 정교화, moving_average·volatility 등
  §6.5 확장 피처 예시.

## 3. 구성 요소

### 3.1 `PriceFeatureSet` projection (`app/domains/features/schema.py`)

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `return_1d` | `Decimal \| None` | 최근 종가 대비 직전 종가 수익률 |
| `return_5d` | `Decimal \| None` | 최근 종가 대비 5거래일 전 종가 수익률 |
| `return_20d` | `Decimal \| None` | 최근 종가 대비 20거래일 전 종가 수익률 |
| `volume_vs_20d_avg` | `Decimal \| None` | 최근 거래량 / 최근 20거래일 평균 거래량 |
| `drawdown_from_52w_high` | `Decimal \| None` | (최근 종가 − 52주 최고가) / 52주 최고가 |

DB·세션 비의존 경량 projection(Pydantic `BaseModel` 또는 frozen dataclass). 각 피처는 이력이
부족하면 `None`.

### 3.2 `PriceFeatureBuilder` (`app/domains/features/price_builder.py`, 순수)

| 시그니처 | 책임 |
| --- | --- |
| `build(bars: list[StockPriceBar]) -> PriceFeatureSet` | timestamp 오름차순 가격 bar 시퀀스에서 가격 피처 5종을 계산해 `PriceFeatureSet` 반환. 이력 부족·분모 0이면 해당 피처 `None` |

- 입력은 오름차순 정렬 가정. 방어적으로 `timestamp` 기준 재정렬한다.
- 계산 기준가는 `close_price`(수익률·드로다운 분자·기준), 52주 최고가는 `high_price`(Decision W).
- 윈도우 상수는 모듈 상수로 둔다(`_RETURN_WINDOWS`, `_VOLUME_AVG_WINDOW=20`,
  `_HIGH_WINDOW_52W=252`).

## 4. Decisions

- **R. 신규 features 도메인·순수 빌더만**: `app/domains/features/`에 `PriceFeatureBuilder`
  (순수·무상태)와 `PriceFeatureSet` projection만 둔다. 서비스·리포지토리·모델·job 변경 없음.
  소비 배선은 6단계 ContextBuilder. 지침 매핑 "Feature/Signal → domains/features/(신규)"를 따른다.
- **S. 빌더 범위 PriceFeatureBuilder만**: 지침 "필요 기능"은 3종 빌더를 나열하지만 완료조건·초기
  피처는 가격만 명시한다. `Portfolio`/`News` 빌더는 소비처·입력 계약 미확정이라 스텁을 만들지 않고
  별도 단계로 분리한다(YAGNI, 사용자 확인).
- **T. 입력·출력 계약**: 입력은 `list[StockPriceBar]`(timestamp 오름차순). 별도 입력 projection을
  신설하지 않고 저장 모델을 그대로 소비한다(현 소비처 부재, YAGNI). 출력은 `PriceFeatureSet`
  (각 피처 `Decimal | None`).
- **U. Graceful degradation**: 필요한 최소 bar 수(return_1d≥2, return_5d≥6, return_20d≥21,
  volume_vs_20d_avg≥20, drawdown_from_52w_high≥1)를 못 채우거나 분모가 0이면 해당 피처만 `None`.
  빌더는 예외를 던지지 않는다. 52주 최고가는 가용한 최근 최대 252 bar에서 계산한다.
- **V. 미영속**: 피처를 별도 테이블에 저장하지 않는다. 마이그레이션 미추가, 단일 head
  `c3d4e5f60058` 유지. 종목별 피처는 6단계 ContextBuilder가 소비 시점에 on-demand 계산한다
  (4단계 Decision Q 계승).
- **W. raw 가격 기준**: 수익률·드로다운은 `close_price`, 52주 최고가는 `high_price`를 쓴다.
  adjusted_close 기반 정교화는 후속(가격 모델에 adjusted_high가 없어 혼용을 피한다).

## 5. 마이그레이션

없음. 스키마 변경이 없다(Decision V). alembic 단일 head `c3d4e5f60058` 유지.

## 6. 테스트

- `PriceFeatureBuilder`: 충분한 이력(≥252 bar)에서 5종 피처 값이 기대 계산과 일치.
- 이력 부족: bar 수가 임계 미만이면 해당 피처 `None`(예: 1 bar → 모든 수익률·평균·드로다운
  경계 확인).
- 분모 0: 기준 종가·평균 거래량이 0이면 해당 피처 `None`.
- 정렬: 역순 입력도 재정렬 후 동일 결과.
- CI 3종(ruff + mypy + pytest) 통과. 신규 타입 주석 완전화(mypy).

## 7. ADR 판단

불필요. 신규 도메인에 순수 계산 컴포넌트를 추가하는 통상 작업이며, 1~4단계에서 합의한 순수/부수효과
분리·미영속·projection 네이밍 정책의 연장선이다. 소비 배선·품질 이력 표현은 6단계 ContextBuilder
설계 시 함께 확정한다.
