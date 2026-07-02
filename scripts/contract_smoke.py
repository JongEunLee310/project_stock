"""BE↔FE 응답 계약 정렬 smoke test.

실제 FastAPI 앱을 in-memory sqlite + TestClient(HTTP 계층)로 띄워, FE가 기대하는
필드가 라이브 응답에 실제로 존재하는지 검증한다. FastAPI `response_model`이 스키마
밖 필드를 제거하는 특성 탓에 스택 기동만 확인하는 smoke test로는 드러나지 않던
필드 단위 계약 불일치(BE #163 / FE #101에서 정렬)를 회귀 감시하는 용도다.

research-summary는 FE adapter 변환(stance 라벨·confidence 정규화)까지 재현해 화면
표시 값이 올바른지 확인한다.

실행:
    uv run python scripts/contract_smoke.py
"""

from __future__ import annotations

import json
import sys
from collections.abc import Generator
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.api.v1.deps import get_current_user  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.domains.alerts.service import AlertService  # noqa: E402
from app.domains.signals.repository import SignalRepository  # noqa: E402
from app.domains.users.model import User  # noqa: E402
from app.main import app  # noqa: E402

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

PASSED: list[str] = []
FAILED: list[str] = []

# FE adapter 재현 (project_stock_FE/src/features/research/adapters.ts,
# src/shared/lib/format/enumLabel.ts).
RESEARCH_STANCE_LABELS = {"BUY_CANDIDATE": "매수 후보", "WATCH": "관찰"}


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASSED if cond else FAILED).append(name)
    mark = "PASS" if cond else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"  [{mark}] {name}{suffix}")


def data(response: Any) -> Any:
    body = response.json()
    assert body["error"] is None, body
    return body["data"]


def fe_stance_label(wire: str | None) -> str:
    return RESEARCH_STANCE_LABELS.get(wire or "", "판단 보류")


def fe_confidence_percent(wire: str | None) -> float | None:
    if wire is None:
        return None
    try:
        return float(wire) * 100
    except ValueError:
        return None


def override_get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def set_current_user(user_id: int, email: str) -> None:
    def override() -> User:
        return User(id=user_id, email=email, hashed_password="smoke-hash")

    app.dependency_overrides[get_current_user] = override


def seed_alert(asset_id: int, user_id: int, client: TestClient) -> None:
    signal = data(
        client.post(
            "/api/v1/signals",
            json={
                "asset_id": asset_id,
                "signal_type": "RISK_ALERT",
                "score": 80,
                "risk_level": "HIGH",
                "reason": "Thesis conflict detected",
                "evidence": {"report_id": 1},
                "expires_at": "2026-12-31T00:00:00Z",
            },
        )
    )
    db = SessionLocal()
    try:
        signal_model = SignalRepository(db).get_by_id(signal["id"])
        assert signal_model is not None
        AlertService(db).create_alert(user_id, signal_model)
    finally:
        db.close()


def run() -> None:
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    print("\n== 1. GET /auth/me (username·created_at) — 실제 register/login ==")
    client.post(
        "/api/v1/auth/register",
        json={"email": "smoke@example.com", "password": "pw123456"},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "smoke@example.com", "password": "pw123456"},
    )
    token = data(login)["access_token"]
    me = data(
        client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    )
    print(json.dumps(me, ensure_ascii=False, indent=2))
    check("/auth/me has username", "username" in me, str(me.get("username")))
    check("/auth/me has created_at", "created_at" in me)
    check("username = email local-part", me.get("username") == "smoke")

    set_current_user(1, email="smoke@example.com")

    asset = data(
        client.post(
            "/api/v1/assets",
            json={
                "symbol": "AAPL",
                "name": "AAPL Inc.",
                "market": "NASDAQ",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "description": "Makes devices and services.",
            },
        )
    )
    aid = asset["id"]

    print("\n== 2. GET /assets (sector) ==")
    first = data(client.get("/api/v1/assets"))[0]
    check("/assets item has sector", "sector" in first, str(first.get("sector")))

    print("\n== 3. GET /assets/{id}/detail (market_cap·next_earnings_date·updated_at) ==")
    detail = data(client.get(f"/api/v1/assets/{aid}/detail"))
    print(json.dumps(detail, ensure_ascii=False, indent=2))
    check("detail has market_cap", "market_cap" in detail)
    check("detail has next_earnings_date", "next_earnings_date" in detail)
    check("detail has updated_at", "updated_at" in detail)
    check("detail dropped as_of", "as_of" not in detail)

    print("\n== 4. GET /assets/{id}/research-summary + FE 변환 ==")
    rs = data(client.get(f"/api/v1/assets/{aid}/research-summary"))
    print(json.dumps(rs, ensure_ascii=False, indent=2))
    for field in ("stance", "stance_confidence", "headline", "body", "key_risks"):
        check(f"research-summary has {field}", field in rs)
    check("research-summary has created_at", "created_at" in rs)
    check("research-summary dropped sources", "sources" not in rs)
    check("research-summary dropped positive_factors", "positive_factors" not in rs)
    label = fe_stance_label(rs.get("stance"))
    pct = fe_confidence_percent(rs.get("stance_confidence"))
    print(
        f"  FE 표시: stance '{rs.get('stance')}' -> '{label}', "
        f"confidence '{rs.get('stance_confidence')}' -> {pct}%"
    )
    check("FE stance label mapped (한글)", label in ("매수 후보", "관찰"), label)
    check("FE confidence 0~100 정규화", pct is not None and 0 <= pct <= 100, str(pct))

    print("\n== 5. GET /assets/{id}/buy-checklist (id·label·description·checked) ==")
    item = data(client.get(f"/api/v1/assets/{aid}/buy-checklist"))["items"][0]
    print(json.dumps(item, ensure_ascii=False, indent=2))
    for field in ("id", "label", "description", "checked"):
        check(f"buy-checklist item has {field}", field in item)
    check("buy-checklist dropped status", "status" not in item)

    print("\n== 6. GET /reports (title·source) ==")
    client.post(
        "/api/v1/reports",
        json={
            "asset_id": aid,
            "summary": "Services growth offsets softer hardware demand.",
            "positive_factors": ["Services revenue accelerated"],
            "negative_factors": ["Hardware demand remains soft"],
            "risk_level": "MEDIUM",
            "thesis_conflict_status": "SUPPORTS",
            "conflict_reason": "The news supports the active thesis.",
            "news_item_ids": [10],
        },
    )
    report = data(client.get("/api/v1/reports", params={"asset_id": aid}))[0]
    check("report has title", "title" in report, str(report.get("title")))
    check("report has source", "source" in report)

    print("\n== 7. GET /theses/latest (title) ==")
    client.post(
        "/api/v1/theses",
        json={
            "asset_id": aid,
            "summary": "Long-term compounder",
            "risk_factors": "Margin compression",
            "invalidation_conditions": "Revenue growth below 5%",
        },
    )
    thesis = data(client.get("/api/v1/theses/latest", params={"asset_id": aid}))
    check("thesis has title", "title" in thesis, str(thesis.get("title")))

    print("\n== 8. GET /alerts (title) ==")
    seed_alert(aid, user_id=1, client=client)
    alert = data(client.get("/api/v1/alerts"))[0]
    check("alert has title", "title" in alert, str(alert.get("title")))

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)

    print("\n" + "=" * 60)
    print(f"결과: {len(PASSED)} PASS / {len(FAILED)} FAIL")
    if FAILED:
        print("실패:", ", ".join(FAILED))
        raise SystemExit(1)
    print("모든 계약 정렬 항목이 라이브 응답에서 확인됨.")


if __name__ == "__main__":
    run()
