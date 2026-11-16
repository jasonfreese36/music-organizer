"""Generated DSD/CUE and failure archival outside Apple import folders."""
import argparse
import hashlib
import json
import struct
from dataclasses import replace
from pathlib import Path

from apple import compatibility_issue
from engine import Organizer
from inventory import scan
from media import Tools,read_audio
from model import Cancel,Settings


def run(root):
    root.mkdir(parents=True,exist_ok=True);source=root/"Source";source.mkdir(exist_ok=True)
    tools=Tools();cancel=Cancel()
    # 0.1 seconds of synthetic stereo DSD64, packed in channel blocks.
    samples=282240;data=b"\x69"*(9*4096*2)
    fmt=b"fmt "+struct.pack("<QIIIIIIQII",52,1,0,2,2,2822400,1,samples,4096,0)
    body=fmt+b"data"+struct.pack("<Q",12+len(data))+data
    (source/"DSD Sample.dsf").write_bytes(b"DSD "+struct.pack("<QQQ",28,28+len(body),0)+body)
    tools.ff(["-y","-f","lavfi","-i","sine=frequency=440:sample_rate=44100:duration=4","-ac","2","-c:a","pcm_s16le",source/"Disc.wav"],cancel)
    (source/"Disc.cue").write_text('PERFORMER "Test Artist"\nTITLE "CUE Album"\nFILE "Disc.wav" WAVE\n  TRACK 01 AUDIO\n    TITLE "First"\n    INDEX 01 00:00:00\n  TRACK 02 AUDIO\n    TITLE "Second"\n    INDEX 01 00:02:00\n',encoding="utf-8")
    (source/"Not SACD.iso").write_bytes(b"This is deliberately not a SACD image"*1024)
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    items,skips=scan(source,tools,cancel)
    assert not skips
    base=Settings(online=False,output_profile="ios")
    for separate in (False,True):
        settings=replace(base,apple_archive_mode="separate" if separate else "none",apple_archive_folder=str(root/"Originals") if separate else "")
        dest=root/("Archived" if separate else "No Archive")
        result=Organizer(source,dest,items,settings,tools,cancel,cache_folder=root/"Cache").run()
        assert result["written"]==3 and result["errors"]==1,result
        files=[p for p in dest.rglob("*") if p.is_file()]
        assert len(files)==3
        for path in files:assert not compatibility_issue(read_audio(path,tools,cancel)[0],settings,path.suffix)
    files=[p for p in (root/"Originals").rglob("*") if p.is_file()]
    assert {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}==before
    assert {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}==before
    result=dict(passed=True,dsd_converted=True,cue_split=True,invalid_iso_isolated=True,archives_verified=4,source_unchanged=True)
    (root/"Test Result.json").write_text(json.dumps(result,indent=2),encoding="utf-8");print(json.dumps(result,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--root",type=Path,required=True);run(parser.parse_args().root.resolve())
