# LLM 사전 데이터 수집 및 가공 파이프라인 지침서

## 1. 문서 목적

이 문서는 자동화 투자 프로젝트에서 **LLM에게 데이터를 전달하기 전 백엔드가 수행해야 하는 데이터 수집, 정규화, 검증, 가공, 컨텍스트 생성 파이프라인**의 전체 지침을 정의한다.

이 프로젝트에서 LLM은 원본 데이터를 직접 조회하거나 외부 API를 직접 호출하지 않는다.
LLM은 백엔드가 정리한 `LLMContextBundle`을 입력으로 받아 투자 판단 보조, 리스크 점검, 뉴스 요약, 포트폴리오 리뷰를 수행한다.

핵심 목표는 다음과 같다.

```text
외부 데이터 → 원본 저장 → 정규화 → 검증 → 피처 생성 → ContextBundle 생성 → LLM 호출
```

이 문서는 Claude Code가 구현 작업을 수행할 때 전체 그림을 잃지 않도록 하기 위한 기준 문서다.

---

## 2. 프로젝트 철학

이 시스템의 1차 목표는 자동매매가 아니다.

목표는 다음과 같다.

1. 관심 종목과 보유 종목을 자동 감시한다.
2. 뉴스, 가격, 공시, 포트폴리오 상태를 정리한다.
3. 사용자의 충동 매수를 방지한다.
4. 리스크, 반대 시나리오, 주의할 점을 명확히 드러낸다.
5. 최종 투자 판단은 사용자가 내릴 수 있도록 돕는다.

따라서 LLM 출력은 “매수하라”, “매도하라” 같은 명령형 판단이 아니라 다음 형태여야 한다.

```text
- 현재 상황 요약
- 주요 리스크
- 추가 확인할 점
- 사용자의 기존 규칙 위반 여부
- 보수적인 검토 의견
- 데이터 부족 여부
```

---

## 3. 핵심 설계 원칙

## 3.1 LLM은 외부 API를 직접 호출하지 않는다

금지 구조:

```text
LLMService → News API 직접 호출
LLMService → Price API 직접 호출
LLMService → Broker API 직접 호출
```

허용 구조:

```text
IngestionService
  → RawStore
  → NormalizationService
  → ValidationService
  → FeatureBuilder
  → ContextBuilder
  → LLMGateway
```

LLM은 오직 `ContextBuilder`가 생성한 입력만 사용한다.

---

## 3.2 원본 데이터와 정규화 데이터를 분리한다

외부 API 응답은 반드시 원본 상태로 저장한다.

원본 저장의 목적:

1. 재처리 가능
2. 디버깅 가능
3. 중복 수집 방지
4. 특정 LLM 판단이 어떤 데이터를 근거로 했는지 추적 가능
5. 외부 API 형식 변경에 대한 대응

예시:

```text
raw_provider_responses
raw_market_prices
raw_news_articles
raw_filings
```

---

## 3.3 내부 도메인 모델은 외부 API 형식에 오염되지 않아야 한다

외부 데이터 공급자의 필드명, 응답 구조, 특이한 날짜 형식, 심볼 표기 방식이 내부 도메인 전체로 퍼지면 안 된다.

모든 외부 응답은 내부 표준 DTO로 변환한다.

예시:

```text
ExternalNewsResponse → RawNewsArticle → NewsArticle
ExternalPriceResponse → RawPriceData → PriceDaily
```

---

## 3.4 계산은 백엔드가 하고, 해석은 LLM이 한다

LLM에게 가격 시계열 전체를 던지고 수익률, 이동평균, 변동성을 계산하게 만들면 안 된다.

백엔드가 계산해야 하는 것:

```text
- 1일, 5일, 20일 수익률
- 20일, 60일 이동평균
- 52주 고점 대비 하락률
- 거래량 평균 대비 증가율
- 포트폴리오 비중
- 단일 종목 집중도
- 최근 뉴스 빈도
- 부정적 이벤트 발생 여부
```

LLM이 맡을 일:

```text
- 계산된 지표의 의미 해석
- 리스크 설명
- 사용자 규칙과 비교
- 반대 시나리오 제시
- 데이터 부족 여부 설명
```

---

## 3.5 LLM 입력은 항상 추적 가능해야 한다

LLM 호출 시 다음을 반드시 저장한다.

