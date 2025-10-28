"""Client for Coinbase Advanced Trade API."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import Any

import requests

_ = load_dotenv()

API_BASE_URL = "https://api.coinbase.com/api/v3/brokerage"


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
    """Minimal client for the Coinbase Advanced Trade REST API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_secret: str | None = None,
        base_url: str = API_BASE_URL,
    ) -> None:
        self._api_key: str | None = api_key or os.getenv("COINBASE_API_KEY")
        self._api_secret: str | ReadableBuffer | None = api_secret or os.getenv(
            "COINBASE_API_SECRET"
        )
        self._base_url: str = base_url.rstrip("/")
        if not self._api_key or not self._api_secret:
            raise CoinbaseAuthError(
                "Coinbase API credentials are required. Set COINBASE_API_KEY and COINBASE_API_SECRET."
            )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    def get_accounts(self) -> list[AccountBalance]:
        """Return available account balances."""
        payload = self._request("GET", "/accounts")
        accounts = []
        for item in payload.get("accounts", []):
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
        payload = self._request("GET", f"/products/{product_id}/ticker")
        price = payload.get("price")
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
        payload = self._request("POST", "/orders", body)
        return self._parse_order_result(payload)

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
        payload = self._request("POST", "/orders", body)
        return self._parse_order_result(payload)

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

    def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        timestamp = str(int(time.time()))
        body_json = json.dumps(body) if body else ""
        prehash = f"{timestamp}{method.upper()}{path}{body_json}"
        signature = hmac.new(
            base64.b64decode(self._api_secret), prehash.encode(), hashlib.sha256
        ).digest()
        signature_b64 = base64.b64encode(signature).decode()

        headers = {
            "CB-ACCESS-KEY": self._api_key,
            "CB-ACCESS-SIGN": signature_b64,
            "CB-ACCESS-TIMESTAMP": timestamp,
            "Content-Type": "application/json",
        }

        response = requests.request(
            method, url, headers=headers, data=body_json if body else None, timeout=30
        )
        response.raise_for_status()
        return response.json()
