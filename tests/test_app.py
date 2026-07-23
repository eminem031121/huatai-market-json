from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from market_json.app import refresh
from market_json.huatai import Stock


BEIJING = ZoneInfo("Asia/Shanghai")


class FakeClient:
    def __init__(self, fail_code: str | None = None, fail_analysis: bool = False) -> None:
        self.fail_code = fail_code
        self.fail_analysis = fail_analysis

    def get_quotes(self, stocks: list[Stock]):
        quotes = []
        errors = []
        for stock in stocks:
            if stock.stock_code == self.fail_code:
                errors.append(f"{stock.name}: simulated failure")
                continue
            quotes.append(
                {
                    "stockName": stock.name,
                    "stockCode": stock.stock_code,
                    "exchange": stock.exchange,
                    "currentPrice": 10.5,
                    "prevClose": 10.0,
                    "changePctCalculated": 5.0,
                }
            )
        return quotes, errors

    def query_indicator(self, query: str) -> str:
        if self.fail_analysis:
            from market_json.huatai import HuataiError

            raise HuataiError("simulated analysis failure")
        return "分时与成交量补充结果"


def _config(tmp_path: Path) -> Path:
    stocks = [
        {"name": f"股票{i}", "stockCode": f"{i:06d}", "exchange": "SZ"}
        for i in range(1, 8)
    ]
    path = tmp_path / "watchlist.json"
    path.write_text(
        json.dumps(
            {
                "stocks": stocks,
                "analysisQuery": "查询七只股票的分时与成交量",
                "snapshotRetentionTradingDays": 90,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_success_writes_latest_snapshot_and_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.github.io/market")
    output = tmp_path / "public"
    now = datetime(2026, 7, 23, 14, 31, tzinfo=BEIJING)

    result = refresh(
        _config(tmp_path),
        output,
        now=now,
        client=FakeClient(),
        session_checker=lambda _: True,
    )

    assert result == 0
    latest = json.loads((output / "latest.json").read_text(encoding="utf-8"))
    status = json.loads((output / "status.json").read_text(encoding="utf-8"))
    assert len(latest["quotes"]) == 7
    assert latest["analysis"]["answerMarkdown"] == "分时与成交量补充结果"
    assert status["state"] == "ok"
    assert (output / "snapshots" / "2026-07-23" / "143100.json").exists()
    assert "https://example.github.io/market" in (output / "openapi.yaml").read_text()


def test_holiday_preserves_existing_latest(tmp_path: Path) -> None:
    output = tmp_path / "public"
    output.mkdir()
    original = {"asOf": "2026-07-22T14:36:00+08:00", "quotes": [1]}
    (output / "latest.json").write_text(json.dumps(original), encoding="utf-8")

    result = refresh(
        _config(tmp_path),
        output,
        now=datetime(2026, 7, 25, 14, 31, tzinfo=BEIJING),
        client=FakeClient(),
        session_checker=lambda _: False,
    )

    assert result == 0
    assert json.loads((output / "latest.json").read_text()) == original
    status = json.loads((output / "status.json").read_text(encoding="utf-8"))
    assert status["state"] == "market_closed"


def test_partial_quote_failure_does_not_overwrite_latest(tmp_path: Path) -> None:
    output = tmp_path / "public"
    output.mkdir()
    original = {"asOf": "previous", "quotes": [1]}
    (output / "latest.json").write_text(json.dumps(original), encoding="utf-8")

    result = refresh(
        _config(tmp_path),
        output,
        now=datetime(2026, 7, 23, 14, 36, tzinfo=BEIJING),
        client=FakeClient(fail_code="000003"),
        session_checker=lambda _: True,
    )

    assert result == 1
    assert json.loads((output / "latest.json").read_text()) == original
    status = json.loads((output / "status.json").read_text(encoding="utf-8"))
    assert status["state"] == "failed"
    assert status["quoteCount"] == 6


def test_analysis_failure_keeps_structured_snapshot(tmp_path: Path) -> None:
    output = tmp_path / "public"
    result = refresh(
        _config(tmp_path),
        output,
        now=datetime(2026, 7, 23, 14, 36, tzinfo=BEIJING),
        client=FakeClient(fail_analysis=True),
        session_checker=lambda _: True,
    )

    assert result == 0
    latest = json.loads((output / "latest.json").read_text(encoding="utf-8"))
    assert latest["status"] == "ok_with_analysis_error"
    assert latest["analysis"]["answerMarkdown"] is None

