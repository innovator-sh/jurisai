#!/usr/bin/env python
"""CLI entrypoint: `python scripts/ingest.py --corpus ipc`.
Thin wrapper — the real logic lives in app.rag.ingest so it's importable
(and testable) without going through argparse."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.rag.ingest import main  # noqa: E402

if __name__ == "__main__":
    main()
