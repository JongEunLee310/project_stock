from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.adapters.llm.base import LLMClient
from app.adapters.news.base import NewsAdapter, NewsAdapterResult
from app.core.exceptions import AppException
from app.domains.analysis.schema import AnalysisFlowResult
from app.domains.alerts.service import AlertService
from app.domains.assets.model import Asset
from app.domains.news.model import NewsItem
from app.domains.news.repository import NewsItemRepository
from app.domains.news.schema import NewsItemCreate, NewsSummaryResult
from app.domains.news.service import NewsAnalysisService
from app.domains.raw_news.repository import RawNewsEventRepository
from app.domains.raw_news.service import RawNewsService
from app.domains.reports.schema import ResearchReportCreate
from app.domains.reports.service import ResearchReportService
from app.domains.signals.repository import SignalRepository
from app.domains.signals.rules import RuleContext, RuleEngine, default_rules
from app.domains.theses.conflict_schema import ThesisConflictResult
from app.domains.theses.conflict_service import ThesisAnalysisService
from app.domains.theses.model import InvestmentThesis
from app.domains.theses.repository import ThesisRepository
from app.domains.watchlists.repository import (
    WatchlistItemRepository,
    WatchlistRepository,
)


class WatchlistAnalysisService:
    def __init__(
        self,
        db: Session,
        llm_client: LLMClient,
        news_adapter: NewsAdapter,
    ) -> None:
        self.db = db
        self.llm_client = llm_client
        self.news_adapter = news_adapter
        self.watchlist_repo = WatchlistRepository(db)
        self.watchlist_item_repo = WatchlistItemRepository(db)
        self.raw_news_repo = RawNewsEventRepository(db)
        self.news_item_repo = NewsItemRepository(db)
        self.thesis_repo = ThesisRepository(db)
        self.news_analysis = NewsAnalysisService(db, llm_client)
        self.thesis_analysis = ThesisAnalysisService(db, llm_client)
        self.report_service = ResearchReportService(db)
        self.alert_service = AlertService(db)

    def run(self, watchlist_id: int) -> AnalysisFlowResult:
        watchlist = self.watchlist_repo.get_by_id(watchlist_id)
        if watchlist is None:
            raise AppException(
                status_code=404,
                detail="관심 목록을 찾을 수 없습니다.",
            )

        result = AnalysisFlowResult(
            watchlist_id=watchlist_id,
            processed_assets=0,
            created_news_items=0,
            created_reports=0,
            created_signals=0,
            created_alerts=0,
            failures=[],
        )

        for item in self.watchlist_item_repo.list_by_watchlist(watchlist_id):
            asset = self.db.get(Asset, item.asset_id)
            if asset is None:
                result.failures.append(
                    {"asset_id": item.asset_id, "error": "asset not found"}
                )
                continue

            try:
                asset_result = self._process_asset(asset, watchlist.user_id)
            except Exception as exc:
                self.db.rollback()
                result.failures.append({"asset_id": asset.id, "error": str(exc)})
                continue

            result.processed_assets += 1
            result.created_news_items += asset_result.created_news_items
            result.created_reports += asset_result.created_reports
            result.created_signals += asset_result.created_signals
            result.created_alerts += asset_result.created_alerts

        return result

    def _process_asset(self, asset: Asset, user_id: int) -> "_AssetAnalysisResult":
        recording_adapter = _RecordingNewsAdapter(self.news_adapter)
        RawNewsService(self.db).collect_and_save(recording_adapter, [asset.symbol])
        news_items = self._create_new_items(asset, recording_adapter.results)
        thesis = self.thesis_repo.get_latest_by_asset(asset.id, user_id)

        created_reports = 0
        created_signals = 0
        created_alerts = 0

        for news_item in news_items:
            summary_result = self.news_analysis.summarize(news_item.id)
            self.db.refresh(news_item)
            conflict_result = self._analyze_conflict(news_item, thesis)
            self._create_report(
                asset.id,
                news_item,
                summary_result,
                thesis,
                conflict_result,
            )
            created_reports += 1

            signals = RuleEngine(default_rules(), SignalRepository(self.db)).run(
                RuleContext(
                    asset_id=asset.id,
                    news_item=news_item,
                    thesis=thesis,
                    conflict_result=conflict_result,
                )
            )
            created_signals += len(signals)
            for signal in signals:
                if self.alert_service.create_alert(user_id, signal) is not None:
                    created_alerts += 1

        return _AssetAnalysisResult(
            created_news_items=len(news_items),
            created_reports=created_reports,
            created_signals=created_signals,
            created_alerts=created_alerts,
        )

    def _create_new_items(
        self,
        asset: Asset,
        collected_results: list[NewsAdapterResult],
    ) -> list[NewsItem]:
        news_items: list[NewsItem] = []
        seen_urls: set[str] = set()
        for result in collected_results:
            if result.url in seen_urls or self.news_item_repo.exists_by_url(result.url):
                continue
            seen_urls.add(result.url)
            raw_event = self.raw_news_repo.get_by_url(result.url)
            news_items.append(
                self.news_item_repo.create(
                    NewsItemCreate(
                        raw_news_event_id=(
                            raw_event.id if raw_event is not None else None
                        ),
                        asset_id=asset.id,
                        title=result.title,
                        url=result.url,
                        source=result.source,
                        published_at=result.published_at,
                    )
                )
            )
        return news_items

    def _analyze_conflict(
        self,
        news_item: NewsItem,
        thesis: InvestmentThesis | None,
    ) -> ThesisConflictResult | None:
        if thesis is None:
            return None
        return self.thesis_analysis.analyze_conflict(news_item.id, thesis.id)

    def _create_report(
        self,
        asset_id: int,
        news_item: NewsItem,
        summary_result: NewsSummaryResult,
        thesis: InvestmentThesis | None,
        conflict_result: ThesisConflictResult | None,
    ) -> None:
        self.report_service.create_report(
            ResearchReportCreate(
                asset_id=asset_id,
                thesis_id=thesis.id if thesis is not None else None,
                summary=summary_result.summary,
                positive_factors=summary_result.positive_factors,
                negative_factors=summary_result.negative_factors,
                risk_level=summary_result.impact_level,
                thesis_conflict_status=(
                    conflict_result.status if conflict_result is not None else None
                ),
                conflict_reason=(
                    conflict_result.reason if conflict_result is not None else None
                ),
                news_item_ids=[news_item.id],
            )
        )


class _RecordingNewsAdapter(NewsAdapter):
    def __init__(self, wrapped: NewsAdapter) -> None:
        self.wrapped = wrapped
        self.results: list[NewsAdapterResult] = []

    def fetch(self, symbols: list[str]) -> list[NewsAdapterResult]:
        self.results = self.wrapped.fetch(symbols)
        return self.results


@dataclass(frozen=True)
class _AssetAnalysisResult:
    created_news_items: int
    created_reports: int
    created_signals: int
    created_alerts: int