```text
- analysis_run_id
- task_type
- input_context_json
- model_name
- prompt_version
- output_json
- created_at
- related_symbols
- related_decision_log_id
```

LLM 판단 결과만 저장하면 안 된다.
어떤 입력을 보고 그런 결과가 나왔는지 반드시 재현 가능해야 한다.

---

## 4. 전체 파이프라인 구조

```text
[External Data Providers]
  ↓
[Ingestion Layer]
  ↓
[Raw Data Store]
  ↓
[Normalization Layer]
  ↓
[Validation Layer]
  ↓
[Feature Engineering Layer]
  ↓
[Signal Detection Layer]
  ↓
[Context Builder]
  ↓
[LLM Gateway]
  ↓
[Analysis Result Store]
  ↓
[Decision Log / Alert / Frontend API]
```

---

## 5. 주요 데이터 종류

초기 버전에서 다룰 데이터는 다음과 같다.

## 5.1 Watchlist

사용자가 감시하고 싶은 종목 목록.

필요 필드 예시:

```text
- id
- user_id
- symbol
- market
- display_name
- memo
- created_at
- is_active
```

---

## 5.2 PortfolioPosition

사용자의 보유 종목 정보.

초기에는 수동 입력을 기준으로 한다.
이후 증권사 API 연동을 고려한다.

필요 필드 예시:

```text
- id
- user_id
- symbol
- market
- quantity
- average_price
- currency
- current_price
- market_value
- weight
- unrealized_gain_loss
- updated_at
```

---

## 5.3 PriceDaily

일봉 가격 데이터.

필요 필드 예시:

```text
- id
- symbol
- market
- trade_date
- open
- high
- low
- close
- adjusted_close
- volume
- source
- created_at
```

초기에는 일봉 중심으로 구현한다.
분봉 데이터는 v0.2 이후 또는 별도 이슈로 분리한다.

---

## 5.4 NewsArticle

뉴스 데이터.

필요 필드 예시:

```text
- id
- symbol
- market
- title
- summary
- source
- url
- published_at
- language
- raw_content_ref
- content_hash
- trust_level
- created_at
```

뉴스 전문을 항상 LLM에게 넘기지 않는다.
기본은 제목, 요약, 출처, 발행 시각 중심으로 넘긴다.

---

## 5.5 Filing

공시와 실적 관련 데이터.

초기 버전에서는 스키마만 준비하고 실제 수집은 v0.2 이후로 미룰 수 있다.

필요 필드 예시:

```text
- id
- symbol
- market
- filing_type
- title
- source
- url
- published_at
- summary
- raw_content_ref
- created_at
```

---

## 5.6 DecisionLog

사용자가 과거에 내린 투자 관련 판단 기록.

필요 필드 예시:

```text
- id
- user_id
- symbol
- decision_type
- reason
- expected_scenario
- risk_notes
- created_at
- related_analysis_run_id
```

예시 decision_type:

```text
- watch
- buy_watch
- hold
- trim_watch
- avoid
- need_more_data
```

---

## 6. 레이어별 책임

## 6.1 Ingestion Layer

외부 API 또는 파일에서 데이터를 가져오는 계층이다.

책임:

```text
- 외부 API 호출
- 응답 원본 저장
- 수집 시각 기록
- source 기록
- payload_hash 생성
- 중복 원본 응답 방지
```

금지:

```text
- 이 계층에서 투자 판단을 하지 않는다.
- 이 계층에서 LLM 입력을 만들지 않는다.
- 이 계층에서 복잡한 도메인 해석을 하지 않는다.
```

인터페이스 예시(이 프로젝트 관례 — 외부 fetch는 `app/adapters/`의 adapter, 원본 저장과 대상
순회는 도메인 `ingestion_service`가 맡고, 둘 다 동기 함수다):

```python
# app/adapters/market/base.py — 외부 API 경계
class MarketAdapter:
    def get_daily_bars(self, symbol: str, market: str) -> list[PriceBarResult]:
        ...
```

```python
# app/domains/prices/ingestion_service.py — 원본 저장 + 검증 + 정규화 적재
class PriceIngestionService:
    def collect_and_save(
        self, provider: MarketAdapter, targets: list[tuple[str, str]]
    ) -> IngestionResult:
        ...
```

---

## 6.2 Raw Store

외부 응답을 원본 그대로 저장하는 계층이다.

책임:

