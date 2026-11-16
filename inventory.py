from i18n import tr
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from media import read_audio
from platform_formats import detect_platform,original_stem
from platform_audio import KeyStore,probe_platform
from model import (Cancelled, DISC_FOLDER, EDITION, IMAGE_EXTS, Item, LP, SIDECARS,
                   SUPPORTED, TRACK_PREFIX, Track, clean_text, count_tag, number, reparse)


GENERIC = {"music", "albums", "album", "singles", "single", "flac", "mp3", "aac", "wav", "lossless",
           "recovered audio", "needs review", "audio", "tracks", "songs", "organized", "music organized"}


def scan(root, tools, cancel, workers=4, emit=lambda *a: None,settings=None):
    paths, skipped = [], []
    stack = [root]
    while stack:
        cancel.check()
        folder = stack.pop()
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    if reparse(path):
                        skipped.append((str(path.relative_to(root)), tr('跳过链接或重解析点')))
                    elif entry.is_dir(follow_symlinks=False):
                        stack.append(path)
                    elif entry.is_file(follow_symlinks=False):
                        paths.append(path)
        except OSError as exc:
            skipped.append((str(folder.relative_to(root)), str(exc)))
    paths.sort(key=lambda p: str(p).casefold())
    emit("log", tr('发现 {0} 个文件，正在读取音频信息').format(len(paths)))
    keys=KeyStore(settings.platform_key_file if settings else "")
    for issue in keys.issues:emit("log",tr('密钥文件：')+issue)

    def inspect(path):
        cancel.check()
        ext = path.suffix.casefold()
        st = path.stat()
        family=detect_platform(path)
        kind = ("ncm" if family=="ncm" else "encrypted" if family else ext[1:] if ext in {".iso", ".cue"} else "audio" if ext in SUPPORTED
                else "image" if ext in IMAGE_EXTS else "sidecar" if ext in SIDECARS else "other")
        profile, tags, cover, error = None, {}, False, ""
        crypto=probe_platform(path,family,keys) if family else {}
        if kind == "audio":
            try:
                profile, tags, cover = read_audio(path, tools, cancel)
            except Cancelled:
                raise
            except Exception as exc:
                error = str(exc)
        item = Item(path, path.relative_to(root), st.st_size, st.st_mtime_ns,
                    kind, profile, tags, cover, error,crypto=crypto)
        item.check()
        return item

    items = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scan") as pool:
        futures = {pool.submit(inspect, path): path for path in paths}
        try:
            for future in as_completed(futures):
                cancel.check()
                try:
                    items.append(future.result())
                except Cancelled:
                    raise
                except Exception as exc:
                    skipped.append((str(futures[future].relative_to(root)), str(exc)))
                if len(items) % 50 == 0 or len(items) + len(skipped) >= len(paths):
                    emit("progress", (tr('读取文件'), len(items), len(paths)))
        except BaseException:
            for future in futures:
                future.cancel()
            raise
    items.sort(key=lambda i: str(i.rel).casefold())
    emit("inventory", items)
    return items, skipped


def infer_track(item, path=None, profile=None, tags=None, has_cover=None):
    values = {k: clean_text(v) for k, v in (item.tags if tags is None else tags).items() if clean_text(v)}
    path = path or item.path
    profile = profile or item.profile
    stem = original_stem(path) if item.kind in {"ncm","encrypted"} else path.stem
    prefix = TRACK_PREFIX.match(stem)
    if prefix:
        values.setdefault("tracknumber", count_tag(int(prefix[1])))
        stem = stem[prefix.end():].strip()
    parent = item.rel.parent
    disc = DISC_FOLDER.match(parent.name)
    if disc:
        values.setdefault("discnumber", count_tag(int(disc[1])))
        parent = parent.parent
    if "title" not in values:
        if " - " in stem:
            artist, title = stem.split(" - ", 1)
            if title and artist:
                values.setdefault("artist", clean_text(artist))
                stem = title
        values["title"] = clean_text(stem) or "Unknown Title"
    if not values.get("album"):
        folder = parent.name
        if folder.casefold().replace("_", " ") in GENERIC or not folder:
            folder = values["title"]
        # Remove transfer-site prefixes, while retaining years, catalogue numbers and edition text.
        folder = re.sub(r"^\s*\[(?:www\.|https?://)[^\]]+\]\s*", "", folder, flags=re.I)
        folder = re.sub(r"^\s*\d{5,}[_-]\d{5,}[_-]?\s*", "", folder)
        values["album"] = clean_text(folder) or "Unknown Album"
    values.setdefault("artist", values.get("albumartist", "Unknown Artist"))
    values.setdefault("albumartist", values["artist"])
    variant_source = str(parent) + " " + values["album"]
    variants = []
    if LP.search(variant_source):
        variants.append("Vinyl Rip")
    for match in EDITION.finditer(variant_source):
        edition = match[0].title()
        if edition.casefold() not in {v.casefold() for v in variants}:
            variants.append(edition)
    if profile and profile.channels > 2:
        variants.append(f"{profile.channels}ch")
    track = Track(item, path, profile, values, " - ".join(variants),
                  item.has_cover if has_cover is None else has_cover)
    track.origin_id = str(item.rel)
    if "title" not in item.tags and tags is None:
        track.metadata_source = tr('文件名推断')
    if values["artist"] == "Unknown Artist":
        track.issues.append(tr('缺少可确认的艺术家'))
    return track
