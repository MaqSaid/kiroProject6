"""Allow running the evaluation harness as a module.

Usage:
    python -m tests.evaluation.cli
"""

from tests.evaluation.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
