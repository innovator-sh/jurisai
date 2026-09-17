#!/usr/bin/env python
"""CLI: `python scripts/eval.py --corpus ipc`. Non-blocking retrieval-quality
report — see app.rag.eval for the actual logic."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.rag.eval import run_eval  # noqa: E402

QUESTIONS_DIR = Path(__file__).parent.parent / "backend" / "tests" / "eval"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the retrieval-hit-rate eval harness.")
    parser.add_argument("--corpus", required=True)
    args = parser.parse_args()

    questions_path = QUESTIONS_DIR / f"{args.corpus}_questions.yaml"
    result = run_eval(args.corpus, questions_path)

    print(f"Corpus: {result['corpus']} ({result['chunk_count']} chunks indexed)")
    if result["skipped_sections"]:
        print(f"Skipped at ingest (low-confidence parse): {result['skipped_sections']}")
    print(f"Hit rate: {result['hits']}/{result['question_count']} ({result['hit_rate']:.0%})\n")
    for r in result["results"]:
        mark = "PASS" if r["hit"] else "FAIL"
        print(f"  [{mark}] expected {r['expected']:>5} | retrieved {r['retrieved']} | {r['query']}")


if __name__ == "__main__":
    main()
