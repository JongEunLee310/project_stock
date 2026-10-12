from sqlalchemy.orm import Session

from app.adapters.disclosure.base import DisclosureProvider
from app.adapters.disclosure.mock import MockDisclosureProvider
from app.adapters.embedding.base import Embedder
from app.adapters.embedding.mock import MockEmbedder
from app.adapters.embedding.openai import OpenAIEmbedder
from app.adapters.llm.base import LLMClient
from app.adapters.llm.budget import DailyCallBudget
from app.adapters.llm.cache import LLMResponseCache
from app.adapters.llm.escalation import EscalationPolicy
from app.adapters.llm.gateway import CLOUD, LOCAL, LLMGateway
from app.adapters.llm.local import LocalLLMProvider
from app.adapters.llm.mock import DEFAULT_MOCK_RESPONSES, MockLLMClient
from app.adapters.llm.openai import OpenAIClient
from app.adapters.market.base import (
    EarningsProvider,
    ExchangeRateProvider,
    IndexQuoteProvider,
    MarketDataProvider,
    PriceSeriesProvider,
    SymbolLookupProvider,
    ValuationProvider,
)
from app.adapters.market.cache import (
    CachedExchangeRateProvider,
    CachedIndexQuoteProvider,
    CachedMarketDataProvider,
)
from app.adapters.market.mock import (
    MockEarningsProvider,
    MockExchangeRateProvider,
    MockIndexQuoteProvider,
    MockMarketDataProvider,
    MockPriceSeriesProvider,
    MockSymbolLookupProvider,
    MockValuationProvider,
)
from app.adapters.market.yfinance import (
    YFinanceEarningsProvider,
    YFinanceExchangeRateProvider,
    YFinanceIndexQuoteProvider,
    YFinanceMarketDataProvider,
    YFinancePriceProvider,
    YFinanceSymbolLookupProvider,
    YFinanceValuationProvider,
)
from app.adapters.news.base import NewsAdapter
from app.adapters.news.mock import MockNewsAdapter
from app.adapters.news.rss import RSSNewsAdapter
from app.adapters.portfolio.base import PortfolioProvider
from app.adapters.portfolio.mock import MockPortfolioProvider
from app.adapters.vector.base import VectorStore
from app.adapters.vector.memory import InMemoryVectorStore
from app.adapters.vector.pgvector import PgVectorStore
from app.core.config import settings
from app.domains.rag.types import EMBEDDING_DIMENSIONS
from app.worker.connection import get_redis_connection

LOCAL_PROXY_OPENAI_API_KEY = "local-proxy"


def get_market_provider() -> MarketDataProvider:
    if settings.MARKET_PROVIDER == "mock":
        return MockMarketDataProvider()
    if settings.MARKET_PROVIDER == "yfinance":
        return CachedMarketDataProvider(YFinanceMarketDataProvider())
    raise NotImplementedError("market real provider 미구현")


def get_price_series_provider() -> PriceSeriesProvider:
    if settings.MARKET_PROVIDER == "mock":
        return MockPriceSeriesProvider()
    if settings.MARKET_PROVIDER == "yfinance":
        return YFinancePriceProvider()
    raise NotImplementedError("market real provider 미구현")


def get_index_quote_provider() -> IndexQuoteProvider:
    if settings.MARKET_PROVIDER == "mock":
        return MockIndexQuoteProvider()
    if settings.MARKET_PROVIDER == "yfinance":
        return CachedIndexQuoteProvider(YFinanceIndexQuoteProvider())
    raise NotImplementedError("market real provider 미구현")


def get_exchange_rate_provider() -> ExchangeRateProvider:
    if settings.MARKET_PROVIDER == "mock":
        return MockExchangeRateProvider()
    if settings.MARKET_PROVIDER == "yfinance":
        return CachedExchangeRateProvider(YFinanceExchangeRateProvider())
    raise NotImplementedError("market real provider 미구현")


def get_symbol_lookup_provider() -> SymbolLookupProvider:
    if settings.MARKET_PROVIDER == "mock":
        return MockSymbolLookupProvider()
    if settings.MARKET_PROVIDER == "yfinance":
        return YFinanceSymbolLookupProvider()
    raise NotImplementedError("market real provider 미구현")


def get_valuation_provider() -> ValuationProvider:
    if settings.MARKET_PROVIDER == "mock":
        return MockValuationProvider()
    if settings.MARKET_PROVIDER == "yfinance":
        return YFinanceValuationProvider()
    raise NotImplementedError("market real provider 미구현")


def get_earnings_provider() -> EarningsProvider:
    if settings.MARKET_PROVIDER == "mock":
        return MockEarningsProvider()
    if settings.MARKET_PROVIDER == "yfinance":
        return YFinanceEarningsProvider()
    raise NotImplementedError("market real provider 미구현")


