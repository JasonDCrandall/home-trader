"""Utilities for managing the trading journal."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


@dataclass
class Journal:
    """Represents the journal file tracking all trade activity."""

    path: Path

    def log_header(self, metadata: Dict[str, Any]) -> None:
        """Initialize the journal with a header containing session metadata."""
        if not self.path.exists():
            header_lines = [
                f"# Trading Journal - {metadata.get('session_id', 'unknown')}\n",
                "\n",
                f"Start Time: {metadata.get('start_time')}\n",
                f"Max Runtime: {metadata.get('max_runtime')}\n",
                f"Profit Target (USDC): {metadata.get('profit_target_usdc')}\n",
                f"Max Transactions: {metadata.get('max_transactions')}\n",
                f"Max Purchase (USDC): {metadata.get('max_purchase_usdc')}\n",
                f"Forbidden Products: {', '.join(metadata.get('forbidden_products', []))}\n",
                "\n",
            ]
            self.path.write_text("".join(header_lines), encoding="utf-8")

    def append_entry(self, heading: str, content: str) -> None:
        """Append a markdown-formatted entry to the journal."""
        timestamp = datetime.utcnow().isoformat()
        entry_lines = [
            f"## {heading} ({timestamp} UTC)\n",
            "\n",
            f"{content}\n",
            "\n",
        ]
        with self.path.open("a", encoding="utf-8") as handle:
            handle.writelines(entry_lines)

    def append_transaction(self, transaction: Dict[str, Any]) -> None:
        """Append a transaction record to the journal."""
        details = "\n".join(f"- **{key}**: {value}" for key, value in transaction.items())
        self.append_entry("Transaction", details)

    def append_decision(self, decision: str, rationale: str) -> None:
        """Log the LLM's decision and rationale."""
        content = f"- **Decision**: {decision}\n- **Rationale**: {rationale}"
        self.append_entry("Decision", content)

    def read_contents(self) -> str:
        """Read the entire journal contents for use as LLM context."""
        if self.path.exists():
            return self.path.read_text(encoding="utf-8")
        return ""


def create_journal(directory: Path, prefix: str, extension: str) -> Journal:
    """Create a journal file with a timestamped name."""
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    filename = f"{prefix}_{timestamp}{extension}"
    path = directory / filename
    return Journal(path=path)
