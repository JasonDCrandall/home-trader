"""Core trading agent orchestration."""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .coinbase_client import CoinbaseClient
from .config import AgentConfig
from .journal import Journal
from .llm import LLMDecisionMaker


@dataclass
class MarketSnapshot:
    """Represents the market context forwarded to the LLM."""

    usdc_balance: float
    open_positions: Dict[str, float]
    candidate_products: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "usdc_balance": self.usdc_balance,
            "open_positions": self.open_positions,
            "candidate_products": self.candidate_products,
        }


@dataclass
class TradeLedger:
    """Tracks realized profit and transaction count."""

    net_profit_usdc: float = 0.0
    transactions: List[Dict[str, Any]] = field(default_factory=list)

    def register_trade(self, trade: Dict[str, Any]) -> None:
        self.transactions.append(trade)
        delta = float(trade.get("net_delta_usdc", 0.0))
        self.net_profit_usdc += delta

    @property
    def transaction_count(self) -> int:
        return len(self.transactions)


class TradingAgent:
    """Coordinates Coinbase, the LLM, and the journal to run trades."""

    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._llm = LLMDecisionMaker(config.llm)
        self._client = CoinbaseClient()
        self._ledger = TradeLedger()
        self._journal: Optional[Journal] = None
        self._start_time: Optional[float] = None

    def initialize_session(self, journal: Journal) -> None:
        self._journal = journal
        self._start_time = time.time()
        metadata = {
            "session_id": str(uuid.uuid4()),
            "start_time": datetime.utcnow().isoformat(),
            "max_runtime": str(self._config.constraints.max_runtime),
            "profit_target_usdc": self._config.constraints.profit_target_usdc,
            "max_transactions": self._config.constraints.max_transactions,
            "max_purchase_usdc": self._config.constraints.max_purchase_usdc,
            "forbidden_products": self._config.forbidden_products,
        }
        journal.log_header(metadata)
        journal.append_entry("Session Started", json.dumps(metadata, indent=2))

    def run(self) -> None:
        if not self._journal or self._start_time is None:
            raise RuntimeError("Session not initialized. Call initialize_session first.")

        while True:
            reason = self._stop_reason()
            if reason:
                self._journal.append_entry("Session Complete", reason)
                break

            snapshot = self._build_market_snapshot()
            constraints = self._build_constraints_payload()
            decision = self._llm.decide(
                journal_contents=self._journal.read_contents(),
                market_snapshot=snapshot.to_dict(),
                constraints=constraints,
            )
            self._journal.append_decision(decision.action, decision.rationale)

            if decision.action == "hold":
                time.sleep(self._config.polling_interval_seconds)
                continue

            if not decision.product_id:
                self._journal.append_entry(
                    "Decision Skipped",
                    "LLM suggested a trade without specifying a product. Action ignored.",
                )
                time.sleep(self._config.polling_interval_seconds)
                continue

            product_id = decision.product_id.upper()
            if not product_id.endswith("-USDC"):
                product_id = f"{product_id}-USDC"

            if not self._validate_decision(decision, product_id):
                time.sleep(self._config.polling_interval_seconds)
                continue

            trade_result = self._execute_trade(decision, product_id)
            if trade_result:
                self._ledger.register_trade(trade_result)
                self._journal.append_transaction(trade_result)

                reason = self._stop_reason()
                if reason:
                    self._journal.append_entry("Session Complete", reason)
                    break

            time.sleep(self._config.polling_interval_seconds)

    def _stop_reason(self) -> Optional[str]:
        assert self._start_time is not None
        elapsed = time.time() - self._start_time
        constraints = self._config.constraints
        if elapsed >= constraints.max_runtime.total_seconds():
            return "Max runtime reached."
        if self._ledger.transaction_count >= constraints.max_transactions:
            return "Max transaction count reached."
        if self._ledger.net_profit_usdc >= constraints.profit_target_usdc:
            return "Profit target achieved."
        return None

    def _build_constraints_payload(self) -> Dict[str, Any]:
        c = self._config.constraints
        return {
            "max_runtime_hours": c.max_runtime.total_seconds() / 3600,
            "profit_target_usdc": c.profit_target_usdc,
            "max_transactions": c.max_transactions,
            "max_purchase_usdc": c.max_purchase_usdc,
            "forbidden_products": self._config.forbidden_products,
            "remaining_transactions": c.max_transactions - self._ledger.transaction_count,
            "current_profit_usdc": self._ledger.net_profit_usdc,
        }

    def _build_market_snapshot(self) -> MarketSnapshot:
        accounts = self._client.get_accounts()
        usdc_balance = next((a.available_balance for a in accounts if a.asset.upper() == "USDC"), 0.0)
        candidate_products = self._discover_candidate_products(accounts)
        open_positions = self._estimate_positions(accounts, candidate_products)
        return MarketSnapshot(
            usdc_balance=usdc_balance,
            candidate_products=candidate_products,
            open_positions=open_positions,
        )

    def _discover_candidate_products(self, accounts: List[Any]) -> List[str]:
        products = set()
        for account in accounts:
            asset = account.asset.upper()
            if asset in self._config.forbidden_products or asset == "USDC":
                continue
            products.add(f"{asset}-USDC")
        return sorted(products)

    def _estimate_positions(self, accounts: List[Any], products: List[str]) -> Dict[str, float]:
        holdings: Dict[str, float] = {}
        for account in accounts:
            asset = account.asset.upper()
            if asset in self._config.forbidden_products or asset == "USDC":
                continue
            holdings[asset] = account.available_balance
        return {product: holdings.get(product.split("-")[0], 0.0) for product in products}

    def _validate_decision(self, decision, product_id: str) -> bool:
        constraints = self._config.constraints
        if product_id.split("-")[0] in self._config.forbidden_products:
            self._journal.append_entry("Decision Rejected", f"Product {product_id} is forbidden.")
            return False

        if self._ledger.transaction_count >= constraints.max_transactions:
            self._journal.append_entry("Decision Rejected", "Max transaction count reached.")
            return False

        if decision.action not in {"buy", "sell"}:
            self._journal.append_entry("Decision Rejected", f"Unsupported action: {decision.action}")
            return False

        if decision.amount_usdc is None or decision.amount_usdc <= 0:
            self._journal.append_entry("Decision Rejected", "Invalid trade size specified.")
            return False

        if decision.action == "buy" and decision.amount_usdc > constraints.max_purchase_usdc:
            self._journal.append_entry(
                "Decision Rejected",
                f"Buy size {decision.amount_usdc} exceeds max purchase limit {constraints.max_purchase_usdc}",
            )
            return False

        if decision.action == "buy":
            balance = self._client.get_usdc_balance()
            if decision.amount_usdc > balance:
                self._journal.append_entry("Decision Rejected", "Insufficient USDC balance for purchase.")
                return False
        else:
            base_asset = product_id.split("-")[0]
            accounts = self._client.get_accounts()
            base_balance = next((a.available_balance for a in accounts if a.asset.upper() == base_asset), 0.0)
            price = self._client.get_product_price(product_id)
            required_base = decision.amount_usdc / price
            if required_base > base_balance:
                self._journal.append_entry(
                    "Decision Rejected",
                    f"Insufficient {base_asset} balance for sale. Need {required_base:.8f}, have {base_balance:.8f}.",
                )
                return False

        return True

    def _execute_trade(self, decision, product_id: str) -> Optional[Dict[str, Any]]:
        order_id = str(uuid.uuid4())
        if decision.action == "buy":
            result = self._client.place_market_buy(product_id, decision.amount_usdc, order_id)
            net_delta = -decision.amount_usdc
        else:
            price = self._client.get_product_price(product_id)
            base_size = decision.amount_usdc / price
            result = self._client.place_market_sell(product_id, base_size, order_id)
            net_delta = decision.amount_usdc

        trade_record = {
            "order_id": result.order_id,
            "status": result.status,
            "product_id": product_id,
            "action": decision.action,
            "amount_usdc": decision.amount_usdc,
            "filled_size": result.filled_size,
            "avg_price": result.avg_price,
            "net_delta_usdc": net_delta,
            "timestamp": datetime.utcnow().isoformat(),
        }
        return trade_record
