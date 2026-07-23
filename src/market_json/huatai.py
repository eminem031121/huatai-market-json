from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


PAPER_TRADING_SKILL_CODE = "mx_1778741794549"
QUERY_INDICATOR_SKILL_CODE = "mx_1779108020995"


class HuataiError(RuntimeError):
    """A safe-to-publish Huatai API error."""


@dataclass(frozen=True)
class Stock:
    name: str
    stock_code: str
    exchange: str

    @classmethod
    def from_dict(cls, item: dict[str, Any]) -> "Stock":
        return cls(
            name=str(item["name"]),
            stock_code=str(item["stockCode"]),
            exchange=str(item["exchange"]),
        )


class HuataiClient:
    def __init__(
        self,
        api_key: str,
        service_url: str = "https://ai.zhangle.com",
        base_url: str = "/edge/entry/gate",
        timeout_seconds: float = 15,
    ) -> None:
        if not api_key.strip():
            raise ValueError("HT_APIKEY is required")
        self.api_key = api_key
        self.service_url = service_url.rstrip("/")
        self.base_url = "/" + base_url.strip("/")
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        retry = Retry(
            total=2,
            connect=2,
            read=2,
            status=2,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"POST"}),
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def _post(
        self,
        path: str,
        body: dict[str, Any],
        skill_code: str,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        url = f"{self.service_url}{self.base_url}{path}"
        headers = {
            "apiKey": self.api_key,
            "skillCode": skill_code,
            "Content-Type": "application/json",
        }
        try:
            response = self.session.post(
                url,
                json=body,
                headers=headers,
                timeout=timeout_seconds or self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.Timeout as exc:
            raise HuataiError("华泰接口调用超时") from exc
        except requests.ConnectionError as exc:
            raise HuataiError("无法连接华泰接口") from exc
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            raise HuataiError(f"华泰接口返回 HTTP {status}") from exc
        except ValueError as exc:
            raise HuataiError("华泰接口返回了无法解析的 JSON") from exc
        except requests.RequestException as exc:
            raise HuataiError("华泰接口网络请求失败") from exc
        if not isinstance(payload, dict):
            raise HuataiError("华泰接口返回结构不是 JSON 对象")
        return payload

    def get_quote(self, stock: Stock) -> dict[str, Any]:
        payload = self._post(
            "/api/simSkills/getQuote",
            {"stockCode": stock.stock_code, "exchange": stock.exchange},
            PAPER_TRADING_SKILL_CODE,
        )
        if payload.get("ok") is not True or not isinstance(payload.get("data"), dict):
            error = payload.get("error") or {}
            message = error.get("message") or "行情查询失败"
            raise HuataiError(f"{stock.name}: {message}")

        quote = dict(payload["data"])
        quote["stockCode"] = stock.stock_code
        quote["exchange"] = stock.exchange
        quote.setdefault("stockName", stock.name)
        current = quote.get("currentPrice")
        previous = quote.get("prevClose")
        if isinstance(current, (int, float)) and isinstance(previous, (int, float)) and previous:
            quote["changePctCalculated"] = round((current - previous) / previous * 100, 4)
        else:
            quote["changePctCalculated"] = None
        return quote

    def get_quotes(
        self,
        stocks: list[Stock],
        max_workers: int = 4,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        quotes_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        errors: list[str] = []
        with ThreadPoolExecutor(max_workers=min(max_workers, len(stocks))) as executor:
            futures = {executor.submit(self.get_quote, stock): stock for stock in stocks}
            for future in as_completed(futures):
                stock = futures[future]
                try:
                    quote = future.result()
                    quotes_by_key[(stock.stock_code, stock.exchange)] = quote
                except Exception as exc:
                    message = str(exc) if isinstance(exc, HuataiError) else f"{stock.name}: 未知错误"
                    errors.append(message)
        ordered = [
            quotes_by_key[(stock.stock_code, stock.exchange)]
            for stock in stocks
            if (stock.stock_code, stock.exchange) in quotes_by_key
        ]
        return ordered, errors

    def query_indicator(self, query: str) -> str:
        payload = self._post(
            "/api/finAnalysis/queryIndicator",
            {"query": query},
            QUERY_INDICATOR_SKILL_CODE,
            timeout_seconds=60,
        )
        if payload.get("code") != 0:
            message = payload.get("message") or "分时与成交量查询失败"
            raise HuataiError(str(message))
        answer = payload.get("data", {}).get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise HuataiError("分时与成交量查询未返回文本")
        return answer

