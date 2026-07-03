from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.adapters.llm.types import LLMTaskType
from app.domains.assets.repository import AssetRepository
from app.domains.decision_logs.repository import DecisionLogRepository
from app.domains.features.price_builder import PriceFeatureBuilder
from app.domains.features.schema import PriceFeatureSet
from app.domains.llm_context.schema import (
    DataQualitySection,
    DataQualityStatus,
    LLMContextBundle,
    OutputContract,
    PortfolioContext,
    PortfolioSummary,
    PriceSnapshot,
    RecentDecision,
    SymbolCard,
)
from app.domains.llm_context.user_rules import DEFAULT_USER_RULES
from app.domains.portfolios.repository import PortfolioRepository
from app.domains.portfolios.schema import PortfolioSummaryResponse, PositionWeight
from app.domains.portfolios.service import PortfolioService
from app.domains.prices.model import StockPriceBar
from app.domains.prices.repository import PriceBarRepository

_PRICE_BAR_LIMIT = 252
_RECENT_DECISION_LIMIT = 5
_NEWS_MISSING_WARNING = "뉴스 데이터는 아직 포함되지 않았습니다."
_OUTPUT_REQUIRED_FIELDS = [
    "summary",
    "risk_level",
    "suggested_action",
    "reasons",
    "watch_points",
    "counter_arguments",
    "data_limitations",
    "confidence",
]
_USER_INTENT_BY_TASK_TYPE: dict[LLMTaskType, str] = {
    LLMTaskType.NEWS_SUMMARY: "관련 뉴스 흐름을 요약하고 투자 판단에 필요한 제한 사항을 확인한다.",
    LLMTaskType.THESIS_CONFLICT: "기존 투자 thesis와 충돌하는 근거가 있는지 점검한다.",
    LLMTaskType.PORTFOLIO_BRIEFING: "포트폴리오 상태와 주요 리스크를 점검한다.",
    LLMTaskType.DASHBOARD_BRIEFING: "대시보드 요약에 필요한 핵심 시장·보유 정보를 점검한다.",
    LLMTaskType.WATCHLIST_NOTE: "관심 종목의 점검 포인트와 데이터 한계를 정리한다.",
    LLMTaskType.TAG_SENTIMENT: "태그별 분위기와 판단 제한 사항을 정리한다.",
    LLMTaskType.AGENT: "사용자 요청에 맞춰 투자 판단에 필요한 맥락을 점검한다.",
}


class ContextBuilder:
    def __init__(self, db: Session) -> None:
        self.asset_repo = AssetRepository(db)
        self.price_bar_repo = PriceBarRepository(db)
        self.portfolio_repo = PortfolioRepository(db)
        self.portfolio_service = PortfolioService(db)
        self.decision_log_repo = DecisionLogRepository(db)
        self.price_feature_builder = PriceFeatureBuilder()

    def build_symbol_context(
        self,
        user_id: int,
        symbol: str,
        market: str,
    ) -> SymbolCard:
        asset = self.asset_repo.get_by_symbol_market(symbol, market)
        bars = self.price_bar_repo.list_recent(
            symbol,
            market,
            interval="1d",
            limit=_PRICE_BAR_LIMIT,
        )
        return SymbolCard(
            symbol=symbol,
            market=market,
            display_name=asset.name if asset is not None else "",
            price_snapshot=_build_price_snapshot(bars, self.price_feature_builder),
            portfolio_context=self._build_position_context(user_id, asset.id)
            if asset is not None
            else None,
            recent_news=[],
            signals=[],
        )

    def build_portfolio_context(self, user_id: int) -> PortfolioSummary | None:
        summary = self._get_first_portfolio_summary(user_id)
        if summary is None or not summary.positions:
            return None

        top_holding_weight = max(position.weight for position in summary.positions)
        return PortfolioSummary(
            cash_ratio=_to_float(summary.cash_weight),
            top_holding_weight=_to_float(top_holding_weight),
            concentration_risk=_concentration_risk(summary),
        )

    def build_recent_decision_context(
        self,
        user_id: int,
        symbol: str,
    ) -> list[RecentDecision]:
        decision_logs = self.decision_log_repo.list_by_user(
            user_id,
            limit=_RECENT_DECISION_LIMIT,
            sort="-decided_at",
        )
        return [
            RecentDecision(
                symbol=decision_log.ticker,
                decision_type=decision_log.decision_type,
                reason=decision_log.reason or "",
                created_at=decision_log.decided_at,
            )
            for decision_log in decision_logs
            if decision_log.ticker == symbol
        ]

    def build_context_bundle(
        self,
        task_type: LLMTaskType,
        user_id: int,
        symbols: list[tuple[str, str]],
    ) -> LLMContextBundle:
        symbol_cards = [
            self.build_symbol_context(user_id, symbol, market)
            for symbol, market in symbols
        ]
        return LLMContextBundle(
            task_type=task_type,
            as_of=datetime.now(UTC),
            user_intent=_USER_INTENT_BY_TASK_TYPE[task_type],
            symbols=[symbol for symbol, _market in symbols],
            data_quality=self._build_data_quality(symbol_cards, user_id),
            symbol_cards=symbol_cards,
            portfolio_summary=self.build_portfolio_context(user_id),
            user_rules=list(DEFAULT_USER_RULES),
            recent_decisions=[
                decision
                for symbol, _market in symbols
                for decision in self.build_recent_decision_context(user_id, symbol)
            ],
            output_contract=OutputContract(required_fields=list(_OUTPUT_REQUIRED_FIELDS)),
        )

    def _build_position_context(
        self,
        user_id: int,
        asset_id: int,
    ) -> PortfolioContext | None:
        summary = self._get_first_portfolio_summary(user_id)
        if summary is None:
            return None

        position = next(
            (
                summary_position
                for summary_position in summary.positions
                if summary_position.asset_id == asset_id
            ),
            None,
        )
        if position is None:
            return None

        return PortfolioContext(
            holding=True,
            weight=_to_float(position.weight),
            avg_buy_price=_to_float(position.avg_buy_price),
            unrealized_return=_calculate_unrealized_return(position),
        )

    def _get_first_portfolio_summary(
        self,
        user_id: int,
    ) -> PortfolioSummaryResponse | None:
        portfolios = self.portfolio_repo.list_by_user(user_id, limit=1)
        if not portfolios:
            return None
        try:
            return self.portfolio_service.get_summary(portfolios[0].id, user_id)
        except Exception:
            return None

    def _build_data_quality(
        self,
        symbol_cards: list[SymbolCard],
        user_id: int,
    ) -> DataQualitySection:
        warnings = [_NEWS_MISSING_WARNING]
        price_status = _price_data_status(symbol_cards)
        if price_status == DataQualityStatus.MISSING:
            warnings.append("가격 데이터가 없습니다.")
        elif price_status == DataQualityStatus.PARTIAL:
            warnings.append("일부 종목의 가격 데이터가 부족합니다.")

        portfolio_status = self._portfolio_data_status(user_id)
        if portfolio_status == DataQualityStatus.MISSING:
            warnings.append("포트폴리오 데이터가 없습니다.")

        return DataQualitySection(
            price_data_status=price_status,
            news_data_status=DataQualityStatus.MISSING,
            portfolio_data_status=portfolio_status,
            warnings=warnings,
        )

    def _portfolio_data_status(self, user_id: int) -> DataQualityStatus:
        summary = self._get_first_portfolio_summary(user_id)
        if summary is None or not summary.positions:
            return DataQualityStatus.MISSING
        return DataQualityStatus.VALID


