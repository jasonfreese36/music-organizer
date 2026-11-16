from i18n import tr
import contextlib
import json
import os
import shutil
import tempfile
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from catalog import Catalog, HTTP
from formats import decrypt_ncm, extract_sacd, split_cue
from inventory import infer_track
from media import output_ext, payload_hash, read_audio, render
from conversion import needs_render,plan_audio
from apple import device_artwork,device_settings,export_locations,preflight_destination
from naming import album_folder,music_top,track_relative
from platform_audio import KeyStore,decrypt_platform
from platform_formats import ARCHIVE_NAMES
from model import (ALBUMS, ARCHIVES, PLAYLISTS, RECORDS, REVIEW, Cancelled, Journal,
                   at, bytes_hash, component, count_tag, match_name, normalize, number,
                   reparse, short_hash, stage, validated_roots, write_atomic, csv_bytes, year)


@contextlib.contextmanager
def library_lock(root):
    import msvcrt
    root.mkdir(parents=True, exist_ok=True)
    path = at(root, Path(RECORDS, "Library.lock"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, 2)
        if not handle.tell():
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise ValueError(tr('目标音乐库正由另一个整理任务使用')) from exc
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def commit(temp, target):
    """Publish without replacing an existing file, even if another program races us."""
    if os.name == "nt":
        os.rename(temp, target)
    else:
        os.link(temp, target)
        temp.unlink()


def release_key(track):
    return (str(track.source_group), match_name(track.tags.get("albumartist")),
            match_name(track.tags.get("album")), year(track.tags.get("date")), normalize(track.variant))


def track_key(tags):
    n, _ = number(tags.get("tracknumber"))
    d, _ = number(tags.get("discnumber"))
    return (match_name(tags.get("title")), d or 1, n)


class Organizer:
    def __init__(self, source, dest, items, settings, tools, cancel, emit=lambda *a: None,
                 overrides=None, cover_overrides=None, cache_folder=None, selections=None):
        self.source, self.dest = validated_roots(source, dest)
        self.records_root,self.archive_root=export_locations(self.source,self.dest,settings)
        self.items, self.settings, self.tools, self.cancel, self.emit = items, settings, tools, cancel, emit
        self.overrides, self.cover_overrides = overrides or {}, cover_overrides or {}
        self.selections = selections or {}
        self.rows, self.errors, self.index = [], [], {}
        self.lock = threading.Lock()
        self.journal = None
        self.http = HTTP(cache_folder)
        self.catalog = Catalog(self.http, settings, cancel, emit)
        self.existing = defaultdict(list)
        self.origins = defaultdict(list)
        self.by_path = {}
        self.source_hashes = {}
        self.comparisons = {}
        self.started = time.monotonic()
        self.status = "completed"
        self.scratch = None
        self.keys=KeyStore(settings.platform_key_file)
        self.platform_events=[]
        self.archived={}

    def error(self, source, message, phase=tr('整理')):
        row = dict(source=str(source), phase=phase, error=str(message))
        if getattr(message,"code",None):row["code"]=message.code
        self.errors.append(row)
        self.emit("log", tr('{0}失败 · {1} · {2}').format(phase, source, str(message)[:400]))
        if self.journal:
            self.journal.put("error", source, phase=phase, error=str(message))

    def archive(self, item, category):
        if self.archive_root is None:return None
        self.cancel.check()
        item.check()
        key=(item.path,item.size,item.mtime,category)
        if key in self.archived:return self.archived[key]
        prefix=Path() if self.settings.output_profile=="library" else Path(component(self.source.name,65)+" ["+short_hash(str(self.source).casefold())+"]")
        target = at(self.archive_root, prefix / ARCHIVES / category / item.rel)
        original_hash = None
        if target.exists():
            original_hash = bytes_hash(item.path, self.cancel)
            if target.is_file() and target.stat().st_size == item.size and bytes_hash(target, self.cancel) == original_hash:
                self.archived[key]=target
                return target
            target = target.with_name(f"{component(target.stem, 65)} [{original_hash[:8]}]{target.suffix}")
            if target.exists():
                if target.is_file() and bytes_hash(target, self.cancel) == original_hash:
                    self.archived[key]=target
                    return target
                raise ValueError(tr('备份名称冲突，未覆盖已有内容'))
        with stage(target) as temp:
            with item.path.open("rb") as src, temp.open("wb") as out:
                while block := src.read(4*1024**2):
                    self.cancel.check()
                    out.write(block)
            original_hash = original_hash or bytes_hash(item.path, self.cancel)
            if bytes_hash(temp, self.cancel) != original_hash:
                raise ValueError(tr('备份副本校验失败'))
            item.check()
            commit(temp, target)
        self.journal.put("archive", item.rel, target=str(target), sha256=original_hash)
        self.archived[key]=target
        self.emit("log", tr('保留原盘 · {0}').format(item.rel))
        return target

    def load_index(self):
        cached = {}
        path = at(self.records_root, Path(RECORDS, "Index.json"))
        if path.is_file():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                self.emit("log", tr('旧索引无法读取，将重新读取目标库'))
        top=music_top(self.settings)
        roots=[at(self.dest,top)] if top else [self.dest]
        roots.append(at(self.dest,ALBUMS))
        for rel in cached:
            try:
                candidate=at(self.dest,rel)
                if candidate.relative_to(self.dest).parts[0].casefold() not in {n.casefold() for n in (ARCHIVES,RECORDS,REVIEW,PLAYLISTS)}:roots.append(candidate.parent)
            except (ValueError,TypeError):continue
        stack=[p for p in dict.fromkeys(roots) if p.is_dir()]
        seen=set()
        while stack:
            self.cancel.check()
            folder = stack.pop()
            if folder in seen:continue
            seen.add(folder)
            for path in folder.iterdir():
                if folder==self.dest and path.name.casefold() in {n.casefold() for n in (ARCHIVES,RECORDS,REVIEW,PLAYLISTS)}:continue
                if reparse(path):
                    raise ValueError(tr('目标库含链接或重解析点，请先移走该链接：{0}').format(path))
                if path.is_dir():
                    stack.append(path)
                elif path.suffix.casefold() in {".flac", ".mp3", ".m4a"}:
                    try:
                        profile, tags, cover = read_audio(path, self.tools, self.cancel)
                        rel = str(path.relative_to(self.dest))
                        old = cached.get(rel, {})
                        release = at(self.dest,old["folder"]) if old.get("folder") else path.parent.parent if path.parent.name.startswith("Disc ") else path.parent
                        entry = dict(path=path, profile=profile, tags=tags, cover=cover,
                                     folder=release, variant=old.get("variant", ""), record=old)
                        self.existing[release].append(entry)
                        self.by_path[path] = entry
                        self.index[rel] = old | dict(tags=tags, variant=entry["variant"], audio_sha256=old.get("audio_sha256", ""))
                        for origin in old.get("origins", []):
                            self.origins[(origin.get("root"), origin.get("id"))].append(entry)
                    except Cancelled:
                        raise
                    except Exception as exc:
                        self.error(str(path.relative_to(self.dest)), exc, tr('读取目标库'))

    def expand(self):
        tracks, covered = [], set()
        mapping = {i.path: i for i in self.items}
        for item in self.items:
            if item.kind != "cue":
                continue
            self.cancel.check()
            folder = self.scratch / ("cue-" + short_hash(item.rel))
            folder.mkdir()
            try:
                members, images = split_cue(item, self.source, folder, mapping, self.tools, self.cancel, self.emit)
                if any(image.path in covered for image in images):
                    # Multiple text encodings of the same CUE should not duplicate an album.
                    self.archive(item, "Cue Images")
                    self.emit("log", tr('相同整轨的附加 CUE 已保留 · {0}').format(item.rel))
                    continue
                for image in [item, *images]:
                    self.archive(image, "Cue Images")
                tracks.extend(members)
                covered.update(image.path for image in images)
            except Cancelled:
                raise
            except Exception as exc:
                self.error(item.rel, exc, tr('CUE 分轨'))
                try:
                    self.archive(item, "Cue Images")
                except Cancelled:
                    raise
                except Exception as archive_exc:
                    self.error(item.rel, archive_exc, tr('CUE 备份'))
        encrypted=[i for i in self.items if i.kind in {"ncm","encrypted"}]
        for issue in self.keys.issues:self.emit("log",tr('密钥文件：')+issue)
        def unwrap(index,item):
            self.cancel.check()
            folder=self.scratch/f"platform-{index:06}-{short_hash(item.rel)}";folder.mkdir()
            info=item.crypto
            category="NCM Originals" if item.kind=="ncm" else "Platform Originals/"+ARCHIVE_NAMES.get(info.get("platform"),"Other")
            self.archive(item,category)
            if not self.settings.decrypt_enabled:return [],dict(source=str(item.rel),platform=info.get("platform",""),name=info.get("name",tr('平台音频')),version=info.get("version",""),state="disabled",detail=tr('平台解密未启用；源文件保留'))
            self.emit("log",tr('平台音频 · {0} · {1}').format(info.get('name', ''), item.rel))
            members,result=decrypt_platform(item,folder,self.tools,self.settings,self.cancel,self.keys)
            return members,dict(source=str(item.rel),**result)
        with ThreadPoolExecutor(max_workers=min(self.settings.workers,self.settings.decrypt_workers),thread_name_prefix="platform") as pool:
            pending=[pool.submit(unwrap,index,item) for index,item in enumerate(encrypted)]
            for index,(item,future) in enumerate(zip(encrypted,pending),1):
                try:
                    members,result=future.result();tracks.extend(members)
                except Cancelled:
                    for job in pending:job.cancel()
                    raise
                except Exception as exc:
                    self.error(item.rel,exc,tr('平台音频'))
                    result=dict(source=str(item.rel),platform=item.crypto.get("platform",""),name=item.crypto.get("name",tr('平台音频')),version=item.crypto.get("version",""),state=getattr(exc,"code","invalid_data"),detail=str(exc)[:300])
                self.platform_events.append(result);self.emit("platform",result)
                self.emit("progress",(tr('平台音频还原'),index,len(encrypted)))
                covered.add(item.path)
        special = [i for i in self.items if i.kind=="iso" or i.path.suffix.casefold() in {".dsf", ".dff"}]
        for index, item in enumerate(special, 1):
            self.cancel.check()
            self.emit("progress", (tr('解密 / 原盘处理'), index-1, len(special)))
            folder = self.scratch / (item.kind + "-" + short_hash(item.rel))
            folder.mkdir()
            category = "DSD Originals"
            try:
                self.archive(item, category)
                if item.kind == "iso":
                    tracks.extend(extract_sacd(item, folder, self.tools, self.settings, self.cancel, self.emit))
                elif item.profile:
                    tracks.append(infer_track(item))
                else:
                    raise ValueError(item.error or tr('DSD 音轨无法读取'))
            except Cancelled:
                raise
            except Exception as exc:
                self.error(item.rel, exc, tr('解密 / 原盘处理'))
            covered.add(item.path)
        for item in self.items:
            self.cancel.check()
            if item.kind == "audio" and item.path not in covered:
                if item.profile and not item.error:
                    if self.settings.output_profile!="library":self.archive(item,"Audio Originals")
                    elif item.profile.codec.startswith("pcm_f") or item.profile.bits > 32:self.archive(item, "PCM Originals")
                    tracks.append(infer_track(item))
                else:
                    self.error(item.rel, item.error or tr('无有效音频'), tr('音频读取'))
        for track in tracks:
            edits = self.overrides.get(track.edit_key, {})
            track.tags.update({k: v for k, v in edits.items() if v})
            plan=plan_audio(track,self.settings)
            if not track.profile.lossless and plan.mode=="encode":
                track.issues.append(tr('{0} 有损重新编码为 {1}；原文件仍在源目录').format(track.profile.codec, plan.codec.upper()))
            if track.profile.codec.startswith("pcm_f") or track.profile.bits > 32:
                track.issues.append(tr('浮点或超高位深转整数 PCM 可能量化；源文件保留，原盘按归档设置处理'))
        compilation_groups = defaultdict(list)
        for track in tracks:
            compilation_groups[(str(track.source_group), match_name(track.tags.get("album")))].append(track)
        for members in compilation_groups.values():
            if (len({match_name(t.tags.get("artist")) for t in members}) > 1
                    and not any(t.source.tags.get("albumartist") for t in members)
                    and not self.overrides.get(members[0].edit_key, {}).get("albumartist")):
                for track in members:
                    track.tags["albumartist"] = "Various Artists"
        return tracks

    def same(self, track, entry):
        record = entry.get("record", {})
        transformed = track.profile.codec.startswith("dsd") or not track.profile.lossless and track.profile.codec not in {"mp3", "aac"}
        for origin in record.get("origins", []):
            if (origin.get("root") == os.path.normcase(str(self.source)) and origin.get("id") == track.origin_id and origin.get("source_sha256")):
                if self.source_hash(track)==origin["source_sha256"] and payload_hash(entry["path"],self.cancel)==record.get("audio_sha256"):
                    return True
        profile = entry["profile"]
        if transformed:
            plan=plan_audio(track,self.settings)
            if profile.channels != plan.channels or profile.rate != plan.rate or profile.codec!=plan.codec or abs(profile.seconds-track.profile.seconds) > .18:
                return False
            key = track.origin_id
            if key not in self.comparisons:
                comparison = self.scratch / ("compare-"+short_hash(key)+plan.ext)
                render(track, comparison, None, self.tools, self.settings, self.cancel)
                self.comparisons[key] = comparison
            comparison = self.comparisons[key]
            if comparison.suffix != entry["path"].suffix:
                return False
            return payload_hash(comparison, self.cancel) == payload_hash(entry["path"], self.cancel)
        if (track.profile.codec == profile.codec == "aac" and track.path.suffix.casefold() != entry["path"].suffix.casefold()
                and track.profile.channels == profile.channels and track.profile.rate == profile.rate):
            return self.tools.encoded_hash(track.path, self.cancel) == self.tools.encoded_hash(entry["path"], self.cancel)
        if profile.channels != track.profile.channels or profile.rate != track.profile.rate or abs(profile.seconds-track.profile.seconds) > .06:
            return False
        ext = track.path.suffix.casefold()
        if ext == entry["path"].suffix.casefold() and ext in {".mp3", ".m4a", ".flac"}:
            if payload_hash(track.path, self.cancel) == payload_hash(entry["path"], self.cancel):
                return True
        if track.profile.lossless and profile.lossless:
            return self.tools.decoded_hash(track.path, self.cancel) == self.tools.decoded_hash(entry["path"], self.cancel)
        return False

    def transform(self,track):
        return plan_audio(track,self.settings).signature

    def source_hash(self, track):
        key = (str(track.source.path), track.source.size, track.source.mtime)
        if key not in self.source_hashes:
            self.source_hashes[key] = bytes_hash(track.source.path, self.cancel)
        return self.source_hashes[key]

    def equivalent_entries(self, track, entries):
        key = track_key(track.tags)
        result = []
        for entry in entries:
            other = track_key(entry["tags"])
            if key[0] == other[0] and key[1] == other[1] and (not key[2] or not other[2] or key[2] == other[2]):
                result.append(entry)
        return result

    def choose_folder(self, tracks):
        lead = tracks[0]
        base=at(self.dest,album_folder(lead,self.settings))
        name=base.name
        candidates = [base]
        # Reuse previously assigned alternate versions even after a restart.
        for folder, entries in self.existing.items():
            if folder == base or not entries:
                continue
            sample = entries[0]
            if (match_name(sample["tags"].get("albumartist")) == match_name(lead.tags["albumartist"])
                    and match_name(sample["tags"].get("album")) == match_name(lead.tags["album"])
                    and normalize(sample["variant"]) == normalize(lead.variant)
                    and year(sample["tags"].get("date")) == year(lead.tags.get("date"))):
                candidates.append(folder)
        viable = []
        for folder in candidates:
            entries, matches, conflict = self.existing.get(folder, []), {}, False
            for index, track in enumerate(tracks):
                overlaps = self.equivalent_entries(track, entries)
                if not overlaps:
                    origins = self.origins.get((os.path.normcase(str(self.source)), track.origin_id), [])
                    equal_origin = next((entry for entry in origins if normalize(entry["variant"]) == normalize(track.variant) and self.same(track, entry)), None)
                    if equal_origin:
                        matches[index] = equal_origin
                    continue
                equal = next((entry for entry in overlaps if self.same(track, entry)), None)
                if equal:
                    matches[index] = equal
                else:
                    conflict = True
                    break
            if not conflict:
                viable.append((len(matches), folder == base, folder, matches))
        if viable:
            _, _, folder, matches = max(viable, key=lambda row: row[:2])
            return folder, matches
        for seq in range(2, 10000):
            alternate = base.with_name(component(name, 62) + f" [Alternate {seq}]")
            if not alternate.exists():
                self.emit("log", tr('发现不同音频版本，单独保留 · {0}').format(alternate.name))
                return alternate, {}
        raise ValueError(tr('同名版本过多，无法分配目录'))

    def row(self, track, target, status, sha="", cover=None,folder=None):
        plan=plan_audio(track,self.settings)
        result = dict(source=str(track.source.rel), target=str(target.relative_to(self.dest)), status=status,
                      title=track.tags.get("title", ""), artist=track.tags.get("artist", ""),
                      album=track.tags.get("album", ""), variant=track.variant,
                      metadata_source=track.metadata_source, cover_source=cover.source if cover else "",
                      issues="；".join(dict.fromkeys(track.issues)), audio_sha256=sha,rule=plan.rule,conversion=plan.description)
        self.rows.append(result)
        self.journal.put(status, track.source.rel, **{k: v for k, v in result.items() if k != "source"})
        prior = self.index.get(result["target"], {})
        origins = list(prior.get("origins", []))
        origin = dict(root=os.path.normcase(str(self.source)), id=track.origin_id, source_sha256=self.source_hash(track))
        origins = [o for o in origins if (o.get("root"), o.get("id")) != (origin["root"], origin["id"])] + [origin]
        record = dict(tags=track.tags, variant=track.variant, audio_sha256=sha or prior.get("audio_sha256", ""),
                      origins=origins, transform=self.transform(track),folder=str((folder or target.parent).relative_to(self.dest)))
        self.index[result["target"]] = record
        if entry := self.by_path.get(target):
            entry["record"] = record
            origin_entries = self.origins[(origin["root"], origin["id"])]
            if not any(e is entry for e in origin_entries):
                origin_entries.append(entry)
        self.emit("result", result)

    def write_one(self, track, target, cover):
        self.cancel.check()
        with stage(target) as temp:
            sha = render(track, temp, cover, self.tools, self.settings, self.cancel)
            self.source_hash(track)
            self.cancel.check()
            commit(temp, target)
        return sha

    def refresh_existing(self, track, entry, cover, desired):
        track.source.check()
        target = entry["path"]
        # Existing files are replaced only after a same-directory staged copy passes audio verification.
        st = target.stat()
        rerender=needs_render(track,entry,self.settings)
        with stage(desired) as temp:
            from media import patch_tags
            before = payload_hash(target, self.cancel)
            if rerender:
                result=render(track,temp,cover,self.tools,self.settings,self.cancel)
            else:
                shutil.copyfile(target,temp)
                patch_tags(temp,track.tags,cover,device_settings(self.settings).id3_version)
                result=payload_hash(temp,self.cancel)
                if result!=before:raise ValueError(tr('已有文件的标签更新未通过音频校验'))
            self.cancel.check()
            after = target.stat()
            if (st.st_size, st.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError(tr('已有文件被其他程序修改，未覆盖'))
            if desired != target:
                desired.parent.mkdir(parents=True, exist_ok=True)
                if desired.exists():
                    if payload_hash(desired, self.cancel) != result:
                        raise ValueError(tr('更正名称的目标已有不同音频，未覆盖'))
                    os.replace(temp, desired)
                else:
                    commit(temp, desired)
                # The source and destination were already confined to Albums by at().
                target.unlink()
                old_rel = str(target.relative_to(self.dest))
                new_rel = str(desired.relative_to(self.dest))
                self.index[new_rel] = self.index.pop(old_rel, {})
                entry["path"] = desired
                self.by_path.pop(target, None)
                self.by_path[desired] = entry
                new_folder=at(self.dest,album_folder(track,self.settings))
                old_folder = entry["folder"]
                if new_folder != old_folder:
                    self.existing[old_folder] = [e for e in self.existing[old_folder] if e is not entry]
                    self.existing[new_folder].append(entry)
                    entry["folder"] = new_folder
                self.journal.put("relocated", old_rel, target=new_rel)
            else:
                os.replace(temp, target)
        entry["tags"] = dict(track.tags)
        if rerender:entry["profile"]=read_audio(desired,self.tools,self.cancel)[0]
        track.source.check()
        return result

    def group(self, tracks, pool, cover):
        cover=device_artwork(cover,self.settings)
        tracks.sort(key=lambda t: (number(t.tags.get("discnumber"))[0], number(t.tags.get("tracknumber"))[0], str(t.path)))
        for track in tracks:
            track.tags.update({k: v for k, v in self.overrides.get(track.edit_key, {}).items() if v})
            track.tags.update(track.source.edits)
            if track.source.edits or self.overrides.get(track.edit_key):
                track.metadata_source = tr('用户更正；') + track.metadata_source
        folder, matches = self.choose_folder(tracks)
        folder.mkdir(parents=True, exist_ok=True)
        if cover and self.settings.write_cover_file and self.settings.output_profile=="library":
            cover_name = "cover.jpg" if cover.mime == "image/jpeg" else "cover.png"
            write_atomic(at(self.dest, folder.relative_to(self.dest) / cover_name), cover.data)
        discs = {number(t.tags.get("discnumber"))[0] or 1 for t in tracks}
        multidisc = len(discs) > 1 or any(number(t.tags.get("discnumber"))[1] > 1 for t in tracks)
        scheduled, duplicates, used = {}, [], {}
        for index, track in enumerate(tracks):
            self.cancel.check()
            disc = number(track.tags.get("discnumber"))[0] or 1
            n = number(track.tags.get("tracknumber"))[0]
            if not n:
                track.issues.append(tr('缺少可确认的轨序，文件名前缀采用目录排序'))
                n = index + 1
            target=at(self.dest,folder.relative_to(self.dest)/track_relative(track,self.settings,plan_audio(track,self.settings),n,multidisc))
            if index in matches:
                entry = matches[index]
                try:
                    converted=needs_render(track,entry,self.settings)
                    sha = self.refresh_existing(track, entry, cover, target)
                    self.row(track,entry["path"],"converted" if converted else "reused",sha,cover,folder)
                except Cancelled:
                    raise
                except Exception as exc:
                    self.error(track.source.rel, exc, tr('更新已有音轨'))
                continue
            key = track_key(track.tags)
            prior = used.get(key)
            if prior and self.same(track, dict(path=prior[0].path, profile=prior[0].profile)):
                duplicates.append((track, prior[1]))
                continue
            if target.exists() or any(target == t[1] for t in used.values()):
                target = target.with_name(component(target.stem, 70) + f" [{short_hash(str(track.source.rel)+str(track.path))}]" + target.suffix)
                if target.exists():
                    raise ValueError(tr('无法安全分配音轨文件名 {0}').format(target.name))
            used[key] = track, target
            future = pool.submit(self.write_one, track, target, cover)
            scheduled[future] = track, target
        successful = set()
        for future in as_completed(scheduled):
            track, target = scheduled[future]
            try:
                sha = future.result()
                successful.add(target)
                profile, tags, has_cover = read_audio(target, self.tools, self.cancel)
                entry = dict(path=target, profile=profile, tags=tags, cover=has_cover, folder=folder, variant=track.variant)
                self.existing[folder].append(entry)
                self.by_path[target] = entry
                self.row(track, target, "written", sha, cover,folder)
            except Cancelled:
                for pending in scheduled:
                    pending.cancel()
                raise
            except Exception as exc:
                self.error(track.source.rel, exc, tr('写入音轨'))
        for track, target in duplicates:
            if target in successful:
                self.row(track, target, "duplicate", cover=cover,folder=folder)
            else:
                self.error(track.source.rel, tr('重复源对应的输出未成功，重跑后可恢复'), tr('重复音轨'))

    def reports(self):
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        summary = dict(status=self.status, source=str(self.source), target=str(self.dest),
                       records_root=str(self.records_root),archive_root=str(self.archive_root) if self.archive_root else "",output_profile=self.settings.output_profile,
                       elapsed_seconds=round(time.monotonic()-self.started, 2),
                       written=sum(r["status"] == "written" for r in self.rows),
                       reused=sum(r["status"] == "reused" for r in self.rows),
                       converted=sum(r["status"] == "converted" for r in self.rows),
                       duplicates=sum(r["status"] == "duplicate" for r in self.rows),
                       tracks_with_issues=sum(bool(r["issues"]) for r in self.rows), errors=len(self.errors),
                       ignored_other_files=sum(i.kind == "other" for i in self.items), settings=asdict(self.settings))
        summary.update(encrypted_decoded=sum(r["state"]=="decoded" for r in self.platform_events),encrypted_pending=sum(r["state"] not in ("decoded","disabled") for r in self.platform_events))
        header = ["source", "target", "status", "title", "artist", "album", "variant", "metadata_source", "cover_source", "rule", "conversion", "issues", "audio_sha256"]
        for name, data in (("Index.json", json.dumps(self.index, ensure_ascii=False, indent=2).encode("utf-8")),
                           ("Latest Run.json", json.dumps(dict(summary=summary,tracks=self.rows,errors=self.errors,encrypted_files=self.platform_events),ensure_ascii=False,indent=2).encode("utf-8")),
                           ("Platform Audio.csv",csv_bytes(["source","platform","state","version","scheme","detail"],([r.get(k,"") for k in ("source","platform","state","version","scheme","detail")] for r in self.platform_events))),
                           (f"Run {timestamp}.csv", csv_bytes(header, ([r.get(k, "") for k in header] for r in self.rows)))):
            write_atomic(at(self.records_root, Path(RECORDS, name)), data)
        issues = [[r["source"], r["target"], r["issues"]] for r in self.rows if r["issues"]]
        issues += [[r["source"], "", r["phase"]+"："+r["error"]] for r in self.errors]
        write_atomic(at(self.records_root, Path(REVIEW, "Review.csv")), csv_bytes(["source", "target", "issue"], issues))
        write_atomic(at(self.records_root, Path(REVIEW, "README.txt")),
                     tr('音轨仍在 Albums 中正常归档；这里列出缺封面、匹配不确定或处理失败的条目。\n在程序扫描预览中修改专辑信息或指定本地封面，重新整理到同一目标库即可补全。\n平台加密音频、ISO 与 CUE 原件保存在 Disc Archives（成功备份的项目）。平台缺密钥项可在高级设置中添加密钥后重跑。源目录始终保留。\n').encode("utf-8"))
        playlist = ["#EXTM3U"]
        for rel in sorted(self.index, key=str.casefold):
            target = at(self.dest, rel)
            if target.is_file():
                playlist.append(Path(os.path.relpath(target,self.records_root/PLAYLISTS)).as_posix())
        if self.settings.write_playlists:write_atomic(at(self.records_root, Path(PLAYLISTS, "All Tracks.m3u8")), ("\n".join(playlist)+"\n").encode("utf-8"))
        self.emit("summary", summary)
        return summary

    def run(self):
        result = None
        try:
            with library_lock(self.records_root):
                self.journal = Journal(self.records_root)
                self.journal.put("run_started", self.source, settings=asdict(self.settings))
                try:
                    self.tools.verify(self.cancel)
                    preflight_destination(self.dest,self.settings,self.tools,self.cancel)
                    self.load_index()
                    workroot = at(self.records_root, Path(RECORDS, "Temporary"))
                    workroot.mkdir(parents=True, exist_ok=True)
                    with tempfile.TemporaryDirectory(prefix="run-", dir=workroot) as folder:
                        self.scratch = Path(folder)
                        tracks = self.expand()
                        groups = defaultdict(list)
                        for track in tracks:
                            groups[release_key(track)].append(track)
                        self.emit("log", tr('整理 {0} 条音轨 / {1} 个专辑分组').format(len(tracks), len(groups)))
                        ordered = list(groups.values())
                        with ThreadPoolExecutor(max_workers=self.settings.workers, thread_name_prefix="audio") as pool, ThreadPoolExecutor(max_workers=2, thread_name_prefix="catalog") as lookups:
                            pending = {}
                            for position in range(min(2, len(ordered))):
                                pending[position] = lookups.submit(self.catalog.enrich, ordered[position], self.cover_overrides, self.selections)
                            for position, members in enumerate(ordered):
                                index = position + 1
                                self.cancel.check()
                                self.emit("progress", (tr('整理专辑'), index-1, len(groups)))
                                self.emit("log", tr('专辑 {0}/{1} · {2}').format(index, len(groups), members[0].tags['album']))
                                try:
                                    cover = pending.pop(position).result()
                                    if position+2 < len(ordered):
                                        pending[position+2] = lookups.submit(self.catalog.enrich, ordered[position+2], self.cover_overrides, self.selections)
                                    self.group(members, pool, cover)
                                except Cancelled:
                                    raise
                                except Exception as exc:
                                    for track in members:
                                        self.error(track.source.rel, exc, tr('专辑整理'))
                                    if position+2 < len(ordered) and position+2 not in pending:
                                        pending[position+2] = lookups.submit(self.catalog.enrich, ordered[position+2], self.cover_overrides, self.selections)
                        if self.settings.keep_sidecars:
                            sidecars = [i for i in self.items if i.kind in {"image", "sidecar"}]
                            for index, item in enumerate(sidecars, 1):
                                self.cancel.check()
                                self.emit("progress", (tr('保留封面与附页'), index, len(sidecars)))
                                try:
                                    self.archive(item, "Artwork and Notes")
                                except Cancelled:
                                    raise
                                except Exception as exc:
                                    self.error(item.rel, exc, tr('附页备份'))
                except Cancelled:
                    self.status = "cancelled"
                    self.emit("log", tr('任务已停止，已完成的音轨保留，重新运行可接着整理'))
                except Exception as exc:
                    self.status = "failed"
                    self.error("", exc, tr('任务'))
                if self.errors and self.status == "completed":
                    self.status = "completed_with_errors"
                result = self.reports()
                self.journal.put("run_finished", self.source, **{k: v for k, v in result.items() if k != "source"})
        finally:
            self.http.close()
        return result