```text
- raw payload 저장
- provider 이름 저장
- fetched_at 저장
- payload_hash 저장
- 처리 상태 저장
```

처리 상태 예시:

```text
- fetched
- normalized
- failed
- skipped_duplicate
```

---

## 6.3 Normalization Layer

Raw 데이터를 내부 표준 모델로 변환한다.

책임:

```text
- 외부 필드명을 내부 필드명으로 변환
- 날짜, 시간대 정규화
- 통화 단위 정규화
- 심볼 표기 통일
- 중복 뉴스 병합
- URL canonicalization
```

예시:

```text
AAPL.O, AAPL, NASDAQ:AAPL → AAPL / US
005930.KS, 삼성전자 → 005930 / KR
```

---

## 6.4 Validation Layer

정규화된 데이터가 신뢰 가능한지 검증한다.

검증 항목:

```text
- 필수 필드 존재 여부
- 가격 데이터의 음수 여부
- high >= low 검증
- close가 open/high/low 범위와 심하게 충돌하지 않는지 검증
- published_at이 미래 시각이 아닌지 검증
- 중복 뉴스 여부
- 오래된 데이터 여부
- symbol이 watchlist 또는 known stock universe에 존재하는지 검증
```

검증 결과는 명시적으로 남긴다.

```text
valid
invalid
stale
duplicate
low_trust
```

---

## 6.5 Feature Engineering Layer

LLM이 해석할 수 있도록 수치 데이터를 요약 피처로 변환한다.

가격 피처 예시:

```text
- return_1d
- return_5d
- return_20d
- moving_average_20d
- moving_average_60d
- distance_from_ma20
- distance_from_ma60
- volume_vs_20d_avg
- drawdown_from_52w_high
- volatility_20d
```

포트폴리오 피처 예시:

```text
- position_weight
- unrealized_return
- concentration_risk
- cash_ratio
- sector_exposure
```

뉴스 피처 예시:

```text
- recent_news_count_24h
- recent_news_count_7d
- negative_news_count
- major_event_detected
- duplicated_news_count
```

---

## 6.6 Signal Detection Layer

정량적 조건에 따라 이벤트를 감지한다.

예시 시그널:

```text
- price_spike
- price_drop
- volume_spike
- near_52w_high
- sharp_drawdown
- news_burst
- earnings_event
- portfolio_overweight
- user_rule_violation
```

시그널은 LLM 호출 여부를 결정하는 데 사용할 수 있다.

단, 시그널은 투자 판단이 아니다.
시그널은 “분석이 필요한 상황”을 알리는 표시다.

---

## 6.7 Context Builder

LLM 직전의 가장 중요한 계층이다.

책임:

```text
- 가격 피처 수집
- 뉴스 요약 수집
- 포트폴리오 상태 수집
- 사용자 규칙 수집
- 과거 decision-log 수집
- 데이터 신뢰도 상태 포함
- LLM task_type에 맞는 ContextBundle 생성
```

Context Builder는 LLM에게 넘길 데이터의 양과 품질을 통제한다.

금지:

```text
- 원본 뉴스 전문을 무제한으로 넣지 않는다.
- 가격 시계열 전체를 무제한으로 넣지 않는다.
- 오래된 데이터를 최신 데이터처럼 넣지 않는다.
- 출처 없는 루머를 일반 뉴스처럼 넣지 않는다.
```

---

## 6.8 LLM Gateway

LLM Provider와 통신하는 계층이다.

책임:

```text
- ContextBundle을 프롬프트 또는 JSON 입력으로 변환
- output schema 강제
- provider별 응답 차이 흡수
- timeout, retry, rate limit 처리
- input/output 저장
```

금지:

```text
- 외부 시장 데이터 API 호출 금지
- 비즈니스 로직 직접 수행 금지
- 데이터 정규화 수행 금지
```

---

## 7. LLMContextBundle 표준 구조

LLM에게 전달하는 입력은 반드시 `LLMContextBundle` 구조를 사용한다.

예시:

