"""Cross-root identity, CUE boundaries, archives, resume and source preservation."""
import argparse
import hashlib
import json
import os
import shutil
from dataclasses import replace
from pathlib import Path

from apple import export_locations
from engine import Organizer
from inventory import infer_track,scan
from media import Tools,patch_tags,read_audio
from model import Cancel,Cancelled,Settings,source_label,validated_sources
from preview import preview_rows


def run(root):
    root.mkdir(parents=True,exist_ok=True)
    a=root/"A"/"Music";b=root/"B"/"Music"
    a.mkdir(parents=True);b.mkdir(parents=True)
    tools=Tools();cancel=Cancel()
    def generate(path,freq,album):
        path.parent.mkdir(parents=True,exist_ok=True)
        tools.ff(["-y","-f","lavfi","-i",f"sine=frequency={freq}:sample_rate=96000:duration=2",
                  "-ac","2","-c:a","flac","-sample_fmt","s32","-bits_per_raw_sample","24",path],cancel)
        patch_tags(path,dict(title="Song",artist="Test Artist",albumartist="Test Artist",album=album,date="2026",tracknumber="1"),None)
    generate(a/"Identical"/"01.flac",440,"Same")
    (b/"Identical").mkdir();shutil.copyfile(a/"Identical/01.flac",b/"Identical/01.flac")
    generate(a/"Different"/"01.flac",660,"Different")
    generate(b/"Different"/"01.flac",880,"Different")
    cue='PERFORMER "Cue Artist"\nTITLE "Cue Album"\nFILE "Image.wav" WAVE\n  TRACK 01 AUDIO\n    TITLE "One"\n    INDEX 01 00:00:00\n  TRACK 02 AUDIO\n    TITLE "Two"\n    INDEX 01 00:01:00\n'
    for base in (a,b):
        folder=base/"Cue";folder.mkdir()
        tools.ff(["-y","-f","lavfi","-i","sine=frequency=500:sample_rate=44100:duration=2","-ac","2","-c:a","pcm_s16le",folder/"Image.wav"],cancel)
        (folder/"Disc.cue").write_text(cue+('REM source B\n' if base==b else ''),encoding="utf-8")
    reference=root/"Platform.mp3"
    tools.ff(["-y","-f","lavfi","-i","sine=frequency=1200:sample_rate=44100:duration=2","-ac","2","-c:a","libmp3lame","-b:a","128k",reference],cancel)
    patch_tags(reference,dict(title="Platform Song",artist="Test Artist",albumartist="Test Artist",album="Platform"),None)
    encrypted=bytes(v^0xa3 for v in reference.read_bytes())
    for base in (a,b):(base/"Same cache.uc").write_bytes(encrypted)
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for base in (a,b) for p in base.rglob("*") if p.is_file()}
    target=root/"Library"
    roots,out=validated_sources([a,b,a],target);assert roots==(a,b) and out==target
    for sources,dest in (([a,a/"Cue"],target),([a,b],b/"Inside"),([a,b],root)):
        try:validated_sources(sources,dest)
        except ValueError:pass
        else:raise AssertionError((sources,dest))
    settings=Settings(online=False)
    single,_=scan(a,tools,cancel)
    first=Organizer(a,target,single,settings,tools,cancel,cache_folder=root/"Cache").run()
    assert not first["errors"],first
    items,skips=scan(roots,tools,cancel);assert not skips
    assert len({str(i.library_rel) for i in items})==len(items)
    ai=next(i for i in items if i.path==a/"Identical/01.flac")
    bi=next(i for i in items if i.path==b/"Identical/01.flac")
    assert infer_track(ai).edit_key!=infer_track(bi).edit_key
    assert infer_track(ai).tags==infer_track(bi).tags
    from source_profiles import load_profiles,save_profiles
    profiles=root/"Profiles";ak=infer_track(ai).edit_key;bk=infer_track(bi).edit_key
    save_profiles(items,profiles,{ak:dict(album="Manual A"),bk:dict(album="Manual B")},
                  {ak:"Cover A.jpg",bk:"Cover B.jpg"},{ak:dict(tag=dict(id="release-A")),bk:dict(tag=dict(id="release-B"))})
    _,edits,covers,picks=load_profiles(single,profiles)
    single_key=infer_track(next(i for i in single if i.path==ai.path)).edit_key
    assert edits[single_key]["album"]=="Manual A" and covers[single_key]=="Cover A.jpg" and picks[single_key]["tag"]["id"]=="release-A"
    _,edits,covers,picks=load_profiles(list(reversed(items)),profiles)
    assert edits[ak]["album"]=="Manual A" and edits[bk]["album"]=="Manual B" and picks[bk]["tag"]["id"]=="release-B"
    rows=preview_rows(items,settings);assert len(rows)==len(items)
    events=[]
    result=Organizer(roots,target,items,settings,tools,cancel,emit=lambda k,v:events.append(v) if k=="platform" else None,cache_folder=root/"Cache").run()
    assert result["errors"]==0 and result["written"]==1,result
    assert len(events)==2 and len({e["source"] for e in events})==2 and all(e["state"]=="decoded" for e in events),events
    assert len(list((target/"Albums").rglob("*.mp3")))==1
    assert len(list((target/"Disc Archives").rglob("*.uc")))==1
    outputs=list((target/"Albums").rglob("*.flac"));assert len(outputs)==5,outputs
    index=json.loads((target/"Library Records/Index.json").read_text(encoding="utf-8"))
    identical=[entry for entry in index.values() if entry["tags"]["album"]=="Same"]
    assert len(identical)==1 and {origin["root"] for origin in identical[0]["origins"]}=={os.path.normcase(str(p)) for p in roots}
    for base in roots:
        for name in ("Disc.cue","Image.wav"):
            assert any(hashlib.sha256(p.read_bytes()).hexdigest()==before[base/"Cue"/name]
                       for p in (target/"Disc Archives/Cue Images").rglob(name))
    assert len(list((target/"Disc Archives/Cue Images").rglob("Disc.cue")))==2
    assert len(list((target/"Disc Archives/Cue Images").rglob("Image.wav")))==1
    # Reordering sources does not change durable provenance or produce another copy.
    reversed_roots=tuple(reversed(roots));reverse_items,_=scan(reversed_roots,tools,cancel)
    repeat=Organizer(reversed_roots,target,reverse_items,settings,tools,cancel,cache_folder=root/"Cache").run()
    assert repeat["errors"]==0 and repeat["written"]==repeat["converted"]==0,repeat
    # Cross-source identical tracks still merge after actual resampling and gain.
    processed=root/"Processed"
    dsp=replace(settings,resample_mode="fixed",sample_rate=48000,gain_db=-3)
    selected=[ai,bi]
    converted=Organizer(roots,processed,selected,dsp,tools,cancel,cache_folder=root/"Cache").run()
    assert not converted["errors"] and len(list((processed/"Albums").rglob("*.flac")))==1,converted
    again=Organizer(roots,processed,selected,dsp,tools,cancel,cache_folder=root/"Cache").run()
    assert not again["errors"] and again["written"]==again["converted"]==0,again
    # Every source is checked against the device report and separate archive folder.
    device=replace(settings,output_profile="ios",apple_archive_mode="separate",apple_archive_folder=str(b/"Bad Archive"))
    try:export_locations(roots,root/"Device",device)
    except ValueError:pass
    else:raise AssertionError("Archive overlaps second source")
    device=replace(device,apple_archive_folder=str(root/"Originals"))
    exported=Organizer(roots,root/"Device",items,device,tools,cancel,cache_folder=root/"Cache").run()
    assert not exported["errors"],exported
    assert all(p.suffix in (".m4a",".mp3") for p in (root/"Device").rglob("*") if p.is_file())
    stop=Cancel();stop.stop()
    try:scan(roots,tools,stop)
    except Cancelled:pass
    else:raise AssertionError("Scan ignored cancellation")
    assert before=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in before}
    result=dict(passed=True,sources=2,same_root_name_safe=True,identical_audio_merged=True,different_versions_retained=True,
                cue_boundaries=True,archive_collisions_avoided=True,single_to_multi_resume=True,reordered_sources_resume=True,
                resampled_duplicates_merged=True,source_specific_edits=True,all_roots_overlap_checked=True,
                platform_event_identity=True,encrypted_audio_merged=True,manual_profiles_survive_source_changes=True,
                apple_export=True,cancellation=True,source_unchanged=True)
    (root/"Test Result.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--root",type=Path,required=True)
    run(parser.parse_args().root.resolve())
