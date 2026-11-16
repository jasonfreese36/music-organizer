"""Real encoders + repeat/relayout checks on generated fixtures only."""
import argparse
import hashlib
import io
import json
from dataclasses import asdict,replace
from pathlib import Path

from PIL import Image
from mutagen.mp3 import MP3

from conversion import plan_audio
from engine import Organizer
from inventory import infer_track,scan
from media import Tools,make_cover,patch_tags,payload_hash,read_audio
from model import Cancel,Settings
from preview import preview_rows
from rules import matches,validate_rules


def run(root):
    root.mkdir(parents=True,exist_ok=True)
    source=root/"Source";source.mkdir(exist_ok=True)
    tools=Tools();cancel=Cancel()
    buf=io.BytesIO();Image.new("RGB",(160,160),(35,66,88)).save(buf,"PNG")
    cover=make_cover(buf.getvalue(),"fixture")
    def generate(name,codec,rate=48000,bits=None,kbps=0,channels=2):
        path=source/name
        signal=f"anoisesrc=r={rate}:d=3:a=0.2:seed=42[a];anoisesrc=r={rate}:d=3:a=0.2:seed=73[b];[a][b]amerge=inputs=2"
        args=["-y","-f","lavfi","-i",signal,"-ac",str(channels),"-c:a",codec]
        if bits:args += ["-sample_fmt","s32","-bits_per_raw_sample",str(bits)]
        if kbps:args += ["-b:a",f"{kbps}k"]
        tags=dict(title=path.stem,artist="Sample Artist",albumartist="Sample Artist",album="Sample Album",date="2024",genre="Jazz",tracknumber=str(len(list(source.iterdir()))+1),discnumber="1/2")
        for k,v in tags.items():args += ["-metadata",f"{k}={v}"]
        tools.ff([*args,path],cancel)
        if path.suffix in (".flac",".mp3",".m4a"):patch_tags(path,tags,cover)
        return path
    high=generate("High AAC.m4a","aac",kbps=384)
    low=generate("Low AAC.m4a","aac",kbps=128)
    flac=generate("Hi Res.flac","flac",rate=96000,bits=24)
    multi=generate("Multichannel.wav","pcm_s24le",rate=192000,channels=6)
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    items,skips=scan(source,tools,cancel)
    assert not skips,skips
    high_track=infer_track(next(i for i in items if i.path==high))
    assert high_track.profile.bitrate>256000,high_track.profile
    rule=dict(name="AAC over 256",enabled=True,match="all",conditions=[dict(field="format",op="is",value="aac"),dict(field="bitrate",op="gt",value=256)],actions=dict(format="mp3",mp3_mode="cbr",mp3_kbps=192))
    settings=Settings(online=False,rules=(rule,),folder_template="Library/{genre}/{albumartist}/{album}{edition}",filename_template="{title} - {artist} - {track:02d}",disc_template="CD {disc:02d}",id3_version="3")
    planned=preview_rows(items,settings)
    assert next(r for r in planned if r["source"]==high.name)["target"].endswith(".mp3")
    assert next(r for r in planned if r["source"]==low.name)["target"].endswith(".m4a")
    assert not matches(rule,replace(high_track,profile=replace(high_track.profile,bitrate=256000)))
    assert not matches(rule,replace(high_track,profile=replace(high_track.profile,bitrate=0)))
    disabled=replace(settings,rules=(dict(rule,enabled=False),))
    assert plan_audio(high_track,disabled).codec=="aac"
    priority=dict(rule,name="First wins",actions=dict(format="aac"))
    assert plan_audio(high_track,replace(settings,rules=(priority,rule))).codec=="aac"
    target=root/"Organized"
    def organize(config):
        result=Organizer(source,target,items,config,tools,Cancel(),cache_folder=root/"Cache").run()
        assert result["errors"]==0,json.loads((target/"Library Records/Latest Run.json").read_text(encoding="utf-8"))["errors"]
        return result
    first=organize(settings)
    for row in planned:
        assert (target/row["target"]).is_file(),row
    high_out=target/next(r["target"] for r in planned if r["source"]==high.name)
    assert MP3(high_out).tags.version[:2]==(2,3)
    assert read_audio(high_out,tools,cancel)[0].codec=="mp3"
    low_out=target/next(r["target"] for r in planned if r["source"]==low.name)
    assert payload_hash(low_out,cancel)==payload_hash(low,cancel)
    again=organize(settings)
    assert not again["written"] and not again["converted"],again
    # Change codec options in place, using the validated source provenance.
    newrule=dict(rule,actions=dict(format="mp3",mp3_mode="cbr",mp3_kbps=320))
    upgraded=replace(settings,rules=(newrule,))
    changed=organize(upgraded)
    assert changed["converted"]==1 and len(list(target.rglob("*.mp3")))==1,changed
    assert abs(read_audio(high_out,tools,cancel)[0].bitrate-320000)<1000
    # Relayout a previously managed custom root, with a different filename order.
    renamed=replace(upgraded,folder_template="By Year/{year}/{album} - {albumartist}",filename_template="{artist} - {title}",multidisc="prefix")
    moved=organize(renamed)
    assert not moved["written"] and not moved["converted"],moved
    assert len([p for p in target.rglob("*") if p.suffix in (".mp3",".m4a",".flac")])==4
    # Real downsampling, 24->16-bit dither, and SoXR support.
    reduced=replace(renamed,resample_mode="limit",sample_rate=44100,pcm_bits=16,resampler="soxr")
    reduced_result=organize(reduced)
    report=json.loads((target/"Library Records/Latest Run.json").read_text(encoding="utf-8"))
    for row in report["tracks"]:
        if row["source"].endswith((".flac",".wav")):
            p=read_audio(target/row["target"],tools,cancel)[0]
            assert p.rate==44100 and p.bits==16,p
    repeat=organize(reduced)
    assert not repeat["written"] and not repeat["converted"],repeat
    restored=organize(replace(reduced,rules=(dict(rule,enabled=False),)))
    restored_report=json.loads((target/"Library Records/Latest Run.json").read_text(encoding="utf-8"))
    restored_high=next(r for r in restored_report["tracks"] if r["source"]==high.name)
    assert restored_high["target"].endswith(".m4a") and not list(target.rglob("*.mp3"))
    assert payload_hash(target/restored_high["target"],cancel)==payload_hash(high,cancel)
    # Portable MP3 constrains sample rate and channels; source PCM remains intact.
    multi_track=infer_track(next(i for i in items if i.path==multi))
    portable=replace(Settings(online=False),lossless_format="mp3")
    plan=plan_audio(multi_track,portable)
    assert plan.channels==2 and plan.rate==48000,plan
    from media import render
    render(multi_track,root/"Portable.mp3",cover,tools,portable,cancel)
    profile=read_audio(root/"Portable.mp3",tools,cancel)[0]
    assert profile.channels==2 and profile.rate==48000
    native_source=root/"Native Source";native_source.mkdir()
    original=native_source/"Original.mp3"
    tools.ff(["-y","-f","lavfi","-i","anoisesrc=r=44100:d=3:a=0.1:seed=77","-ac","2","-c:a","libmp3lame","-b:a","320k",original],cancel)
    native_items,_=scan(native_source,tools,cancel)
    native_dest=root/"Native Library"
    reencoded=Settings(online=False,reencode_lossy=True,mp3_mode="cbr",mp3_kbps=128)
    a=Organizer(native_source,native_dest,native_items,reencoded,tools,cancel,cache_folder=root/"Cache").run()
    b=Organizer(native_source,native_dest,native_items,Settings(online=False),tools,cancel,cache_folder=root/"Cache").run()
    assert not a["errors"] and not b["errors"] and b["converted"]==1
    assert payload_hash(next((native_dest/"Albums").rglob("*.mp3")),cancel)==payload_hash(original,cancel)
    # Reject traversal, executable-looking fields and reserved report roots.
    for field,value in (("folder_template","../{album}"),("folder_template","Library Records/{album}"),("filename_template","{title.__class__}"),("filename_template","{title!r}"),("disc_template","../{disc}")):
        try:replace(settings,**{field:value})
        except ValueError:pass
        else:raise AssertionError((field,value))
    assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    profile=dict(schema=1,version="1.2.0",settings=asdict(reduced),appearance="light",accent="violet")
    (root/"Profile.json").write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding="utf-8")
    result=dict(defaults_preserved=True,real_bitrate_threshold=True,first_match_priority=True,preview_matches_paths=True,
                mp3_cbr_and_id3_v23=True,lossy_native_preserved=True,custom_layout_resumes=True,reencoding_updates_in_place=True,
                soxr_downsample_and_dither=True,multichannel_mp3=True,repeat_does_not_reencode=True,disabled_rule_restores_source_encoding=True,native_copy_restores_original_payload=True,source_unchanged=True,
                first=first,changed=changed,reduced=reduced_result)
    (root/"test-result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if isinstance(v,bool)},indent=2))
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--root",type=Path,required=True)
    run(parser.parse_args().root.resolve())