```json
{
  "task_type": "symbol_risk_review",
  "as_of": "2026-07-02T18:00:00+09:00",
  "user_intent": "관심 종목의 리스크를 점검하고 충동 매수를 방지한다.",
  "symbols": ["NVDA"],
  "data_quality": {
    "price_data_status": "valid",
    "news_data_status": "valid",
    "portfolio_data_status": "valid",
    "warnings": []
  },
  "symbol_cards": [
    {
      "symbol": "NVDA",
      "market": "US",
      "display_name": "NVIDIA Corp.",
      "price_snapshot": {
        "close": 153.2,
        "return_1d": -1.2,
        "return_5d": 4.8,
        "return_20d": 12.5,
        "drawdown_from_52w_high": -6.3,
        "volume_vs_20d_avg": 1.8
      },
      "portfolio_context": {
        "holding": true,
        "weight": 18.5,
        "avg_buy_price": 121.4,
        "unrealized_return": 26.2
      },
      "recent_news": [
        {
          "title": "Example news title",
          "summary": "Short normalized summary",
          "source": "Example Source",
          "published_at": "2026-07-02T09:00:00+09:00",
          "trust_level": "high"
        }
      ],
      "signals": [
        {
          "type": "volume_spike",
          "severity": "medium",
          "reason": "거래량이 20일 평균 대비 1.8배입니다."
        }
      ]
    }
  ],
  "portfolio_summary": {
    "cash_ratio": 22.0,
    "top_holding_weight": 18.5,
    "concentration_risk": "medium"
  },
  "user_rules": [
    "단일 종목 비중 20% 초과 금지",
    "5일 수익률 15% 이상 급등 시 추격 매수 금지",
    "실적 발표 직전 신규 매수 금지"
  ],
  "recent_decisions": [
    {
      "symbol": "NVDA",
      "decision_type": "hold",
      "reason": "이미 목표 비중에 근접하여 신규 매수는 보류",
      "created_at": "2026-06-28T21:00:00+09:00"
    }
  ],
  "output_contract": {
    "format": "json",
    "required_fields": [
      "summary",
      "risk_level",
      "suggested_action",
      "reasons",
      "watch_points",
      "counter_arguments",
      "data_limitations",
      "confidence"
    ]
  }
}
```

---

## 8. LLM 출력 표준 구조

LLM 응답은 자유 텍스트가 아니라 JSON Schema 기반으로 받아야 한다.

예시:

```json
{
  "summary": "현재 보유 비중은 유지 가능하나 단기 과열 신호가 있습니다.",
  "risk_level": "medium",
  "suggested_action": "hold",
  "reasons": [
    "20일 수익률이 높습니다.",
    "거래량이 평균 대비 증가했습니다.",
    "단일 종목 비중이 내부 제한에 근접했습니다."
  ],
  "watch_points": [
    "다음 실적 발표 일정",
    "거래량 증가 지속 여부",
    "섹터 조정 가능성"
  ],
  "counter_arguments": [
    "실적 성장률이 유지된다면 추가 상승 가능성도 있습니다."
  ],
  "data_limitations": [
    "공시 데이터가 아직 포함되지 않았습니다."
  ],
  "confidence": 0.72
}
```

`suggested_action`은 enum으로 제한한다.

```text
- buy_watch
- hold
- trim_watch
- avoid
- need_more_data
```

주의:

```text
buy
sell
strong_buy
strong_sell
```

위와 같은 직접 매수, 매도 명령형 enum은 사용하지 않는다.

---

## 9. 패키지 구조

이 프로젝트는 레이어별 top-level 패키지(`services/ingestion`, `services/normalization` 등)가
아니라 **도메인 응집형** 레이아웃을 쓴다. 도메인 하나가 `model` / `schema` / `service` /
`repository`(+ 필요 시 `ingestion_service` / `universe`)를 함께 묶고, 외부 provider 연동은
`app/adapters/`로, 백그라운드 잡은 `app/worker/jobs/`로 분리한다. 지침의 파이프라인 레이어는
아래 구조 안의 모듈로 매핑된다(`신규` = 이 지침으로 새로 추가할 대상).

