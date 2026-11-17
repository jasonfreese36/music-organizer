"""Smoke-test a packaged EXE using generated source fixtures from test_apple.py."""
import argparse
import json
import os
import shutil
import subprocess
import time
from dataclasses import asdict,replace
from pathlib import Path

from apple import compatibility_issue
from media import Tools,payload_hash,read_audio,render
from inventory import infer_track,scan
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
    # Real compiled multi-root + DSP pipeline, compared against the source build.
    a=root/"Source A";b=root/"Source B";a.mkdir();b.mkdir()
    fixture=next(p for p in source.glob("*.flac") if read_audio(p,Tools(),Cancel())[0].channels==2)
    shutil.copyfile(fixture,a/"01.flac");shutil.copyfile(fixture,b/"01.flac")
    settings=Settings(online=False,resample_mode="fixed",sample_rate=48000,pcm_bits=16,resampler="soxr",
                      soxr_precision=33,resample_cutoff_enabled=True,gain_db=-3)
    config=root/"DSP.json";config.write_text(json.dumps(asdict(settings)),encoding="utf-8")
    dest=root/"Multi"
    arguments=["--organize","--settings",str(config),"--source",str(a),"--source",str(b),"--dest",str(dest)]
    first=command("Multi-DSP",arguments)["organize"]
    assert first["written"]==1 and first["errors"]==0 and len(first["sources"])==2,first
    outputs=list((dest/"Albums").rglob("*.flac"));assert len(outputs)==1
    tools=Tools();cancel=Cancel();items,_=scan(a,tools,cancel)
    expected=root/"Expected.flac";render(infer_track(items[0]),expected,None,tools,settings,cancel)
    assert payload_hash(outputs[0],cancel)==payload_hash(expected,cancel)
    again=command("Multi-DSP-repeat",arguments)["organize"]
    assert again["written"]==again["converted"]==again["errors"]==0,again
    settings=replace(settings,resample_cutoff=90)
    config.write_text(json.dumps(asdict(settings)),encoding="utf-8")
    changed=command("Multi-DSP-changed",arguments)["organize"]
    assert changed["converted"]==1 and changed["errors"]==0,changed
    from test_audio_dsp import make_dsf
    ds=root/"DSD Source";ds.mkdir();make_dsf(ds/"Tone.dsf")
    dsd_settings=Settings(online=False,sacd_rate=176400,dsd_advanced=True,dsd_lowpass_order=8,
                          dsd_remove_dc=True,dsd_gain_db=-3,resampler="soxr")
    dc=root/"DSD.json";dc.write_text(json.dumps(asdict(dsd_settings)),encoding="utf-8")
    dd=root/"DSD"
    converted=command("DSD-Advanced",["--organize","--settings",str(dc),"--source",str(ds),"--dest",str(dd)])["organize"]
    assert converted["written"]==1 and not converted["errors"],converted
    dsd_items,_=scan(ds,tools,cancel);expected=root/"DSD Expected.flac"
    render(infer_track(dsd_items[0]),expected,None,tools,dsd_settings,cancel)
    assert payload_hash(next((dd/"Albums").rglob("*.flac")),cancel)==payload_hash(expected,cancel)
    for language in ("en","zh_CN"):
        checked=command("GUI-"+language,["--check-gui","--language",language])
        assert checked["gui"]["dsp_controls"] and checked["gui"]["multiple_source_controls"],checked
    result=dict(exe=str(exe),passed=True,bundled_tools=5,profiles=2,repeat=True,source_path_independent=True,
                multiple_sources=True,compiled_dsp_matches_source=True,cutoff_change_updates=True,
                compiled_dsd_matches_source=True,bilingual_gui=True,elapsed_seconds=durations)
    (root/"Test Result.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--exe",type=Path,required=True);parser.add_argument("--root",type=Path,required=True);parser.add_argument("--source",type=Path,required=True)
    args=parser.parse_args();run(args.exe.resolve(),args.root.resolve(),args.source.resolve())
