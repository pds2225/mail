#!/usr/bin/env python3
"""Union two PII-free delivery checkpoint files after a GitHub push race."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mail_core.delivery import state as delivery_state  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    parser.add_argument("incoming")
    args = parser.parse_args()
    target = Path(args.target)
    merged = delivery_state.load(target) | delivery_state.load(args.incoming)
    delivery_state.save(target, merged)
    print(f"delivery_state merged: {len(merged)} checkpoint keys")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