```text
app/
  main.py

  api/
    v1/
      router.py
      deps.py
      endpoints/                 # route는 얇게 — Application Service 호출만
        prices.py  market.py  watchlists.py  portfolios.py
        reports.py  signals.py  theses.py  assets.py
        alerts.py  alert_candidates.py  decision_logs.py
        dashboard.py  job_runs.py  worker.py  health.py  auth.py
        # 신규: llm_analysis.py (분석 실행/결과 조회)

  adapters/                      # Ingestion Layer의 fetch 계층 (외부 API 경계)
    factory.py
    market/    { base.py, mock.py, yfinance }
    news/      { base.py, mock.py, rss.py }
    disclosure/  portfolio/
    llm/       { base.py, gateway.py, router.py, privacy.py, mock.py, ... }  # LLM Gateway

  domains/
    # --- Raw Store (원본 저장, 기존) ---
    raw_prices/    { model, schema, service, repository }        # payload_hash dedup
    raw_news/      { model, schema, service, repository, ingestion_service, universe }  # url dedup

    # --- 정규화 도메인 (기존) ---
    prices/        { model(PriceDaily), schema, service, repository,
                     ingestion_service, universe }              # 정규화·검증을 잡 내부에 인라인 응집
    news/          { model(NewsArticle), schema, service, repository }

    # --- 신규 도메인 (지침 5·6·1단계) ---
    features/      # PriceFeatureBuilder / PortfolioFeatureBuilder / NewsFeatureBuilder
    llm_context/   # LLMContextBundle schema + ContextBuilder
    llm_analysis/  # LLMAnalysisRun / LLMAnalysisResult (input_context_json 저장)

    # --- 기타 기존 도메인 ---
    assets/  watchlists/  portfolios/  theses/  reports/  signals/
    alerts/  alert_candidates/  decision_logs/  decision_checklist/
    research_summary/  dashboard/  market/  analysis/  jobs/  users/

  core/    { config, exceptions, security, response, ... }
  db/      { base.py, session.py }

  worker/
    connection.py
    entrypoint.py
    jobs/
      prices.py       # collect_prices_job
      news.py         # collect_news_job
      analysis.py     # analyze_watchlist_job
      # 신규: detect_signals 등 필요 시

  scheduler/ { interface, jobs, registry, runner }

alembic/                         # DB migration (repo 루트 alembic.ini)
  env.py
  versions/
```

레이어 → 모듈 매핑:

```text
Ingestion        → app/adapters/<domain>/ + app/domains/<domain>/ingestion_service.py
Raw Store        → app/domains/raw_prices/, app/domains/raw_news/
Normalization    → 도메인 service/ingestion_service에 응집 (별도 패키지 아님)
                   · 가격: prices/ingestion_service.py 에서 정규화 인라인
                   · 뉴스: 현재 domains/analysis/service.py 에 분리됨 → domains/news/로
                     끌어와 수집 잡과 연결하는 것이 3단계 과제
Validation       → 도메인 내부 (가격: prices/ingestion_service.py 의 _validate_bars).
                   뉴스 Validator·DataQualityStatus 는 신규
Feature/Signal   → domains/features/ (신규), domains/signals/ + domains/analysis/ (룰 엔진)
Context Builder  → domains/llm_context/ (신규)
LLM Gateway      → app/adapters/llm/gateway.py (기존)
Analysis Store   → domains/llm_analysis/ (신규)
```

> 지침 3.1의 계층 흐름(`IngestionService → RawStore → … → LLMGateway`)은 개념 순서이며,
> 물리적으로는 위 도메인 모듈에 나뉘어 산다. top-level `services/` 패키지는 두지 않는다.

---

## 10. 초기 구현 범위

처음부터 모든 것을 만들지 않는다.

## v0.1 목표

```text
- Watchlist 모델
- PortfolioPosition 모델
- PriceDaily 모델
- NewsArticle 모델
- DecisionLog 모델
- RawProviderResponse 모델
- 가격 데이터 raw 저장
- 뉴스 데이터 raw 저장
- 가격 정규화
- 뉴스 정규화
- 가격 검증
- 뉴스 검증
- 기본 가격 피처 생성
- 기본 뉴스 피처 생성
- LLMContextBundle DTO
- ContextBuilder 기본 구현
- LLMAnalysisRun 저장 구조
```

## v0.1에서 하지 않는 것

```text
- 자동매매
- 증권사 API 실거래 연동
- 분봉 데이터 처리
- 공시 전문 파싱
- 복잡한 RAG
- 벡터 DB
- 전체 시장 스캐닝
- 실시간 WebSocket 가격 감시
```

---

## 11. 구현 우선순위

Claude Code는 아래 순서로 작업한다.

## 1단계: 데이터 계약 정의

먼저 Pydantic Schema와 SQLAlchemy Model을 정의한다.

대상:

```text
- Watchlist
- PortfolioPosition
- PriceDaily
- NewsArticle
- DecisionLog
- RawProviderResponse
- LLMContextBundle
- LLMAnalysisRun
- LLMAnalysisResult
```

