import importlib.util
from pathlib import Path
from types import ModuleType
from datetime import datetime, timezone
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.llm.types import LLMTaskType, RiskLevel
from app.domains.ingestion.schema import (
    ProcessingStatus,
    RawDataType,
    RawProviderResponse,
)
from app.domains.llm_analysis.model import LLMAnalysisRun
from app.domains.llm_analysis.schema import LLMAnalysisResult, SuggestedAction
from app.domains.llm_context.schema import LLMContextBundle


REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    REPO_ROOT
    / "alembic"
    / "versions"
    / "c3d4e5f60057_create_llm_analysis_runs.py"
)


def _load_migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "test_c3d4e5f60057_create_llm_analysis_runs",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _context_bundle_payload() -> dict[str, Any]:
    return {
        "task_type": LLMTaskType.WATCHLIST_NOTE.value,
        "as_of": "2026-07-02T18:00:00+09:00",
        "user_intent": "관심 종목의 리스크를 점검하고 충동 매수를 방지한다.",
        "symbols": ["NVDA"],
        "data_quality": {
            "price_data_status": "valid",
            "news_data_status": "valid",
            "portfolio_data_status": "valid",
            "warnings": [],
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
                    "volume_vs_20d_avg": 1.8,
                },
                "portfolio_context": {
                    "holding": True,
                    "weight": 18.5,
                    "avg_buy_price": 121.4,
                    "unrealized_return": 26.2,
                },
                "recent_news": [
                    {
                        "title": "Example news title",
                        "summary": "Short normalized summary",
                        "source": "Example Source",
                        "published_at": "2026-07-02T09:00:00+09:00",
                        "trust_level": "high",
                    }
                ],
                "signals": [
                    {
                        "type": "volume_spike",
                        "severity": "medium",
                        "reason": "거래량이 20일 평균 대비 1.8배입니다.",
                    }
                ],
            }
        ],
        "portfolio_summary": {
            "cash_ratio": 22.0,
            "top_holding_weight": 18.5,
            "concentration_risk": "medium",
        },
        "user_rules": [
            "단일 종목 비중 20% 초과 금지",
            "5일 수익률 15% 이상 급등 시 추격 매수 금지",
            "실적 발표 직전 신규 매수 금지",
        ],
        "recent_decisions": [
            {
                "symbol": "NVDA",
                "decision_type": "hold",
                "reason": "이미 목표 비중에 근접하여 신규 매수는 보류",
                "created_at": "2026-06-28T21:00:00+09:00",
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
                "confidence",
            ],
        },
    }


def _analysis_result_payload() -> dict[str, Any]:
    return {
        "summary": "현재 보유 비중은 유지 가능하나 단기 과열 신호가 있습니다.",
        "risk_level": RiskLevel.MEDIUM.value,
        "suggested_action": SuggestedAction.HOLD.value,
        "reasons": [
            "20일 수익률이 높습니다.",
            "거래량이 평균 대비 증가했습니다.",
            "단일 종목 비중이 내부 제한에 근접했습니다.",
        ],
        "watch_points": [
            "다음 실적 발표 일정",
            "거래량 증가 지속 여부",
            "섹터 조정 가능성",
        ],
        "counter_arguments": [
            "실적 성장률이 유지된다면 추가 상승 가능성도 있습니다."
        ],
        "data_limitations": ["공시 데이터가 아직 포함되지 않았습니다."],
        "confidence": 0.72,
    }


def test_raw_provider_response_defaults_to_fetched() -> None:
    response = RawProviderResponse(
        provider="yfinance",
        data_type=RawDataType.PRICE,
        symbol="NVDA",
        market="US",
        payload={"close": 153.2},
        payload_hash="a" * 64,
        fetched_at=datetime.now(timezone.utc),
    )

    assert response.processing_status is ProcessingStatus.FETCHED


def test_llm_context_bundle_accepts_contract_payload() -> None:
    bundle = LLMContextBundle.model_validate(_context_bundle_payload())

    assert bundle.task_type is LLMTaskType.WATCHLIST_NOTE
    assert bundle.data_quality.price_data_status.value == "valid"


def test_llm_context_bundle_requires_data_quality() -> None:
    payload = _context_bundle_payload()
    del payload["data_quality"]

    with pytest.raises(ValidationError):
        LLMContextBundle.model_validate(payload)


def test_llm_context_bundle_rejects_invalid_data_quality_status() -> None:
    payload = _context_bundle_payload()
    payload["data_quality"]["price_data_status"] = "unknown"

    with pytest.raises(ValidationError):
        LLMContextBundle.model_validate(payload)


def test_llm_analysis_result_accepts_contract_payload() -> None:
    result = LLMAnalysisResult.model_validate(_analysis_result_payload())

    assert result.risk_level is RiskLevel.MEDIUM
    assert result.suggested_action is SuggestedAction.HOLD


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_llm_analysis_result_rejects_confidence_out_of_range(
    confidence: float,
) -> None:
    payload = _analysis_result_payload()
    payload["confidence"] = confidence

    with pytest.raises(ValidationError):
        LLMAnalysisResult.model_validate(payload)


@pytest.mark.parametrize("suggested_action", ["buy", "sell", "strong_buy"])
def test_llm_analysis_result_rejects_imperative_suggested_actions(
    suggested_action: str,
) -> None:
    payload = _analysis_result_payload()
    payload["suggested_action"] = suggested_action

    with pytest.raises(ValidationError):
        LLMAnalysisResult.model_validate(payload)


def test_llm_analysis_result_rejects_invalid_risk_level() -> None:
    payload = _analysis_result_payload()
    payload["risk_level"] = "critical"

    with pytest.raises(ValidationError):
        LLMAnalysisResult.model_validate(payload)


def test_llm_analysis_run_requires_input_context_json(db: Session) -> None:
    db.add(
        LLMAnalysisRun(
            user_id=1,
            task_type=LLMTaskType.WATCHLIST_NOTE.value,
            related_symbols=["NVDA"],
        )
    )

    with pytest.raises(IntegrityError):
        db.commit()


def test_llm_analysis_runs_migration_up_down() -> None:
    migration = _load_migration_module()
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        operations = Operations(context)
        original_op = getattr(migration, "op")
        setattr(migration, "op", operations)
        try:
            upgrade = getattr(migration, "upgrade")
            downgrade = getattr(migration, "downgrade")

            upgrade()
            inspector = inspect(connection)
            assert "llm_analysis_runs" in inspector.get_table_names()

            columns = {
                column["name"]: column
                for column in inspector.get_columns("llm_analysis_runs")
            }
            assert columns["input_context_json"]["nullable"] is False

            downgrade()
            inspector = inspect(connection)
            assert "llm_analysis_runs" not in inspector.get_table_names()
        finally:
            setattr(migration, "op", original_op)
