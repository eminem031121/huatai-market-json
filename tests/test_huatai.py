from __future__ import annotations

from market_json.huatai import HuataiClient, Stock


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self):
        return {
            "ok": True,
            "data": {
                "stockName": "沪电股份",
                "currentPrice": 105.0,
                "prevClose": 100.0,
                "change": 5.0,
            },
        }


def test_get_quote_adds_identity_and_calculated_change(monkeypatch) -> None:
    client = HuataiClient("test-key")
    monkeypatch.setattr(client.session, "post", lambda *args, **kwargs: FakeResponse())

    quote = client.get_quote(Stock("沪电股份", "002463", "SZ"))

    assert quote["stockCode"] == "002463"
    assert quote["exchange"] == "SZ"
    assert quote["changePctCalculated"] == 5.0