---

## 2단계: Raw 저장 구조 구현

외부 API 연동이 없어도 테스트 가능한 구조로 만든다.

필요 기능:

```text
- raw payload 저장
- provider 저장
- payload_hash 생성
- 중복 payload 방지
- processing_status 관리
```

---

## 3단계: Normalizer 구현

Raw 데이터를 내부 모델로 변환한다.

필요 기능:

```text
- PriceNormalizer
- NewsNormalizer
- 날짜, 시간대 정규화
- symbol, market 정규화
- URL, source 정규화
```

---

## 4단계: Validator 구현

정규화된 데이터가 사용할 수 있는지 검증한다.

필요 기능:

```text
- PriceValidator
- NewsValidator
- DataQualityStatus
- ValidationErrorReason
```

---

## 5단계: Feature Builder 구현

LLM에 넣기 전에 계산 가능한 지표를 만든다.

필요 기능:

```text
- PriceFeatureBuilder
- PortfolioFeatureBuilder
- NewsFeatureBuilder
```

초기 가격 피처:

```text
- return_1d
- return_5d
- return_20d
- volume_vs_20d_avg
- drawdown_from_52w_high
```

---

## 6단계: ContextBuilder 구현

가격, 뉴스, 포트폴리오, decision-log를 모아 `LLMContextBundle`을 만든다.

필요 기능:

```text
- build_symbol_context(user_id, symbol)
- build_portfolio_context(user_id)
- build_recent_decision_context(user_id, symbol)
- build_context_bundle(task_type, user_id, symbols)
```

---

## 7단계: LLM Gateway는 마지막에 구현

LLM Gateway는 ContextBuilder 이후에 구현한다.

필요 기능:

```text
- ContextBundle 입력 받기
- prompt_version 관리
- output_schema 관리
- LLM input/output 저장
- JSON 응답 파싱
```

---

## 12. 테스트 기준

테스트는 외부 API 없이도 돌아가야 한다.

필수 테스트:

```text
- raw payload hash가 동일하면 중복 저장을 방지한다.
- price raw payload를 PriceDaily로 정규화할 수 있다.
- news raw payload를 NewsArticle로 정규화할 수 있다.
- 잘못된 가격 데이터는 invalid 처리된다.
- 미래 published_at을 가진 뉴스는 invalid 또는 stale 처리된다.
- 가격 피처가 올바르게 계산된다.
- ContextBuilder가 필요한 필드를 빠뜨리지 않는다.
- LLMContextBundle이 Pydantic validation을 통과한다.
- LLMAnalysisRun에 input_context_json이 저장된다.
```

---

## 13. 데이터 품질 정책

데이터 품질 상태는 명시적으로 표현한다.

예시 enum:

```text
valid
invalid
stale
partial
duplicate
low_trust
missing
```

LLMContextBundle에는 반드시 data_quality 섹션이 포함되어야 한다.

예시:

```json
{
  "data_quality": {
    "price_data_status": "valid",
    "news_data_status": "partial",
    "portfolio_data_status": "valid",
    "warnings": [
      "최근 24시간 뉴스 데이터가 부족합니다.",
      "공시 데이터는 아직 포함되지 않았습니다."
    ]
  }
}
```

LLM이 데이터 부족을 모른 채 확신 있게 답하지 않도록 해야 한다.

---

## 14. 사용자 규칙 처리

사용자 규칙은 하드코딩하지 않는다.

초기에는 기본 규칙을 seed data 또는 config로 둘 수 있다.

기본 규칙 예시:

```text
- 단일 종목 비중 20% 초과 금지
- 하루 10% 이상 급등한 종목은 당일 신규 매수 금지
- 5일 수익률 15% 이상 급등 시 추격 매수 금지
- 실적 발표 직전 신규 매수 금지
- 손실 중인 종목에 추가 매수하기 전 기존 thesis 재검토
- 뉴스 하나만 보고 매수 판단 금지
- AI 의견만으로 매수, 매도하지 않기
```

향후 모델:

```text
UserRule
- id
- user_id
- rule_type
- description
- is_active
- severity
- created_at
```

---

## 15. LLM 호출 트리거 정책

LLM은 모든 데이터 수집마다 호출하지 않는다.
비용과 품질을 위해 호출 조건을 제한한다.

