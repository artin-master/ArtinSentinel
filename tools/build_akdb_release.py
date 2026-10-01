#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import base64
import gzip
import json
from pathlib import Path

from artin_akdb import build_bundle, write_bundle
from artin_sentinel.akdb_shared import sentinel_domain_extensions


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an official AKDB bundle + manifest")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--release-revision", type=int, required=True)
    parser.add_argument("--base-url", default="", help="Public base URL containing the generated bundle")
    parser.add_argument("--inline", action="store_true", help="Embed the gzip/base64 bundle directly in stable.json")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle = build_bundle(extensions=sentinel_domain_extensions())
    bundle_name = f"core-r{int(args.release_revision)}.json"
    bundle_path = write_bundle(out_dir / bundle_name, bundle)
    raw = bundle_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    manifest = {
        "schema": "artin-akdb-manifest-v1",
        "channel": "stable",
        "release_revision": int(args.release_revision),
        "core_version": bundle.get("core_version"),
        "core_revision": int(bundle.get("core_revision") or 0),
        "domain_revisions": {"sentinel": max((int(e.get("revision") or 0) for e in bundle.get("extensions") or [] if e.get("domain") == "sentinel"), default=0)},
        "summary": {
            "records": len(bundle.get("records") or []),
            "extensions": len(bundle.get("extensions") or []),
        },
        "bundle": ({
            "data_gzip_base64": base64.b64encode(gzip.compress(raw, 9)).decode("ascii"),
            "sha256": digest,
            "size": len(raw),
            "encoding": "gzip+base64",
        } if args.inline else {
            "url": args.base_url.rstrip("/") + "/" + bundle_name,
            "sha256": digest,
            "size": len(raw),
        }),
    }
    manifest_path = out_dir / "stable.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(manifest_path)
    print(bundle_path)
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