def _build_price_snapshot(
    bars: list[StockPriceBar],
    price_feature_builder: PriceFeatureBuilder,
) -> PriceSnapshot:
    if not bars:
        return PriceSnapshot(
            close=None,
            return_1d=None,
            return_5d=None,
            return_20d=None,
            drawdown_from_52w_high=None,
            volume_vs_20d_avg=None,
        )

    features = price_feature_builder.build(bars)
    return _snapshot_from_features(bars[-1], features)


def _snapshot_from_features(
    latest_bar: StockPriceBar,
    features: PriceFeatureSet,
) -> PriceSnapshot:
    return PriceSnapshot(
        close=_to_float(latest_bar.close_price),
        return_1d=_to_float(features.return_1d),
        return_5d=_to_float(features.return_5d),
        return_20d=_to_float(features.return_20d),
        drawdown_from_52w_high=_to_float(features.drawdown_from_52w_high),
        volume_vs_20d_avg=_to_float(features.volume_vs_20d_avg),
    )


def _calculate_unrealized_return(position: PositionWeight) -> float | None:
    if position.cost_value == 0:
        return None
    return _to_float((position.market_value - position.cost_value) / position.cost_value)


def _to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _concentration_risk(summary: PortfolioSummaryResponse) -> str:
    if any(position.exceeds_threshold for position in summary.positions):
        return "high"
    if summary.has_sector_concentration:
        return "medium"
    return "low"


def _price_data_status(symbol_cards: list[SymbolCard]) -> DataQualityStatus:
    if not symbol_cards:
        return DataQualityStatus.MISSING

    cards_with_price = sum(1 for card in symbol_cards if _has_any_price_data(card))
    if cards_with_price == len(symbol_cards):
        if all(_has_complete_price_data(card) for card in symbol_cards):
            return DataQualityStatus.VALID
        return DataQualityStatus.PARTIAL
    if cards_with_price > 0:
        return DataQualityStatus.PARTIAL
    return DataQualityStatus.MISSING


def _has_any_price_data(card: SymbolCard) -> bool:
    return card.price_snapshot.close is not None


def _has_complete_price_data(card: SymbolCard) -> bool:
    snapshot = card.price_snapshot
    return (
        snapshot.close is not None
        and snapshot.return_1d is not None
        and snapshot.return_5d is not None
        and snapshot.return_20d is not None
        and snapshot.drawdown_from_52w_high is not None
        and snapshot.volume_vs_20d_avg is not None
    )
