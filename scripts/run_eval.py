"""CLI entry point for running the eval-dag system.

Usage:
    py scripts/run_eval.py --dataset path/to/data.json [--metadata path/to/meta.json]
    py scripts/run_eval.py --dataset path/to/data.json --output results.json

Requires OPENAI_API_KEY — set it in a .env file at the project root or in the environment.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Allow running from repo root without install
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Load .env file from project root (if it exists) before anything else reads env vars.
# This means OPENAI_API_KEY in .env is picked up by LangChain/OpenAI automatically.
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(dotenv_path=_env_path, override=False)  # override=False: real env vars win
except ImportError:
    pass  # python-dotenv not installed — fall back to os.environ only


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )


def load_json(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the eval-dag evaluation pipeline")
    parser.add_argument(
        "--dataset",
        required=True,
        help="Path to the dataset JSON file (dict of keys -> data)",
    )
    parser.add_argument(
        "--metadata",
        default=None,
        help="Path to optional metadata JSON file (description, domain, etc.)",
    )
    parser.add_argument(
        "--output",
        default="eval_results.json",
        help="Path to write the final report JSON (default: eval_results.json)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger("run_eval")

    if not os.environ.get("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY environment variable is not set")
        sys.exit(1)

    # Load inputs
    logger.info(f"Loading dataset from {args.dataset}")
    dataset = load_json(args.dataset)

    metadata: dict = {}
    if args.metadata:
        logger.info(f"Loading metadata from {args.metadata}")
        metadata = load_json(args.metadata)

    # Import here so top-level module errors surface cleanly
    from eval_dag.graphs import orchestrator

    logger.info("Starting evaluation pipeline...")
    final_state = orchestrator.invoke({
        "dataset": dataset,
        "metadata": metadata,
        "questions": [],
        "completed_results": [],
        "failed_questions": [],
        "final_report": {},
        "messages": [],
    })

    report = final_state["final_report"]
    summary = report.get("summary", {})

    logger.info(
        f"Done. {summary.get("successful_executions", 0)}/{summary.get("total_questions", 0)} "
        f"passed ({summary.get("pass_rate", 0):.1%}), "
        f"{summary.get("critic_loop_exhausted", 0)} exhausted critic loop"
    )

    output_path = Path(args.output)
    output_path.write_text(json.dumps(report, indent=2, default=str))
    logger.info(f"Report written to {output_path}")


if __name__ == "__main__":
    main()
