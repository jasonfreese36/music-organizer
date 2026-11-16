"""Device exports tested with real encoders, generated audio and isolated folders."""
import argparse
import hashlib
import io
import json
from dataclasses import replace
from pathlib import Path

from PIL import Image
from mutagen.mp3 import MP3

from apple import compatibility_issue,export_locations
from conversion import plan_audio
from engine import Organizer
from inventory import infer_track,scan
from media import Tools,embedded_cover,make_cover,patch_tags,payload_hash,read_audio
from model import Cancel,Settings


def run(root):
    root.mkdir(parents=True,exist_ok=True)
    source=root/"Source";source.mkdir(exist_ok=True)
    tools=Tools();cancel=Cancel()
    buf=io.BytesIO();Image.new("RGBA",(1700,1400),(30,90,160,140)).save(buf,"PNG")
    cover=make_cover(buf.getvalue(),"fixture")
    fixtures=[("Hi Res.flac","flac",192000,24,2,0),("Surround.wav","pcm_s24le",96000,24,6,0),
              ("ALAC.m4a","alac",96000,24,2,0),("Low AAC.m4a","aac",44100,0,2,128),
              ("High AAC.m4a","aac",48000,0,2,384),("MP3.mp3","libmp3lame",44100,0,2,320)]
    for n,(name,codec,rate,bits,channels,kbps) in enumerate(fixtures,1):
        path=source/name
        args=["-y","-f","lavfi","-i",f"anoisesrc=r={rate}:d=3:a=0.2:seed={n}","-ac",str(channels),"-c:a",codec]
        if bits:args += ["-sample_fmt","s32p" if codec=="alac" else "s32","-bits_per_raw_sample",str(bits)]
        if kbps:args += ["-b:a",f"{kbps}k"]
        tags=dict(title=path.stem,artist="测试艺术家",albumartist="测试艺术家",album="Device Album",date="2024",tracknumber=str(n),discnumber="1")
        for key,value in tags.items():args += ["-metadata",f"{key}={value}"]
        tools.ff([*args,path],cancel)
        if path.suffix!=".wav":patch_tags(path,tags,cover)
    (source/"cover.png").write_bytes(cover.data)
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    items,skips=scan(source,tools,cancel)
    assert not skips,skips
    def organize(name,settings):
        dest=root/name
        result=Organizer(source,dest,items,settings,tools,Cancel(),cache_folder=root/"Cache").run()
        assert result["errors"]==0,json.loads((Path(result["records_root"])/"Library Records/Latest Run.json").read_text(encoding="utf-8"))["errors"]
        files=[p for p in dest.rglob("*") if p.is_file()]
        assert len(files)==6,(result,files)
        for path in files:
            profile,tags,has=read_audio(path,tools,cancel)
            assert not compatibility_issue(profile,settings,path.suffix),(path,profile)
            assert has,path
            embedded=embedded_cover(path)
            assert embedded.mime=="image/jpeg" and max(embedded.width,embedded.height)<=(1000 if settings.output_profile=="ios" else 600)
            if path.suffix==".mp3" and settings.output_profile=="ipod":assert MP3(path).tags.version[:2]==(2,3)
        return result,files
    standard=Settings(online=False,output_profile="ipod")
    first,files=organize("iPod",standard)
    assert not first["archive_root"] and all(p.suffix==".mp3" for p in files)
    assert not (root/"iPod/Disc Archives").exists()
    again,_=organize("iPod",standard)
    assert again["reused"]==6 and not again["written"] and not again["converted"],again
    archive=root/"Original Discs"
    lossless=replace(standard,output_profile="ios",apple_quality="lossless",apple_archive_mode="separate",apple_archive_folder=str(archive))
    ios,files=organize("iOS",lossless)
    assert len(list(archive.rglob("*.*")))>=7
    archived=[p for p in archive.rglob("*") if p.is_file()]
    assert {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in archived}==before
    for p in files:
        profile=read_audio(p,tools,cancel)[0]
        if p.stem.endswith(("Hi Res","Surround","ALAC")):assert profile.codec=="alac" and profile.bits==24 and profile.rate<=48000
        if p.stem.endswith("Low AAC"):assert payload_hash(p,cancel)==payload_hash(source/"Low AAC.m4a",cancel)
    again,_=organize("iOS",lossless)
    assert again["reused"]==6 and not again["converted"],again
    assert len([p for p in archive.rglob("*") if p.is_file()])==7
    classic=replace(lossless,output_profile="ipod",ipod_model="classic_nano",apple_archive_mode="none",apple_archive_folder="")
    _,files=organize("Classic",classic)
    assert all(p.bits==16 and p.rate==44100 for p in (read_audio(f,tools,cancel)[0] for f in files) if p.codec=="alac")
    # Device constraints override conversion rules and custom high-rate settings.
    rule=dict(name="Unsupported for device",enabled=True,match="all",conditions=[dict(field="format",op="is",value="flac")],actions=dict(format="flac",sample_rate=192000,pcm_bits=32,channels="preserve"))
    strict=replace(standard,rules=(rule,),resample_mode="fixed",sample_rate=192000,pcm_bits=32)
    for item in items:
        if item.profile:
            plan=plan_audio(infer_track(item),strict)
            assert plan.codec=="mp3" and plan.rate<=48000 and plan.channels<=2,plan
    # Unsafe paths and incompatible old output are rejected without modifying it.
    for folder in (root/"iOS",source,root):
        try:export_locations(source,root/"iOS",replace(lossless,apple_archive_folder=str(folder)))
        except ValueError:pass
        else:raise AssertionError(folder)
    dest=root/"Unsafe";dest.mkdir(exist_ok=True);sentinel=dest/"keep.flac";sentinel.write_bytes(b"do not change")
    rejected=Organizer(source,dest,items,standard,tools,Cancel(),cache_folder=root/"Cache").run()
    assert rejected["status"]=="failed" and list(dest.iterdir())==[sentinel] and sentinel.read_bytes()==b"do not change",rejected
    assert {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}==before
    report=dict(passed=True,generated_tracks=6,profiles=["iPod MP3","classic/nano ALAC","iOS ALAC"],source_unchanged=True,separate_archives=7)
    (root/"Test Result.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--root",type=Path,required=True)
    run(parser.parse_args().root.resolve())
