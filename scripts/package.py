#!/usr/bin/env python3
"""Build the release zip HACS installs: the integration folder's contents, with
manifest.json carrying the release version.

    python3 scripts/package.py --version 1.2.0 --out dist
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "custom_components" / "feedrion"
ZIP_DATE = (2024, 1, 1, 0, 0, 0)  # reproducible archives
SKIP = {"__pycache__"}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--version", required=True)
    p.add_argument("--out", required=True, type=pathlib.Path)
    a = p.parse_args()
    if not re.fullmatch(r"\d+\.\d+\.\d+", a.version):
        raise SystemExit("version must be X.Y.Z")
    a.out.mkdir(parents=True, exist_ok=True)
    target = a.out / "feedrion.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(SRC.rglob("*")):
            rel = path.relative_to(SRC)
            if path.is_dir() or SKIP & set(rel.parts) or path.suffix == ".pyc":
                continue
            data = path.read_bytes()
            if rel.as_posix() == "manifest.json":
                manifest = json.loads(data)
                manifest["version"] = a.version
                data = (json.dumps(manifest, indent=2) + "\n").encode()
            info = zipfile.ZipInfo(rel.as_posix(), ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (a.out / "SHA256SUMS").write_text(f"{digest}  {target.name}\n")
    print(f"{digest}  {target.name}")


if __name__ == "__main__":
    main()
