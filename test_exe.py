"""Smoke-test a packaged EXE using generated source fixtures from test_apple.py."""
import argparse
import json
import os
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

from apple import compatibility_issue
from media import Tools,read_audio
from model import Cancel,Settings


def run(exe,root,source):
    root.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,LOCALAPPDATA=str(root/"State"))
    durations=[]
    def command(name,arguments,expected=0):
        report=root/(name+".json");start=time.monotonic()
        result=subprocess.run([str(exe),"--language","en",*arguments,"--report",str(report)],env=env,timeout=180,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        assert result.returncode==expected,(name,result.returncode)
        doc=json.loads(report.read_text(encoding="utf-8"));durations.append(round(time.monotonic()-start,2));return doc
    checked=command("Tools",["--check-tools"])
    assert len(checked["tools"])==5
    for profile in ("ipod","ios"):
        settings=Settings(online=False,output_profile=profile,apple_quality="lossless" if profile=="ios" else "standard",apple_archive_mode="separate" if profile=="ios" else "none",apple_archive_folder=str(root/"Originals") if profile=="ios" else "")
        config=root/(profile+"-settings.json");config.write_text(json.dumps(asdict(settings)),encoding="utf-8")
        dest=root/profile
        arguments=["--organize","--settings",str(config),"--source",str(source),"--dest",str(dest)]
        first=command(profile,arguments)["organize"]
        assert first["written"]==6 and first["errors"]==0,first
        again=command(profile+"-repeat",arguments)["organize"]
        assert again["reused"]==6 and not again["written"] and not again["converted"],again
        files=[p for p in dest.rglob("*") if p.is_file()]
        assert len(files)==6
        for path in files:
            data,tags,cover=read_audio(path,Tools(),Cancel())
            assert cover and not compatibility_issue(data,settings,path.suffix)
    result=dict(exe=str(exe),passed=True,bundled_tools=5,profiles=2,repeat=True,source_path_independent=True,elapsed_seconds=durations)
    (root/"Test Result.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--exe",type=Path,required=True);parser.add_argument("--root",type=Path,required=True);parser.add_argument("--source",type=Path,required=True)
    args=parser.parse_args();run(args.exe.resolve(),args.root.resolve(),args.source.resolve())
