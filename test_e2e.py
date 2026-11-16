"""Integration checks operate only on generated fixtures, never on the user's library."""
import argparse
import hashlib
import io
import json
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

from PIL import Image
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.id3 import TXXX

from engine import Organizer
from inventory import scan
from media import Tools, images, make_cover, patch_tags, payload_hash, read_audio
from model import Cancel, Settings, bytes_hash


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def integration(root, real_ncm=None):
    root.mkdir(parents=True, exist_ok=True)
    src, dest = root / "Source with 中文", root / "Organized"
    src.mkdir(exist_ok=True)
    tools, cancel = Tools(), Cancel()
    versions = tools.verify(cancel)
    picture = Image.new("RGB", (400, 400), (34, 68, 102))
    data = io.BytesIO()
    picture.save(data, "PNG")
    cover = make_cover(data.getvalue(), "integration fixture")

    def audio(folder, name, codec, title, track, frequency=440, album="Test Album", **options):
        parent = src / folder
        parent.mkdir(parents=True, exist_ok=True)
        path = parent / name
        args = ["-y", "-f", "lavfi", "-i", f"sine=frequency={frequency}:sample_rate=44100:duration=2",
                "-ac", "2", "-c:a", codec, "-threads", "1"]
        if codec == "aac":
            args += ["-b:a", "192k"]
        if options.get("bits"):
            args += ["-sample_fmt", "s32", "-bits_per_raw_sample", str(options["bits"])]
        tags = dict(title=title, artist="Test Artist", albumartist="Test Artist", album=album,
                    tracknumber=str(track), discnumber="1", date="2020", genre="Test")
        for k, v in tags.items():
            args += ["-metadata", k + "=" + v]
        tools.ff([*args, path], cancel)
        if path.suffix in (".mp3", ".flac", ".m4a"):
            patch_tags(path, tags, cover)
        return path

    flac = audio("A album", "01 - 原声.flac", "flac", "原声", 1)
    audio("A album", "02 - MP3.mp3", "libmp3lame", "MP3", 2)
    audio("A album", "03 - AAC.m4a", "aac", "AAC", 3)
    audio("A album", "04 - ALAC.m4a", "alac", "ALAC", 4)
    wave = audio("A album", "05 - WAV.wav", "pcm_s24le", "WAV", 5)
    dup = src / "A album" / "duplicate.flac"
    shutil.copyfile(flac, dup)
    polluted = FLAC(dup)
    polluted["163 key(Don't modify)"] = ["fixture platform identifier"]
    polluted.save()
    audio("B album LP Rip", "01 - 原声.flac", "flac", "原声", 1)
    audio("C alternate", "01 - 原声.flac", "flac", "原声", 1, frequency=550)
    cue_folder = src / "D cue"
    cue_folder.mkdir()
    image = cue_folder / "Full Image.wav"
    tools.ff(["-y", "-f", "lavfi", "-i", "sine=frequency=777:sample_rate=44100:duration=2", "-ac", "2", "-c:a", "pcm_s24le", image], cancel)
    (cue_folder / "Full Image.cue").write_text('PERFORMER "Cue Artist"\nTITLE "Cue Album"\nFILE "Full Image.wav" WAVE\n  TRACK 01 AUDIO\n    TITLE "First"\n    INDEX 01 00:00:00\n  TRACK 02 AUDIO\n    TITLE "Second"\n    INDEX 01 00:01:00\n', encoding="utf-8")
    (cue_folder / "cover.png").write_bytes(cover.data)
    (src / "unhandled.xyz").write_text("preserved at source")
    if real_ncm:
        ncm_folder = src / "NCM"
        ncm_folder.mkdir()
        shutil.copyfile(real_ncm, ncm_folder / real_ncm.name)
    before = snapshot(src)
    items, skipped = scan(src, tools, cancel)
    assert not skipped, skipped
    settings = Settings(online=False, workers=3, verify_pcm=True)
    events = []
    report = Organizer(src, dest, items, settings, tools, cancel, lambda *a: events.append(a), cache_folder=root/"Cache").run()
    (root / "events.json").write_text(json.dumps(events, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    assert report["errors"] == 0, json.loads((dest / "Library Records" / "Latest Run.json").read_text(encoding="utf-8"))["errors"]
    assert before == snapshot(src), "Source files changed"
    assert report["duplicates"] >= 1, report
    files = list((dest / "Albums").rglob("*"))
    audio_files = [p for p in files if p.suffix in (".flac", ".mp3", ".m4a")]
    assert len(audio_files) == 9 + bool(real_ncm), [str(p) for p in audio_files]
    assert any("Vinyl Rip" in str(p) for p in audio_files)
    assert any("Alternate 2" in str(p) for p in audio_files)
    cue_tracks = sorted([p for p in audio_files if "Cue Album" in str(p)])
    assert len(cue_tracks) == 2
    concat = root / "concat.txt"
    concat.write_text("\n".join("file '" + str(p).replace("\\", "/").replace("'", "'\\''") + "'" for p in cue_tracks), encoding="utf-8")
    raw = tools.ff(["-f", "concat", "-safe", "0", "-i", concat, "-map", "0:a:0", "-c:a", "pcm_s32le", "-f", "hash", "-hash", "sha256", "-"], cancel)
    assert tools.decoded_hash(image, cancel) == raw.decode().strip().split("=")[-1], "Cue PCM concatenation differs"
    native = [p for p in audio_files if p.suffix == ".mp3" and p.stem.endswith(" - MP3")][0]
    assert payload_hash(native, cancel) == payload_hash(src/"A album"/"02 - MP3.mp3", cancel)
    for p in audio_files:
        profile, tags, has_cover = read_audio(p, tools, cancel)
        assert has_cover, (p, tags)
        if p.suffix == ".flac":
            assert not any("163 key" in k.casefold() for k in FLAC(p).keys())
    again = Organizer(src, dest, items, settings, tools, Cancel(), cache_folder=root/"Cache").run()
    assert again["written"] == 0 and again["errors"] == 0, again
    assert before == snapshot(src), "Source files changed on repeat"
    from inventory import infer_track
    edited_item = next(i for i in items if i.path == flac)
    overrides = {infer_track(edited_item).edit_key: dict(album="Corrected Album", date="2021")}
    corrected = Organizer(src, dest, items, settings, tools, Cancel(), overrides=overrides, cache_folder=root/"Cache").run()
    assert corrected["written"] == 0 and corrected["errors"] == 0, corrected
    assert len(list((dest/"Albums").rglob("*.mp3"))) == len([p for p in audio_files if p.suffix==".mp3"])
    assert len(list((dest/"Albums"/"Test Artist"/"2021 - Corrected Album").glob("*.*"))) == 6
    assert before == snapshot(src), "Source files changed during metadata correction"
    stopped = Cancel()
    stopped.stop()
    cancelled = Organizer(src, root/"Cancelled", items, settings, tools, stopped, cache_folder=root/"Cache").run()
    assert cancelled["status"] == "cancelled"
    assert not list(dest.rglob(".pending-*")), "Uncommitted output left behind"
    result = dict(versions=versions, first=report, second=again, corrected=corrected, cancellation=cancelled,
                  source_unchanged=True, cue_sample_exact=True, native_payload_unchanged=True,
                  test_root=str(root))
    (root / "test-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--ncm", type=Path)
    args = parser.parse_args()
    print(json.dumps(integration(args.root.resolve(), args.ncm), ensure_ascii=False, indent=2))
