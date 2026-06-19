# Design: Mock Data Provider 구조 (Issue #49 / 제목 Issue 29)

외부 증권/뉴스/공시/시세 API 없이도 백엔드를 기동하고 프론트엔드 화면을 개발할 수 있도록, 어댑터 경계를 표준화하고 환경 변수로 mock/real provider를 전환하는 구조를 추가한다.

## 어댑터 경계

기존 `app/adapters/news/`, `app/adapters/llm/` 패턴(ABC `base.py` + `mock.py`)을 따른다. 신규 도메인 어댑터를 추가한다.

| 어댑터 | 디렉터리 | 추상 인터페이스 | mock 구현 |
|--------|----------|----------------|-----------|
| 시세 | app/adapters/market/ | `MarketDataProvider` | `MockMarketDataProvider` |
| 뉴스 | app/adapters/news/ (기존) | `NewsAdapter` | `MockNewsAdapter` (존재) |
| 공시 | app/adapters/disclosure/ | `DisclosureProvider` | `MockDisclosureProvider` |
| 포트폴리오 | app/adapters/portfolio/ | `PortfolioProvider` | `MockPortfolioProvider` |

각 `base.py`는 `ABC` + `@abstractmethod` 메서드 시그니처와 `@dataclass(frozen=True)` 결과 DTO만 정의(news 패턴 동일). 실제 메서드 집합은 핸드오프에서 화면 요구(Issue #48)에 맞춰 확정.

- `MarketDataProvider.get_quote(symbols) -> list[QuoteResult]` (현재가/등락 등 mock 시세)
- `DisclosureProvider.fetch(symbols) -> list[DisclosureResult]`
- `PortfolioProvider.fetch_holdings(account_ref) -> list[HoldingResult]`

## Provider Mode 설정 (app/core/config.py)

프로바이더별 개별 플래그를 추가한다. 각 값은 `mock | real`.

| 설정 | 기본값 |
|------|--------|
| MARKET_PROVIDER | mock |
| NEWS_PROVIDER | mock |
| DISCLOSURE_PROVIDER | mock |
| PORTFOLIO_PROVIDER | mock |

- 타입은 `Literal["mock", "real"]` 권장(검증은 시스템 경계인 설정 로딩에서).

## Provider 팩토리

신규 `app/adapters/factory.py` (또는 `app/adapters/registry.py`).

- `get_market_provider() -> MarketDataProvider`
- `get_news_adapter() -> NewsAdapter`
- `get_disclosure_provider() -> DisclosureProvider`
- `get_portfolio_provider() -> PortfolioProvider`

각 팩토리는 해당 설정 플래그를 읽어 mock 구현을 반환한다. `real`이 선택되면 현 단계에서는 `NotImplementedError`(real 구현은 후속 이슈). worker 잡(`app/worker/jobs/news.py`, `analysis.py`)의 `MockNewsAdapter()` 직접 인스턴스화를 팩토리 경유로 교체.

## 샘플 데이터

- mock 구현은 결정적(deterministic)인 샘플 데이터를 반환해 프론트 개발/테스트 재현성 확보(기존 `MockNewsAdapter` 스타일).
- 샘플 종목/시세/공시/보유 데이터는 mock 모듈 내 상수 또는 `app/adapters/<domain>/sample_data.py`로 관리.

## 의존성

- 기존 `app/adapters/news`, `app/adapters/llm` 패턴 재사용.
- Issue #48(API 명세)이 mock 응답 형태를 참조 — 단, 본 구조는 독립 진행 가능.

## 마이그레이션/스키마

- DB 변경 없음. 어댑터/설정 계층만.

## 리스크

- Low~Medium. 신규 어댑터 경계 추가 + worker 와이어링 교체. 기존 동작(mock 사용)은 유지되므로 회귀 표면 작음.
- real 구현 미존재 상태에서 `real` 선택 시 명시적 `NotImplementedError`로 조기 실패.
