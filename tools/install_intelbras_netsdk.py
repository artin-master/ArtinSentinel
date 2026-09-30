#!/usr/bin/env python3
from __future__ import annotations

"""Import the official Intelbras Linux x86-64 NetSDK runtime locally.

The Sentinel package does not redistribute the vendor archive. The operator
selects the official ZIP once; libraries and the 05.Talk reference audio are
copied to the persistent per-user vendor directory and reused by future updates.
"""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from artin_sentinel.intelbras_netsdk import install_from_official_archive, vendor_install_directory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path, help="General_NetSDK_3.050_PlaySDK_3.042.zip")
    parser.add_argument("--target", type=Path, default=vendor_install_directory())
    args = parser.parse_args()
    imported = install_from_official_archive(args.archive, args.target)
    print(f"NetSDK Intelbras importado em: {args.target.expanduser()}")
    print("Arquivos: " + ", ".join(imported))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
