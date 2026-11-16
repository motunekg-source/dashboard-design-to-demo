#!/usr/bin/env python3
"""Build a clean local iframe host from a ZIP produced by pack_web.py (Python 3.9+)."""
import argparse
import hashlib
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

PAGE = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Demo 导入测试</title>
<style>*{box-sizing:border-box}body{margin:0;background:#12251d;color:#e3ece5;font:14px sans-serif}
header{height:44px;display:flex;align-items:center;padding:0 20px;gap:16px}
iframe{display:block;border:0;width:100%;height:calc(100vh - 44px)}</style>
<header>独立测试宿主<button id="toggle">关闭模块</button></header>
<main></main><script>
const area=document.querySelector('main'),btn=document.querySelector('#toggle');
function openModule(){const frame=document.createElement('iframe');frame.title='导入的 Demo';
frame.src='./modules/visualization/index.html';area.append(frame);btn.textContent='关闭模块';}
btn.onclick=()=>{if(area.firstChild){area.replaceChildren();btn.textContent='打开模块'}else openModule()};
openModule();</script></html>"""

def prepare(bundle, destination):
    if destination.exists():
        raise FileExistsError("请选择尚不存在的测试目录。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as scratch:
        root=Path(scratch)/"host"
        module=root/"modules"/"visualization"
        module.mkdir(parents=True)
        with zipfile.ZipFile(bundle) as archive:
            names=archive.namelist()
            if "index.html" not in names or len(set(names))!=len(names):
                raise ValueError("运行包需要唯一的文件名以及根目录的 index.html。")
            for entry in archive.infolist():
                name=entry.filename
                rel=PurePosixPath(name)
                if rel.is_absolute() or ".." in rel.parts or "\\" in name or stat.S_ISLNK(entry.external_attr >> 16):
                    raise ValueError("不支持的归档路径："+name)
                if entry.is_dir():
                    continue
                target=module/rel
                target.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(entry) as src, target.open("xb") as dest:
                    shutil.copyfileobj(src,dest)
        (root/"index.html").write_text(PAGE,encoding="utf-8")
        root.rename(destination)
    print("SHA-256:",hashlib.sha256(bundle.read_bytes()).hexdigest())
    print("测试目录:",destination)
    print("进入该目录后运行 python3 -m http.server 8090 --bind 127.0.0.1，再打开 http://127.0.0.1:8090/ 。")
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("bundle",type=Path)
    p.add_argument("destination",type=Path)
    a=p.parse_args()
    prepare(a.bundle,a.destination)
