"""Entry point for running the trading agent."""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from .config import AgentConfig
from .journal import create_journal
from .trading_agent import TradingAgent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Autonomous crypto trading agent")
    parser.add_argument(
        "--model",
        default=AgentConfig().llm.model,
        help="Name of the Ollama model to use",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=AgentConfig().polling_interval_seconds,
        help="Seconds to wait between decision cycles",
    )
    parser.add_argument(
        "--journal-dir",
        type=Path,
        default=AgentConfig().journal.directory,
        help="Directory where journal files are stored",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = AgentConfig()
    config = replace(config, polling_interval_seconds=args.poll_interval)
    config = replace(config, llm=replace(config.llm, model=args.model))
    config = replace(config, journal=replace(config.journal, directory=args.journal_dir))

    journal = create_journal(config.journal.directory, config.journal.prefix, config.journal.extension)
    agent = TradingAgent(config)
    agent.initialize_session(journal)
    agent.run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
