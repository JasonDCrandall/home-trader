"""Tools for interacting with a local Ollama model."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

from .config import LLMConfig


@dataclass
class LLMDecision:
    """Represents a structured response from the LLM."""

    action: str
    product_id: Optional[str]
    amount_usdc: Optional[float]
    rationale: str


class LLMDecisionMaker:
    """Wrapper around the Ollama HTTP API for trading decisions."""

    def __init__(self, config: LLMConfig) -> None:
        self._config = config

    def decide(self, *, journal_contents: str, market_snapshot: Dict[str, Any], constraints: Dict[str, Any]) -> LLMDecision:
        """Ask the LLM for a decision based on the journal and market snapshot."""
        prompt = self._build_prompt(journal_contents, market_snapshot, constraints)
        payload = {
            "model": self._config.model,
            "prompt": prompt,
            "options": {"temperature": self._config.temperature},
            "stream": False,
        }
        response = requests.post(self._config.endpoint, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        raw_reply = data.get("response") or data.get("message") or ""
        return self._parse_response(raw_reply)

    def _build_prompt(self, journal_contents: str, market_snapshot: Dict[str, Any], constraints: Dict[str, Any]) -> str:
        """Build the prompt sent to the LLM."""
        constraints_text = json.dumps(constraints, indent=2)
        snapshot_text = json.dumps(market_snapshot, indent=2)
        prompt = f"""
You are an autonomous crypto trading strategist.

Session constraints:
{constraints_text}

Recent market snapshot:
{snapshot_text}

Trading journal:
{journal_contents}

Respond with strict JSON using the schema:
{{
  "action": "buy" | "sell" | "hold",
  "product_id": string | null,
  "amount_usdc": number | null,
  "rationale": string
}}

Explain your reasoning in the rationale field. Respect every constraint. Return `hold` when unsure.
"""
        return prompt.strip()

    def _parse_response(self, reply: str) -> LLMDecision:
        """Parse the LLM response into a :class:`LLMDecision`."""
        try:
            data = json.loads(reply)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive programming
            raise ValueError(f"LLM returned non-JSON response: {reply}") from exc

        action = (data.get("action") or "hold").lower()
        product_id = data.get("product_id")
        amount_usdc = data.get("amount_usdc")
        rationale = data.get("rationale") or "No rationale provided."

        if amount_usdc is not None:
            try:
                amount_usdc = float(amount_usdc)
            except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
                raise ValueError(f"Invalid amount_usdc: {amount_usdc}") from exc

        return LLMDecision(action=action, product_id=product_id, amount_usdc=amount_usdc, rationale=rationale)
