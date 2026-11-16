import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from inventory import infer_track
from media import read_audio
from model import Cancelled, count_tag, reparse


@dataclass
class CuePart:
    index: int
    file: str
    tags: dict = field(default_factory=dict)
    frame: int | None = None


def cue_text(path):
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8", "gb18030", "cp932", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeError:
            pass
    raise ValueError("CUE 文本编码无法识别")


def parse_cue(path):
    common, parts, filename, part = {}, [], None, None
    for line in cue_text(path).splitlines():
        line = line.strip()
        file_match = re.match(r'^FILE\s+(?:"(.+)"|(.+?))\s+\S+\s*$', line, re.I)
        if file_match:
            filename = file_match[1] or file_match[2]
            part = None
            continue
        track = re.match(r"TRACK\s+(\d+)\s+(\S+)", line, re.I)
        if track:
            if track[2].upper() != "AUDIO" or not filename:
                raise ValueError("CUE 含数据轨或缺少 FILE，保留原盘待核对")
            part = CuePart(int(track[1]), filename)
            parts.append(part)
            continue
        index = re.match(r"INDEX\s+01\s+(\d+):(\d+):(\d+)", line, re.I)
        if index and part:
            m, s, f = map(int, index.groups())
            if s >= 60 or f >= 75:
                raise ValueError("CUE 索引时间无效")
            part.frame = (m * 60 + s) * 75 + f
            continue
        match = re.match(r'(TITLE|PERFORMER|SONGWRITER|ISRC|CATALOG|REM\s+(?:DATE|GENRE|DISCID))\s+(.+)', line, re.I)
        if match:
            key, value = match[1].upper(), match[2].strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1].replace(r'\"', '"')
            mapped = {"TITLE": "title" if part else "album", "PERFORMER": "artist" if part else "albumartist",
                      "SONGWRITER": "composer", "REM DATE": "date", "REM GENRE": "genre",
                      "CATALOG": "barcode" if re.fullmatch(r"\d{12,14}", value) else "catalognumber", "ISRC": "isrc"}.get(key)
            if mapped:
                (part.tags if part else common)[mapped] = value
    if not parts or any(p.frame is None for p in parts):
        raise ValueError("CUE 缺少有效音轨或 INDEX 01")
    return common, parts


