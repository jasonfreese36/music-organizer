"""Download and verify the pinned third-party source materials for a release."""
import argparse
import json
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from prepare import ROOT,digest,fetch


def bundle_sources(output,cache=None):
    manifest=ROOT/"resources/ThirdPartySources.json"
    records=json.loads(manifest.read_text(encoding="utf-8"))["sources"]
    cache=cache or ROOT/"_downloads/corresponding-sources";cache.mkdir(parents=True,exist_ok=True)
    def obtain(record):
        name=record["file"]
        if Path(name).name!=name or "/" in name or "\\" in name:raise ValueError("Invalid source archive filename")
        path=cache/name
        if not path.is_file() or digest(path)!=record["sha256"]:fetch(record["url"],path)
        if digest(path)!=record["sha256"]:raise ValueError("Source checksum mismatch: "+record["name"])
        return path
    with ThreadPoolExecutor(max_workers=6) as pool:files=list(pool.map(obtain,records))
    output.mkdir(parents=True,exist_ok=True)
    target=output/"ThirdPartySources.zip"
    with zipfile.ZipFile(target,"w",zipfile.ZIP_STORED) as package:
        package.write(manifest,"ThirdPartySources/Manifest.json")
        package.write(ROOT/"docs/CORRESPONDING_SOURCES.md","ThirdPartySources/README.md")
        for path in files:package.write(path,"ThirdPartySources/"+path.name)
    return target


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,default=ROOT/"dist");parser.add_argument("--cache",type=Path)
    args=parser.parse_args();target=bundle_sources(args.output.resolve(),args.cache.resolve() if args.cache else None)
    print(json.dumps(dict(file=str(target),size=target.stat().st_size,sha256=digest(target)),indent=2))
