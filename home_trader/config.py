"""Configuration models for the trading agent."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import List, Sequence


DEFAULT_FORBIDDEN_PRODUCTS: Sequence[str] = ("SOL", "SUI", "BTC", "ETH")


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for communicating with the local LLM served by Ollama."""

    model: str = "llama3"
    endpoint: str = "http://localhost:11434/api/generate"
    temperature: float = 0.2


@dataclass(frozen=True)
class TradingConstraints:
    """Fixed operational constraints for the trading agent."""

    max_runtime: timedelta = timedelta(hours=5)
    profit_target_usdc: float = 50.0
    max_transactions: int = 15
    max_purchase_usdc: float = 200.0
    forbidden_products: Sequence[str] = field(default_factory=lambda: list(DEFAULT_FORBIDDEN_PRODUCTS))


@dataclass(frozen=True)
class JournalConfig:
    """Parameters for journaling trade activity."""

    directory: Path = Path("journals")
    prefix: str = "journal"
    extension: str = ".md"


@dataclass(frozen=True)
class AgentConfig:
    """Aggregate configuration for the trading agent."""

    llm: LLMConfig = LLMConfig()
    constraints: TradingConstraints = TradingConstraints()
    journal: JournalConfig = JournalConfig()
    polling_interval_seconds: int = 60

    @property
    def forbidden_products(self) -> List[str]:
        return [p.upper() for p in self.constraints.forbidden_products]
