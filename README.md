# home-trader

Autonomous crypto trading agent that coordinates a local Ollama model with Coinbase Advanced Trade.

## Features

- Creates a timestamped journal for each run and records every LLM decision and executed trade.
- Sends the entire journal contents to the local LLM so decisions always include prior context.
- Trades exclusively against USDC, observing a 5 hour max runtime, 15 trade cap, and $200 per-buy limit.
- Skips forbidden assets (SOL, SUI, BTC, ETH) automatically.
- Targets $50 net profit before shutting down early.

## Prerequisites

1. Python 3.10+
2. A running [Ollama](https://ollama.ai/) instance with an available model (default: `llama3`).
3. Coinbase Advanced Trade API key and secret with trading permissions.

Install dependencies:

```bash
pip install -r requirements.txt
```

Export your Coinbase credentials so the agent can authenticate:

```bash
export COINBASE_API_KEY="your_api_key"
export COINBASE_API_SECRET="your_api_secret"
```

> **Security note:** Never commit API credentials. Consider using a dedicated restricted key for the agent.

## Usage

Run the agent from the repository root:

```bash
python -m home_trader.main \
  --model llama3 \
  --poll-interval 120 \
  --journal-dir journals
```

Arguments:

- `--model`: Ollama model name (default: `llama3`).
- `--poll-interval`: Seconds to wait between decision cycles (default: 60).
- `--journal-dir`: Directory where session journals are stored (default: `journals/`).

Each run creates a markdown journal inside the chosen directory. The file captures session metadata, every LLM decision, and the result of any trade placed via Coinbase. When the agent reaches the $50 profit target, hits the 15-trade cap, or runs for 5 hours, it automatically terminates.

## Architecture Overview

- `home_trader/config.py`: Dataclasses for agent, LLM, constraint, and journal configuration.
- `home_trader/journal.py`: Journal creation and logging helpers.
- `home_trader/llm.py`: Wrapper for calling the local Ollama API and parsing structured decisions.
- `home_trader/coinbase_client.py`: Minimal Coinbase Advanced Trade REST client (USDC quote enforced).
- `home_trader/trading_agent.py`: Main orchestration loop enforcing runtime and trading rules.
- `home_trader/main.py`: CLI entry point that wires everything together.

## Important Constraints

The agent strictly enforces the following rules on every decision:

1. Maximum runtime: 5 hours per session.
2. Profit target: exit after netting at least 50 USDC.
3. Trade limit: no more than 15 total transactions.
4. Purchase cap: individual buy orders cannot exceed 200 USDC.
5. Asset restrictions: SOL, SUI, BTC, and ETH are never traded.
6. Journal coverage: every trade and decision is written to the session journal, and the complete journal is sent to the LLM each cycle.

These guardrails ensure the program operates safely within the requirements stated in the project brief.