허용 트리거:

```text
- 사용자가 직접 분석 요청
- 장 시작 전 브리핑
- 장 마감 후 리뷰
- 급등락 발생
- 거래량 급증
- 뉴스 폭증
- 포트폴리오 비중 제한 근접
- 사용자 규칙 위반 가능성 발생
```

초기 구현에서는 다음만 지원한다.

```text
- 사용자가 직접 분석 요청
- 수동으로 특정 symbol에 대한 ContextBundle 생성
```

이벤트 기반 자동 호출은 이후 단계에서 구현한다.

---

## 16. 저장소 선택 기준

초기 저장소:

```text
PostgreSQL
```

PostgreSQL에 저장할 데이터:

```text
- watchlist
- portfolio_positions
- price_daily
- news_articles
- decision_logs
- raw_provider_responses
- llm_analysis_runs
- llm_analysis_results
```

Redis는 초기 필수는 아니다.

Redis가 필요한 시점:

```text
- API rate limit 관리
- 작업 lock
- 중복 LLM 요청 방지
- 짧은 TTL 캐시
```

Object Storage가 필요한 시점:

```text
- 공시 원문
- 뉴스 전문
- 대량 raw payload
- LLM input/output 장기 아카이브
```

초기에는 PostgreSQL JSONB로 충분하다.

---

## 17. 금지 사항

Claude Code는 다음을 구현하지 않는다.

```text
- LLM이 외부 API를 직접 호출하는 구조
- LLM에게 가격 시계열 전체를 무제한 전달하는 구조
- LLM에게 뉴스 전문 전체를 무제한 전달하는 구조
- 매수, 매도 명령형 액션
- 자동매매 실행 로직
- 증권사 주문 API
- 출처 없는 데이터를 high trust로 처리하는 로직
- input_context_json 없이 LLM 결과만 저장하는 구조
- prompt string만 저장하고 구조화된 ContextBundle을 생략하는 구조
```

---

## 18. 완료 조건

이 파이프라인의 1차 완료 조건은 다음과 같다.

```text
- 외부 데이터 원본과 정규화 데이터가 분리되어 있다.
- RawProviderResponse가 존재한다.
- PriceDaily, NewsArticle, PortfolioPosition, DecisionLog 모델이 존재한다.
- 가격 데이터와 뉴스 데이터의 Normalizer가 존재한다.
- 데이터 품질 상태를 표현할 수 있다.
- 가격 피처를 계산할 수 있다.
- ContextBuilder가 LLMContextBundle을 생성할 수 있다.
- LLMContextBundle은 Pydantic schema로 검증된다.
- LLMAnalysisRun에 input_context_json이 저장된다.
- LLMGateway는 ContextBundle만 입력받는다.
- LLM은 외부 API를 직접 호출하지 않는다.
```

---

## 19. Claude Code 작업 방식

작업 시 다음 순서를 따른다.

```text
1. 기존 프로젝트 구조를 먼저 파악한다.
2. 이미 존재하는 모델, schema, service, route와 중복되지 않게 설계한다.
3. 데이터 계약을 먼저 만든다.
4. DB migration을 작성한다.
5. service를 구현한다.
6. unit test를 작성한다.
7. route는 가장 마지막에 얇게 붙인다.
```

route는 비즈니스 로직을 가지면 안 된다.

좋은 구조:

```text
API Route → Application Service → Domain Service → Repository
```

나쁜 구조:

```text
API Route 내부에서 정규화, 검증, 피처 계산, LLM 호출을 모두 수행
```

---

## 20. 최종 목표 그림

이 프로젝트의 LLM 데이터 파이프라인은 다음 상태를 목표로 한다.

```text
사용자 관심 종목
  ↓
가격, 뉴스, 포트폴리오, decision-log 수집
  ↓
정규화와 검증
  ↓
수치 피처와 이벤트 시그널 생성
  ↓
LLMContextBundle 생성
  ↓
LLM 분석
  ↓
리스크, 반대 시나리오, 주의점 저장
  ↓
사용자 의사결정 보조
```

LLM은 시스템의 두뇌 전체가 아니다.
LLM은 정리된 근거를 읽고 해석하는 마지막 분석 계층이다.

백엔드는 LLM에게 “판단할 수 있는 재료”를 만들어주는 데이터 조리장이다.

이 원칙을 기준으로 구현한다.
