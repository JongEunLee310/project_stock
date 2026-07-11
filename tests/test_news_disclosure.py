from datetime import datetime, timezone
from typing import Any, cast

from fastapi.testclient import TestClient

from app.adapters.disclosure.base import DisclosureProvider, DisclosureResult
from app.domains.assets.model import Asset
from app.domains.news.model import NewsItem
from tests.conftest import TestingSessionLocal, api_data, api_error, set_current_user


class StubDisclosureProvider(DisclosureProvider):
    def fetch(self, symbols: list[str]) -> list[DisclosureResult]:
        assert symbols == ["AAPL"]
        return [
            DisclosureResult(
                symbol="AAPL",
                title="Older disclosure",
                url="https://example.com/disclosures/older",
                source="test-disclosure",
                published_at=datetime(2026, 6, 18, tzinfo=timezone.utc),
                payload={"kind": "filing"},
            ),
            DisclosureResult(
                symbol="AAPL",
                title="Latest disclosure",
                url="https://example.com/disclosures/latest",
                source="test-disclosure",
                published_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
                payload={"kind": "filing"},
            ),
        ]


def create_asset_with_news() -> int:
    with TestingSessionLocal() as db:
        asset = Asset(symbol="AAPL", name="Apple Inc.", market="NASDAQ")
        db.add(asset)
        db.commit()
        db.refresh(asset)
        db.add_all(
            [
                NewsItem(
                    asset_id=asset.id,
                    title="Older news",
                    url="https://example.com/news/older",
                    source="Example News",
                    published_at=datetime(2026, 6, 18, tzinfo=timezone.utc),
                    summary="Older summary",
                    category="MARKET",
                    impact_level="LOW",
                    sentiment="NEUTRAL",
                ),
                NewsItem(
                    asset_id=asset.id,
                    title="Latest news",
                    url="https://example.com/news/latest",
                    source="Example News",
                    published_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
                    summary="Latest summary",
                    category="PRODUCT",
                    impact_level="HIGH",
                    sentiment="POSITIVE",
                ),
            ]
        )
        db.commit()
        return asset.id


def test_get_news_disclosure_separates_news_and_disclosures(
    client: TestClient,
    monkeypatch: Any,
) -> None:
    set_current_user(1)
    asset_id = create_asset_with_news()
    monkeypatch.setattr(
        "app.domains.news.news_disclosure_service.get_disclosure_provider",
        lambda: StubDisclosureProvider(),
    )

    response = client.get(f"/api/v1/assets/{asset_id}/news-disclosure")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["asset_id"] == asset_id
    news_item = data["news"][0]
    assert isinstance(news_item["id"], int)
    assert {key: value for key, value in news_item.items() if key != "id"} == {
        "title": "Latest news",
        "url": "https://example.com/news/latest",
        "source": "Example News",
        "published_at": "2026-06-20T00:00:00Z",
        "summary": "Latest summary",
        "category": "PRODUCT",
        "impact_level": "HIGH",
        "sentiment": "POSITIVE",
    }
    assert data["disclosures"][0] == {
        "title": "Latest disclosure",
        "url": "https://example.com/disclosures/latest",
        "source": "test-disclosure",
        "published_at": "2026-06-20T00:00:00Z",
        "category": "OTHER",
        "impact_level": None,
        "summary": None,
    }


def test_get_news_disclosure_applies_limit_to_both_arrays(
    client: TestClient,
    monkeypatch: Any,
) -> None:
    set_current_user(1)
    asset_id = create_asset_with_news()
    monkeypatch.setattr(
        "app.domains.news.news_disclosure_service.get_disclosure_provider",
        lambda: StubDisclosureProvider(),
    )

    response = client.get(
        f"/api/v1/assets/{asset_id}/news-disclosure",
        params={"limit": 1},
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert [item["title"] for item in data["news"]] == ["Latest news"]
    assert [item["title"] for item in data["disclosures"]] == [
        "Latest disclosure"
    ]


def test_get_news_disclosure_returns_404_for_missing_asset(
    client: TestClient,
) -> None:
    set_current_user(1)

    response = client.get("/api/v1/assets/999/news-disclosure")

    assert response.status_code == 404
    assert api_error(response) == {
        "code": "ASSET_NOT_FOUND",
        "message": "종목을 찾을 수 없습니다.",
    }


def test_get_news_disclosure_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/assets/1/news-disclosure")

    assert response.status_code == 401
