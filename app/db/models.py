# Register all models in metadata regardless of each process import graph.
import app.domains.alert_candidates.model  # noqa: F401 — registers alert candidate model
import app.domains.alerts.model  # noqa: F401 — registers Alert model for autogenerate
import app.domains.assets.model  # noqa: F401 — registers Asset model for autogenerate
import app.domains.decision_checklist.model  # noqa: F401 — registers checklist model
import app.domains.decision_logs.model  # noqa: F401 — registers decision log model
import app.domains.earnings.model  # noqa: F401 — registers earnings models
import app.domains.jobs.model  # noqa: F401 — registers JobRun model for autogenerate
import app.domains.llm_analysis.model  # noqa: F401 — registers LLM analysis run model
import app.domains.news.model  # noqa: F401 — registers NewsItem model for autogenerate
import app.domains.portfolios.model  # noqa: F401 — registers Portfolio models for autogenerate
import app.domains.prices.model  # noqa: F401 — registers price bar model
import app.domains.raw_news.model  # noqa: F401 — registers RawNewsEvent model for autogenerate
import app.domains.raw_prices.model  # noqa: F401 — registers RawPrice model
import app.domains.reports.model  # noqa: F401 — registers ResearchReport model for autogenerate
import app.domains.signals.model  # noqa: F401 — registers Signal model for autogenerate
import app.domains.signals.snapshot_model  # noqa: F401 — registers signal snapshot model
import app.domains.theses.conflict_model  # noqa: F401 — registers thesis conflict model
import app.domains.theses.model  # noqa: F401 — registers InvestmentThesis model for autogenerate
import app.domains.users.model  # noqa: F401 — registers User model for autogenerate
import app.domains.valuation.model  # noqa: F401 — registers valuation snapshot model
import app.domains.watchlists.model  # noqa: F401 — registers Watchlist models for autogenerate
