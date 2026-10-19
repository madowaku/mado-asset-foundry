"""Offline, fail-closed MOSS layout and paired image benchmark evidence.

No model execution, downloads, LoRA loading, or upstream code execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image

MODELS = ("moss-base", "moss-sft", "moss-sft-lora", "anima")
SCHEMA = "maf.moss-bakeoff.v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compile_layout(spec: dict[str, Any]) -> dict[str, Any]:
    """Compile top-left pixel xyxy boxes to official centered yxyx boxes."""
    width, height = spec["width"], spec["height"]
    if type(width) is not int or type(height) is not int or not (64 <= width <= 8192 and 64 <= height <= 8192):
        raise ValueError("canvas width/height must be integers from 64 to 8192")
    caption = spec["caption"]
    if not isinstance(caption, str) or not caption.strip():
        raise ValueError("nonempty caption required")
    items = spec["items"]
    if not isinstance(items, list) or not items or len(items) > 64:
        raise ValueError("1 to 64 layout items required")
    compiled = []
    for item in items:
        if not isinstance(item, dict) or item.get("label") not in ("text", "object"):
            raise ValueError("item label must be text or object")
        box = item.get("bbox_xyxy")
        if not isinstance(box, list) or len(box) != 4 or any(type(v) is not int for v in box):
            raise ValueError("bbox_xyxy must contain four integer pixels")
        x1, y1, x2, y2 = box
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            raise ValueError("bbox outside canvas or not ordered")
        detail = item.get("caption")
        if not isinstance(detail, str) or not detail.strip():
            raise ValueError("item caption required")
        result = {"label": item["label"], "caption": detail,
                  "bbox": [y1 - height // 2, x1 - width // 2, y2 - height // 2, x2 - width // 2]}
        if item["label"] == "text":
            word = item.get("text")
            if not isinstance(word, str) or not word.strip():
                raise ValueError("text item requires text")
            result["text"] = word
        elif "text" in item:
            raise ValueError("object item must not have text")
        compiled.append(result)
    return {"summary": {"meta": ["poster"], "canvas": "single", "caption": caption},
            "items": compiled, "bbox_coord_space": "abs_centralized", "bbox_format": "yxyx"}


def inspect_images(manifest: dict[str, Any], root: Path) -> dict[str, Any]:
    """Collect image hashes and declared subjective scores, without claiming model quality."""
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a nonempty list")
    seen = set()
    output = []
    for case in cases:
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise ValueError("duplicate/invalid case id")
        seen.add(case_id)
        width, height = case.get("width"), case.get("height")
        if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
            raise ValueError("invalid target dimensions")
        seed = case.get("seed")
        if type(seed) is not int or seed < 0:
            raise ValueError("each case needs nonnegative integer seed")
        samples = case.get("samples")
        if not isinstance(samples, list):
            raise ValueError("samples must be list")
        sample_models = set()
        found = []
        for sample in samples:
            model = sample.get("model")
            if model not in MODELS or model in sample_models:
                raise ValueError("unknown/duplicate model in case")
            sample_models.add(model)
            value = sample.get("path")
            if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts:
                raise ValueError("sample path must be relative and contained")
            path = root / value
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
                raise ValueError("missing/unsafe sample path")
            with Image.open(path) as img:
                img.verify()
            with Image.open(path) as img:
                if img.format != "PNG" or img.size != (width, height):
                    raise ValueError("expected PNG with target dimensions")
            found.append({"model": model, "path": value, "sha256": sha256(path)})
        output.append({"id": case_id, "seed": seed, "width": width, "height": height,
                       "samples": found, "paired_complete": len(found) == len(MODELS)})
    return {"schema": SCHEMA, "status": "awaiting_human_review",
            "models": list(MODELS), "cases": output, "generation_executed": False,
            "quality_approved": False, "rights_approved": False}


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline MOSS layout compiler and evidence inspector")
    sub = parser.add_subparsers(dest="command", required=True)
    layout = sub.add_parser("layout")
    layout.add_argument("input", type=Path)
    evidence = sub.add_parser("evidence")
    evidence.add_argument("manifest", type=Path)
    evidence.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "layout":
        result = compile_layout(json.loads(args.input.read_text(encoding="utf-8")))
    else:
        result = inspect_images(json.loads(args.manifest.read_text(encoding="utf-8")), args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