def resolve_cue_file(cue, name, source_root):
    relative = Path(name.replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts or relative.drive:
        raise ValueError("CUE 引用目录外的文件")
    exact = cue.parent / relative
    if exact.is_file() and exact.resolve().is_relative_to(source_root) and not reparse(exact):
        return exact
    # Some rips rename .wav to .flac without updating the CUE.
    nearby = [p for p in cue.parent.iterdir() if p.is_file() and not reparse(p)
              and p.stem.casefold() == relative.stem.casefold()
              and p.suffix.casefold() in {".wav", ".wave", ".flac", ".ape", ".wv", ".tta", ".aif", ".aiff"}]
    if len(nearby) == 1:
        return nearby[0]
    raise ValueError(f"CUE 引用的音频不存在或不唯一：{name}")


def split_cue(item, source_root, scratch, item_by_path, tools, cancel, emit):
    item.check()
    common, parts = parse_cue(item.path)
    grouped = {}
    for part in parts:
        path = resolve_cue_file(item.path, part.file, source_root)
        grouped.setdefault(path, []).append(part)
    tracks, references = [], []
    for seq, (path, members) in enumerate(grouped.items()):
        cancel.check()
        source = item_by_path.get(path)
        if not source or not source.profile or source.error:
            raise ValueError("CUE 对应音频未通过扫描")
        if not source.profile.lossless or source.profile.codec.startswith("dsd"):
            raise ValueError("CUE 分轨需要可解码的 PCM 无损原轨，已保留整轨")
        source.check()
        profile = source.profile
        # Decode the image once. Subsequent track encodes seek in the raw PCM file.
        raw = scratch / f"image-{seq}.s32"
        tools.ff(["-y", "-i", path, "-map", "0:a:0", "-c:a", "pcm_s32le", "-f", "s32le", raw], cancel)
        stride = 4 * profile.channels
        samples = raw.stat().st_size // stride
        indexes = [(p.frame * profile.rate) // 75 for p in members]
        if any(b <= a for a, b in zip(indexes, indexes[1:])) or indexes[-1] >= samples:
            raise ValueError("CUE 索引超出整轨或次序异常")
        # Preserve leading audio/pregap in the first track; the whole image remains archived too.
        indexes[0] = 0
        for j, part in enumerate(members):
            cancel.check()
            start, end = indexes[j], indexes[j + 1] if j + 1 < len(members) else samples
            out = scratch / f"track-{seq}-{part.index:03}.flac"
            args = ["-y", "-f", "s32le", "-ar", str(profile.rate), "-ac", str(profile.channels),
                    "-skip_initial_bytes", str(start * stride), "-i", raw,
                    "-af", f"atrim=end_sample={end-start},asetpts=N/SR/TB", "-c:a", "flac",
                    "-compression_level", "5", "-sample_fmt", "s32", "-bits_per_raw_sample",
                    "32" if profile.bits > 24 else "24" if profile.bits > 16 else "16", "-threads", "1"]
            if profile.bits > 24:
                args += ["-strict", "experimental"]
            tools.ff([*args, out], cancel)
            result_profile, _, _ = read_audio(out, tools, cancel)
            if round(result_profile.seconds * profile.rate) != end - start:
                raise ValueError("CUE 分轨采样数校验失败")
            tags = source.tags | common | part.tags
            tags["tracknumber"] = count_tag(part.index, len(parts))
            tags.setdefault("artist", tags.get("albumartist", ""))
            track = infer_track(source, out, result_profile, tags, False)
            track.origin_id += f"#CUE:{part.index}"
            track.metadata_source = "CUE 与原轨标签"
            tracks.append(track)
            emit("log", f"CUE 分轨 {part.index:02} · {tags.get('title', out.name)}")
        source.check()
        references.append(source)
        raw.unlink()
    item.check()
    return tracks, references


def decrypt_ncm(item, scratch, tools, cancel):
    item.check()
    tools.run([tools.ncmdump, "-o", scratch, item.path], cancel, cwd=scratch)
    paths = [p for p in scratch.rglob("*") if p.is_file() and p.suffix.casefold() in {".flac", ".mp3", ".m4a", ".aac"}]
    if len(paths) != 1:
        raise ValueError("ncmdump 未产生唯一的有效音频")
    profile, tags, cover = read_audio(paths[0], tools, cancel)
    if profile.seconds <= 0:
        raise ValueError("NCM 解密结果没有有效时长")
    item.check()
    track = infer_track(item, paths[0], profile, tags, cover)
    track.metadata_source = "NCM 原始元数据"
    return [track]


def extract_sacd(item, scratch, tools, settings, cancel, emit):
    item.check()
    areas = ("stereo", "multi") if settings.sacd_area == "both" else (settings.sacd_area,)
    results = []
    failures = []
    for area in areas:
        cancel.check()
        folder = scratch / area
        folder.mkdir()
        try:
            emit("log", f"读取 SACD {area} · {item.rel.name}")
            tools.run([tools.sacd, "-i", item.path, "-2" if area == "stereo" else "-m",
                       "-f", "-C", "-b", "--flac-rate", str(settings.sacd_rate),
                       "--max-read-errors", "0", "-y", folder], cancel, cwd=folder)
            files = sorted(folder.rglob("*.flac"))
            if not files:
                raise ValueError("此 SACD 区域没有可提取音轨")
            common, parts = {}, []
            cues = list(folder.rglob("*.cue"))
            if cues:
                try:
                    common, parts = parse_cue(cues[0])
                except ValueError:
                    pass
            if parts and len(parts) != len(files):
                raise ValueError("SACD 元数据与提取音轨数量不一致")
            xml_tags = {}
            xmls = list(folder.rglob("*.xml"))
            if xmls:
                doc = ET.parse(xmls[0]).getroot()
                album_node = doc.find("Album")
                disc_node = doc.find(".//Disc")
                for node in doc.findall(".//Area"):
                    stereo = "2 Channel" in node.get("speaker_configuration", "")
                    if stereo != (area == "stereo"):
                        continue
                    expected = int(node.get("totaltracks", "0"))
                    if expected and expected != len(files):
                        raise ValueError("SACD TOC 音轨数与输出数量不同，未导入不完整专辑")
                    for member in node.findall("track"):
                        raw_tags = {m.get("name"): m.get("value", "") for m in member.findall("meta")}
                        aliases = {"TITLE": "title", "PERFORMER": "artist", "ALBUM": "album",
                                   "ALBUM ARTIST": "albumartist", "GENRE": "genre", "ISRC": "isrc"}
                        values = {target: raw_tags[key] for key, target in aliases.items() if raw_tags.get(key) and raw_tags[key] != "Not used"}
                        values["tracknumber"] = count_tag(int(member.get("id")), expected)
                        if disc_node is not None:
                            values["date"] = disc_node.get("creation_date", "")
                            values["catalognumber"] = disc_node.get("catalog_number", "")
                        if album_node is not None:
                            values["discnumber"] = count_tag(int(album_node.get("sequence_number", "1")), int(album_node.get("set_size", "1")))
                            publisher = album_node.findtext("Publisher") or ""
                            values["label"] = re.sub(r"^[©℗\s]*\d{4}\s*", "", publisher)
                        xml_tags[int(member.get("id"))] = {k: v for k, v in values.items() if v}
            for index, path in enumerate(files, 1):
                profile, tags, cover = read_audio(path, tools, cancel)
                if profile.seconds <= 0 or profile.codec != "flac":
                    raise ValueError("SACD 提取产生无效音轨")
                cue_part = next((p for p in parts if Path(p.file).name.casefold() == path.name.casefold()), None)
                if cue_part:
                    tags = common | cue_part.tags | tags
                tags.update(xml_tags.get(index, {}))
                tags.setdefault("tracknumber", count_tag(index, len(files)))
                track = infer_track(item, path, profile, tags, cover)
                track.origin_id += f"#SACD:{area}:{index}"
                track.variant = "SACD" + (f" - {profile.channels}ch" if profile.channels > 2 else "")
                track.metadata_source = "SACD TOC / CD Text"
                results.append(track)
        except Cancelled:
            raise
        except Exception as exc:
            failures.append(f"{area}: {exc}")
    item.check()
    if not results:
        raise ValueError("；".join(failures))
    if failures:
        for track in results:
            track.issues.extend(failures)
    return results
