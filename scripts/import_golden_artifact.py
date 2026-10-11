"""One-time, provenance-locked import of the MAF-M1.2 green CI screenshots.

Run only from a deliberately restricted branch bootstrap workflow or
an operator-approved local import. Never refresh goldens on normal tests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True, help="Extracted pinned GitHub Actions artifact folder")
    p.add_argument("--manifest", type=Path, default=Path("e2e/goldens/manifest.json"))
    args = p.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    root = args.manifest.parent
    if manifest.get("schema_version") != "1.0":
        raise ValueError("Invalid golden manifest")
    for name, item in manifest["goldens"].items():
        target = root / f"{name}.png"
        source = args.source / f"{name}.png"
        if source.is_symlink() or not source.is_file():
            raise FileNotFoundError(f"Missing expected CI screenshot: {source}")
        if digest(source) != item["sha256"]:
            raise ValueError(f"CI screenshot does not match pinned SHA-256: {name}")
        with Image.open(source) as image:
            if image.format != "PNG" or list(image.size) != item["size"]:
                raise ValueError(f"Unexpected screenshot encoding or size: {name}")
        if target.exists() or target.is_symlink():
            if target.is_file() and not target.is_symlink() and digest(target) == item["sha256"]:
                print(f"Locked golden already present: {name}")
                continue
            raise FileExistsError(f"Will not overwrite changed golden: {target}")
        root.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            with source.open("rb") as reader:
                shutil.copyfileobj(reader, handle)
        print(f"Imported locked golden: {name}")
    print(f"Verified {len(manifest['goldens'])} screenshots; no existing golden changed.")


if __name__ == "__main__":
    main()
