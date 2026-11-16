#!/usr/bin/env python3
"""Package an explicit static file list. Paths in the ZIP are relative to index.html."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

def pack(root, file_list, destination):
    root = root.resolve()
    names = json.loads(file_list.read_text(encoding="utf-8"))
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise ValueError("The manifest must contain an array of relative file paths.")
    if "index.html" not in names or len(set(names)) != len(names):
        raise ValueError("Include index.html and list each file once.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as tmp:
        temporary = Path(tmp.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(names):
                rel = PurePosixPath(name)
                if rel.is_absolute() or ".." in rel.parts or rel.as_posix() != name or "\\" in name:
                    raise ValueError(f"Invalid relative file path: {name}")
                path = (root / rel).resolve(strict=True)
                if not path.is_relative_to(root) or not path.is_file() or path in (temporary, destination.resolve()):
                    raise ValueError(f"File is outside the explicit project input: {name}")
                archive.write(path, name)
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip():
                raise ValueError("ZIP integrity check failed")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"{destination.name}  {len(names)} files  sha256={hashlib.sha256(destination.read_bytes()).hexdigest()}")

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("file_list", type=Path)
    parser.add_argument("destination", type=Path)
    args=parser.parse_args()
    pack(args.root,args.file_list,args.destination)