def get_news_adapter() -> NewsAdapter:
    if settings.NEWS_PROVIDER == "mock":
        return MockNewsAdapter()
    if settings.NEWS_PROVIDER == "rss":
        return RSSNewsAdapter([], query_url_template=settings.NEWS_QUERY_URL_TEMPLATE)
    raise NotImplementedError("news real provider 미구현")


def get_disclosure_provider() -> DisclosureProvider:
    if settings.DISCLOSURE_PROVIDER == "mock":
        return MockDisclosureProvider()
    raise NotImplementedError("disclosure real provider 미구현")


def get_portfolio_provider() -> PortfolioProvider:
    if settings.PORTFOLIO_PROVIDER == "mock":
        return MockPortfolioProvider()
    raise NotImplementedError("portfolio real provider 미구현")


def get_llm_client(provider: str | None = None) -> LLMClient:
    selected_provider = settings.LLM_PROVIDER if provider is None else provider
    if selected_provider == "cloud":
        base_url = settings.OPENAI_BASE_URL
        api_key = settings.OPENAI_API_KEY
        if api_key is None or not api_key.strip():
            if base_url is None:
                raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=cloud")
            api_key = LOCAL_PROXY_OPENAI_API_KEY
        return OpenAIClient(
            api_key=api_key,
            model=settings.OPENAI_MODEL,
            base_url=base_url,
        )
    if selected_provider == "local":
        return LocalLLMProvider()
    if selected_provider == "mock":
        return MockLLMClient(DEFAULT_MOCK_RESPONSES)
    raise NotImplementedError(f"llm provider 미구현: {selected_provider}")


def get_llm_gateway() -> LLMGateway:
    if settings.LLM_PROVIDER == "mock":
        mock_client = get_llm_client("mock")
        return LLMGateway(
            {CLOUD: mock_client, LOCAL: mock_client},
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
        )
    if settings.LLM_PROVIDER == "cloud":
        redis = (
            get_redis_connection()
            if settings.LLM_DAILY_CALL_LIMIT is not None
            or settings.LLM_CACHE_TTL_SECONDS is not None
            else None
        )
        call_budget = (
            DailyCallBudget(redis, settings.LLM_DAILY_CALL_LIMIT)
            if redis is not None and settings.LLM_DAILY_CALL_LIMIT is not None
            else None
        )
        response_cache = (
            LLMResponseCache(redis, settings.LLM_CACHE_TTL_SECONDS)
            if redis is not None and settings.LLM_CACHE_TTL_SECONDS is not None
            else None
        )
        escalation_policy = (
            EscalationPolicy(settings.LLM_ESCALATION_CONFIDENCE_THRESHOLD)
            if settings.LLM_ESCALATION_ENABLED
            else None
        )
        return LLMGateway(
            {
                CLOUD: get_llm_client("cloud"),
                LOCAL: get_llm_client("local"),
            },
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
            call_budget=call_budget,
            response_cache=response_cache,
            escalation_policy=escalation_policy,
        )
    if settings.LLM_PROVIDER == "local":
        local_client = get_llm_client("local")
        return LLMGateway(
            {LOCAL: local_client, CLOUD: local_client},
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
        )
    raise NotImplementedError(f"llm provider 미구현: {settings.LLM_PROVIDER}")


def get_embedder() -> Embedder:
    if settings.EMBEDDING_PROVIDER == "mock":
        return MockEmbedder()
    if settings.EMBEDDING_PROVIDER == "openai":
        api_key = settings.EMBEDDING_API_KEY or settings.OPENAI_API_KEY
        if api_key is None or not api_key.strip():
            raise RuntimeError(
                "EMBEDDING_API_KEY or OPENAI_API_KEY is required "
                "when EMBEDDING_PROVIDER=openai"
            )
        return OpenAIEmbedder(
            api_key=api_key,
            model=settings.EMBEDDING_MODEL,
            base_url=settings.EMBEDDING_BASE_URL,
            dimensions=EMBEDDING_DIMENSIONS,
        )
    raise NotImplementedError(
        f"embedding provider 미구현: {settings.EMBEDDING_PROVIDER}"
    )


def get_vector_store(db: Session) -> VectorStore:
    if settings.VECTOR_STORE_PROVIDER == "pgvector":
        return PgVectorStore(db)
    if settings.VECTOR_STORE_PROVIDER == "mock":
        return InMemoryVectorStore()
    raise NotImplementedError(
        f"vector store provider 미구현: {settings.VECTOR_STORE_PROVIDER}"
    )
