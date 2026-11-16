import argparse
import json
import shutil
from pathlib import Path

from engine import Organizer
from inventory import scan
from media import Tools
from model import Cancel, Settings, validated_roots
from test_e2e import snapshot


def test(root, dsd=None):
    root.mkdir(parents=True, exist_ok=True)
    src, dest = root/"Source", root/"Organized"
    src.mkdir()
    tools, cancel = Tools(), Cancel()
    for disc in (1, 2):
        folder = src / f"Multi Disc Album/CD{disc}"
        folder.mkdir(parents=True)
        tools.ff(["-y", "-f", "lavfi", "-i", f"sine=frequency={400+disc}:sample_rate=48000:duration=2",
                  "-ac", "2", "-c:a", "flac", "-metadata", "album=Multi Disc", "-metadata", "artist=Artist",
                  "-metadata", "albumartist=Artist", "-metadata", f"title=Disc {disc}", "-metadata", "track=1", "-metadata", f"disc={disc}/2",
                  folder/f"01 - Disc {disc}.flac"], cancel)
    for ext, codec in ((".aac", "aac"), (".ogg", "libvorbis"), (".opus", "libopus")):
        tools.ff(["-y", "-f", "lavfi", "-i", "sine=frequency=900:sample_rate=48000:duration=2", "-ac", "2", "-c:a", codec,
                  "-metadata", "title=Other format", "-metadata", f"album=Album {ext[1:]}", "-metadata", "artist=Artist",
                  src/ ("01 - Artist - Other format"+ext)], cancel)
    if dsd:
        shutil.copyfile(dsd, src/dsd.name)
    before=snapshot(src)
    items,_=scan(src,tools,cancel)
    settings=Settings(online=False,workers=3)
    first=Organizer(src,dest,items,settings,tools,cancel,cache_folder=root/"Cache").run()
    assert first["errors"]==0, (dest/"Library Records/Latest Run.json").read_text(encoding="utf-8")
    assert len(list((dest/"Albums").rglob("Disc 01")))==1
    assert len(list((dest/"Albums").rglob("Disc 02")))==1
    second=Organizer(src,dest,items,settings,tools,Cancel(),cache_folder=root/"Cache").run()
    assert second["written"]==0 and second["errors"]==0, second
    def packet_hash(path):
        return tools.encoded_hash(path,Cancel())
    aac_source=next(src.glob("*.aac"))
    candidates=list((dest/"Albums").rglob("*.m4a"))
    assert any(packet_hash(aac_source)==packet_hash(p) for p in candidates), "AAC remux changed encoded packets"
    stop=Cancel()
    def emit(kind,value):
        if kind=="result":stop.stop()
    interrupted=Organizer(src,root/"Interrupted",items,settings,tools,stop,emit,cache_folder=root/"Cache").run()
    assert interrupted["status"]=="cancelled",interrupted
    assert not list((root/"Interrupted").rglob(".pending-*"))
    resumed=Organizer(src,root/"Interrupted",items,settings,tools,Cancel(),cache_folder=root/"Cache").run()
    assert resumed["errors"]==0,resumed
    broken=src/"damaged.mp3";broken.write_bytes(b"not an mp3")
    bad_items,_=scan(src,tools,Cancel())
    failed=Organizer(src,root/"With Error",bad_items,settings,tools,Cancel(),cache_folder=root/"Cache").run()
    assert failed["errors"]==1 and failed["written"]==first["written"],failed
    broken.unlink()
    assert before==snapshot(src),"Sources changed"
    try:validated_roots(src,src/"Nested")
    except ValueError:pass
    else:raise AssertionError("Overlapping roots accepted")
    result=dict(first=first,repeat=second,interrupted=interrupted,resumed=resumed,failure_continued=failed,
                sources_unchanged=True,aac_encoded_packets_unchanged=True,overlapping_roots_rejected=True)
    (root/"test-result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--dsd",type=Path)
    a=p.parse_args();print(json.dumps(test(a.root.resolve(),a.dsd),ensure_ascii=False,indent=2))
