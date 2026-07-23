from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from market_json.calendar import is_a_share_session
from market_json.huatai import HuataiClient, HuataiError, Stock


SCHEMA_VERSION = "1.0"
BEIJING = ZoneInfo("Asia/Shanghai")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _latest_success_at(output_dir: Path) -> str | None:
    latest = output_dir / "latest.json"
    if not latest.exists():
        return None
    try:
        return str(_read_json(latest).get("asOf") or "") or None
    except (OSError, ValueError, TypeError):
        return None


def _public_base_url() -> str:
    explicit = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    if "/" not in repository:
        return "https://OWNER.github.io/REPOSITORY"
    owner, name = repository.split("/", 1)
    if name.lower() == f"{owner.lower()}.github.io":
        return f"https://{owner}.github.io"
    return f"https://{owner}.github.io/{name}"


def _write_index_and_openapi(
    output_dir: Path,
    base_url: str,
    stocks: list[Stock],
    now: datetime,
) -> None:
    index = {
        "schemaVersion": SCHEMA_VERSION,
        "service": "huatai-pages-market-json",
        "updatedAt": now.isoformat(),
        "timezone": "Asia/Shanghai",
        "endpoints": {
            "latest": f"{base_url}/latest.json",
            "status": f"{base_url}/status.json",
            "openapi": f"{base_url}/openapi.yaml",
            "snapshots": f"{base_url}/snapshots/",
        },
        "watchlist": [
            {"stockName": stock.name, "stockCode": stock.stock_code, "exchange": stock.exchange}
            for stock in stocks
        ],
    }
    _write_json(output_dir / "index.json", index)
    openapi = f"""openapi: 3.1.0
info:
  title: Huatai A-share Market JSON
  version: "{SCHEMA_VERSION}"
  description: Read-only market snapshots for the configured seven-stock watchlist.
servers:
  - url: {base_url}
paths:
  /latest.json:
    get:
      operationId: getLatestMarketSnapshot
      summary: Get the latest complete Huatai quote snapshot
      responses:
        "200":
          description: Latest snapshot JSON
          content:
            application/json:
              schema:
                type: object
  /status.json:
    get:
      operationId: getMarketRefreshStatus
      summary: Get the most recent refresh status
      responses:
        "200":
          description: Refresh status JSON
          content:
            application/json:
              schema:
                type: object
"""
    (output_dir / "openapi.yaml").write_text(openapi, encoding="utf-8")
    (output_dir / ".nojekyll").touch()


def _prune_snapshots(output_dir: Path, retention_days: int) -> None:
    root = output_dir / "snapshots"
    if not root.exists():
        return
    dated = sorted(
        (path for path in root.iterdir() if path.is_dir() and len(path.name) == 10),
        key=lambda path: path.name,
        reverse=True,
    )
    for obsolete in dated[retention_days:]:
        shutil.rmtree(obsolete)


def refresh(
    config_path: Path,
    output_dir: Path,
    now: datetime | None = None,
    client: HuataiClient | None = None,
    session_checker=is_a_share_session,
) -> int:
    now = now or datetime.now(BEIJING)
    if now.tzinfo is None:
        now = now.replace(tzinfo=BEIJING)
    else:
        now = now.astimezone(BEIJING)

    config = _read_json(config_path)
    stocks = [Stock.from_dict(item) for item in config["stocks"]]
    if len(stocks) != 7:
        raise ValueError("watchlist must contain exactly seven stocks")
    retention_days = int(config.get("snapshotRetentionTradingDays", 90))
    analysis_query = str(config["analysisQuery"])
    base_url = _public_base_url()
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_index_and_openapi(output_dir, base_url, stocks, now)

    if not session_checker(now.date()):
        _write_json(
            output_dir / "status.json",
            {
                "schemaVersion": SCHEMA_VERSION,
                "state": "market_closed",
                "attemptedAt": now.isoformat(),
                "marketDate": now.date().isoformat(),
                "latestSuccessAt": _latest_success_at(output_dir),
                "message": "A 股休市，未抓取且未覆盖 latest.json。",
            },
        )
        return 0

    if client is None:
        client = HuataiClient(
            api_key=os.getenv("HT_APIKEY", ""),
            service_url=os.getenv("HT_SERVICE_URL", "https://ai.zhangle.com"),
            base_url=os.getenv("HT_BASE_URL", "/edge/entry/gate"),
        )

    quotes, quote_errors = client.get_quotes(stocks)
    analysis_markdown: str | None = None
    analysis_error: str | None = None
    try:
        analysis_markdown = client.query_indicator(analysis_query)
    except HuataiError as exc:
        analysis_error = str(exc)

    if quote_errors or len(quotes) != len(stocks):
        errors = quote_errors or ["结构化行情返回数量不足"]
        if analysis_error:
            errors.append(f"analysis: {analysis_error}")
        _write_json(
            output_dir / "status.json",
            {
                "schemaVersion": SCHEMA_VERSION,
                "state": "failed",
                "attemptedAt": now.isoformat(),
                "marketDate": now.date().isoformat(),
                "latestSuccessAt": _latest_success_at(output_dir),
                "quoteCount": len(quotes),
                "errors": errors,
                "message": "本次结构化行情不完整，未覆盖 latest.json。",
            },
        )
        return 1

    state = "ok" if analysis_error is None else "ok_with_analysis_error"
    snapshot = {
        "schemaVersion": SCHEMA_VERSION,
        "status": state,
        "asOf": now.isoformat(),
        "marketDate": now.date().isoformat(),
        "timezone": "Asia/Shanghai",
        "source": {
            "provider": "Huatai Securities",
            "structuredTool": "a-share-paper-trading.getQuote",
            "analysisTool": "query-indicator.queryIndicator",
        },
        "quotes": quotes,
        "analysis": {
            "query": analysis_query,
            "answerMarkdown": analysis_markdown,
            "error": analysis_error,
        },
    }
    _write_json(output_dir / "latest.json", snapshot)
    snapshot_path = (
        output_dir
        / "snapshots"
        / now.date().isoformat()
        / f"{now.strftime('%H%M%S')}.json"
    )
    _write_json(snapshot_path, snapshot)
    _prune_snapshots(output_dir, retention_days)
    _write_json(
        output_dir / "status.json",
        {
            "schemaVersion": SCHEMA_VERSION,
            "state": state,
            "attemptedAt": now.isoformat(),
            "marketDate": now.date().isoformat(),
            "latestSuccessAt": now.isoformat(),
            "quoteCount": len(quotes),
            "snapshot": str(snapshot_path.relative_to(output_dir)).replace("\\", "/"),
            "analysisError": analysis_error,
        },
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish Huatai quotes as static JSON.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/watchlist.json"),
        help="Watchlist JSON path.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("public"),
        help="GitHub Pages output directory.",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    try:
        exit_code = refresh(args.config, args.output)
    except Exception as exc:
        print(f"refresh failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()

