"""Client for Coinbase Advanced Trade API using the official SDK."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

try:
    from coinbase.rest import RESTClient
except Exception as exc:  # pragma: no cover - import guard
    raise ImportError(
        "coinbase-advanced-py is required. Install it with `pip install coinbase-advanced-py`."
    ) from exc

_ = load_dotenv()


class CoinbaseAuthError(RuntimeError):
    """Raised when API credentials are missing."""


@dataclass
class AccountBalance:
    """Represents the balance of a specific account."""

    asset: str
    available_balance: float


@dataclass
class OrderResult:
    """Represents the result of placing an order."""

    order_id: str
    status: str
    filled_size: float | None
    avg_price: float | None


class CoinbaseClient:
    """Client wrapper around the official Coinbase Advanced Trade SDK."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_secret: str | None = None,
    ) -> None:
        self._api_key: str | None = api_key or os.getenv("COINBASE_API_KEY")
        self._api_secret: str | None = api_secret or os.getenv("COINBASE_API_SECRET")
        if not self._api_key or not self._api_secret:
            raise CoinbaseAuthError(
                "Coinbase API credentials are required. Set COINBASE_API_KEY and COINBASE_API_SECRET."
            )

        self._client = RESTClient(api_key=self._api_key, api_secret=self._api_secret)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    def get_accounts(self) -> list[AccountBalance]:
        """Return available account balances."""
        payload = self._client.get_accounts()
        data = _unwrap(payload)
        accounts = []
        for item in data.get("accounts", []):
            asset = item.get("asset")
            available = item.get("available_balance", {}).get("value")
            if asset and available is not None:
                accounts.append(
                    AccountBalance(asset=asset, available_balance=float(available))
                )
        return accounts

    def get_usdc_balance(self) -> float:
        """Return the available USDC balance."""
        for account in self.get_accounts():
            if account.asset.upper() == "USDC":
                return account.available_balance
        return 0.0

    def get_product_price(self, product_id: str) -> float:
        """Return the latest trade price for a product."""
        payload = self._client.get_market_ticker(product_id=product_id)
        data = _unwrap(payload)
        price = data.get("price")
        if price is None:
            raise RuntimeError(
                f"Ticker response missing price for {product_id}: {payload}"
            )
        return float(price)

    def place_market_buy(
        self, product_id: str, quote_size: float, client_order_id: str
    ) -> OrderResult:
        """Place a market IOC buy order with a quote size in USDC."""
        body = {
            "client_order_id": client_order_id,
            "product_id": product_id,
            "side": "BUY",
            "order_configuration": {
                "market_market_ioc": {
                    "quote_size": f"{quote_size:.2f}",
                }
            },
        }
        payload = self._client.create_order(**body)
        return self._parse_order_result(_unwrap(payload))

    def place_market_sell(
        self, product_id: str, base_size: float, client_order_id: str
    ) -> OrderResult:
        """Place a market IOC sell order for a base asset size."""
        body = {
            "client_order_id": client_order_id,
            "product_id": product_id,
            "side": "SELL",
            "order_configuration": {
                "market_market_ioc": {
                    "base_size": f"{base_size:.8f}",
                }
            },
        }
        payload = self._client.create_order(**body)
        return self._parse_order_result(_unwrap(payload))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _parse_order_result(self, payload: dict[str, Any]) -> OrderResult:
        success = payload.get("success", False)
        if not success:
            raise RuntimeError(f"Order failed: {payload}")

        filled_size = None
        avg_price = None
        if "fills" in payload:
            fills = payload["fills"]
            if fills:
                last_fill = fills[-1]
                filled_size = float(last_fill.get("size", 0.0))
                avg_price = float(last_fill.get("price", 0.0))

        return OrderResult(
            order_id=payload.get("order_id", ""),
            status=payload.get("order_status", "unknown"),
            filled_size=filled_size,
            avg_price=avg_price,
        )


def _unwrap(response: Any) -> dict[str, Any]:
    """Extract the raw payload from an SDK API response."""

    if isinstance(response, dict):
        return response
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if hasattr(data, "model_dump"):
        return data.model_dump()  # type: ignore[no-any-return]
    if hasattr(data, "dict"):
        return data.dict()  # type: ignore[no-any-return]
    if isinstance(data, list):
        return {"data": data}
    if data is not None:
        nested = getattr(data, "__dict__", None)
        if isinstance(nested, dict):
            return nested
    raw = getattr(response, "__dict__", None)
    if isinstance(raw, dict):
        return raw
    return {}
