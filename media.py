from i18n import tr
import hashlib
import base64
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import threading
import tempfile
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen import id3
from mutagen.flac import FLAC, Picture
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm
from PIL import Image, ImageOps

from model import Cancelled, Cover, FIELDS, Item, NATIVE, PLATFORM, Profile, clean_text, first, number


ID3_FIELDS = dict(title="TIT2", artist="TPE1", album="TALB", albumartist="TPE2",
                  tracknumber="TRCK", discnumber="TPOS", date="TDRC", genre="TCON",
                  composer="TCOM", label="TPUB", isrc="TSRC")
MP4_FIELDS = dict(title="\xa9nam", artist="\xa9ART", album="\xa9alb", albumartist="aART",
                  date="\xa9day", genre="\xa9gen", composer="\xa9wrt")
STORE_ATOMS = {"cnID", "plID", "atID", "geID", "cmID", "akID", "sfID", "apID",
               "ownr", "purd", "xid ", "----:com.apple.iTunes:iTunMOVI",
               "----:com.apple.iTunes:iTunes_CDDB_1", "----:com.apple.iTunes:iTunes_CDDB_TrackNumber"}
KEY_ALIASES = {"album_artist": "albumartist", "album artist": "albumartist",
               "track": "tracknumber", "disc": "discnumber", "year": "date",
               "organization": "label", "catalog": "catalognumber", "catalog_number": "catalognumber"}


def resource(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    relative=Path(name)
    if relative.parts and relative.parts[0]=="tools" and os.environ.get("MUSIC_ORGANIZER_TOOLS"):
        return Path(os.environ["MUSIC_ORGANIZER_TOOLS"]).expanduser().resolve().joinpath(*relative.parts[1:])
    if relative.parts and relative.parts[0]=="tools" and not (base/"resources/tools").is_dir():
        from runtime_tools import unpack_tools
        return unpack_tools(base/"resources/NativeTools.zip").joinpath(*relative.parts[1:])
    return base / "resources" / name


class Tools:
    def __init__(self):
        self.folder = resource("tools")
        self.ffmpeg = self.folder / "ffmpeg.exe"
        self.ffprobe = self.folder / "ffprobe.exe"
        self.ncmdump = self.folder / "ncmdump.exe"
        self.sacd = self.folder / "sacd_extract.exe"
        self.platformaudio=self.folder/"platformaudio.exe"
        self.hash_cache = {}
        self.hash_lock = threading.Lock()

    def verify(self, cancel):
        versions = {}
        with tempfile.TemporaryDirectory(prefix="MusicOrganizer-check-") as folder:
            for name, path, option in (("FFmpeg", self.ffmpeg, "-version"),
                                       ("FFprobe", self.ffprobe, "-version"),
                                       ("ncmdump", self.ncmdump, "--version"),
                                       ("SACD Extract", self.sacd, "--version"),("PlatformAudio",self.platformaudio,"--self-test")):
                if not path.is_file():
                    raise FileNotFoundError(tr('缺少已打包的工具 {0}').format(name))
                output = self.run([path, option], cancel, cwd=folder)
                versions[name] = output.decode("utf-8", "replace").strip()[:260]
        return versions

    def run(self, args, cancel, cwd=None, timeout=None,input_data=None):
        cancel.check()
        args = list(map(str, args))
        with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
                              cwd=cwd, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) as process:
            import time
            started = time.monotonic()
            try:
                while True:
                    cancel.check()
                    if timeout and time.monotonic() - started > timeout:
                        raise TimeoutError(tr('工具运行超时 {0}').format(Path(args[0]).name))
                    try:
                        stdout, stderr = process.communicate(input=input_data,timeout=0.2)
                        break
                    except subprocess.TimeoutExpired:
                        input_data=None
            except BaseException:
                process.kill()
                process.communicate()
                raise
        if process.returncode:
            message = (stderr + b"\n" + stdout).decode("utf-8", "replace").strip()
            raise ValueError(tr('{0} 退出码 {1}\n{2}').format(Path(args[0]).name, process.returncode, message[-3500:]))
        cancel.check()
        return stdout

    def ff(self, args, cancel, cwd=None):
        prefix = [self.ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror", "-threads", "1"]
        return self.run([*prefix, *args], cancel, cwd=cwd)

    def probe(self, path, cancel):
        raw = self.run([self.ffprobe, "-v", "error", "-select_streams", "a:0",
                        "-show_streams", "-show_format", "-of", "json", path], cancel)
        doc = json.loads(raw)
        if not doc.get("streams"):
            raise ValueError(tr('文件中没有可读取的音频流'))
        stream = doc["streams"][0]
        duration = float(stream.get("duration") or doc.get("format", {}).get("duration") or 0)
        profile = Profile(stream["codec_name"], int(stream.get("sample_rate") or 0),
                          int(stream.get("channels") or 0),
                          int(stream.get("bits_per_raw_sample") or stream.get("bits_per_sample") or 0),
                          duration, stream.get("channel_layout", ""),int(stream.get("bit_rate") or 0),str(stream.get("profile") or ""))
        tags = dict(doc.get("format", {}).get("tags") or {})
        tags.update(stream.get("tags") or {})
        return profile, canonical(tags)

    def decoded_hash(self, path, cancel):
        st = path.stat()
        key = (str(path), st.st_size, st.st_mtime_ns)
        with self.hash_lock:
            if key in self.hash_cache:
                return self.hash_cache[key]
        raw = self.ff(["-i", path, "-map", "0:a:0", "-c:a", "pcm_s32le",
                       "-f", "hash", "-hash", "sha256", "-"], cancel)
        result = raw.decode("ascii").strip().split("=")[-1]
        if not re.fullmatch(r"[0-9a-fA-F]{64}", result):
            raise ValueError(tr('音频解码校验未返回有效结果'))
        with self.hash_lock:
            self.hash_cache[key] = result
        return result

    def verify_audio(self,path,profile,cancel):
        raw=self.ff(["-i",path,"-map","0:a:0","-c:a","pcm_s32le","-progress","pipe:1","-nostats",
                     "-f","hash","-hash","sha256","-"],cancel).decode("ascii","replace")
        fields={k.strip():v.strip() for line in raw.splitlines() if "=" in line for k,v in [line.split("=",1)]}
        digest=fields.get("SHA256","")
        if not re.fullmatch(r"[0-9a-fA-F]{64}",digest):raise ValueError(tr('完整解码校验未返回音频摘要'))
        micros=fields.get("out_time_us","")
        if micros.isdigit() and (profile.lossless or path.suffix.casefold() in (".mp3",".m4a")):
            decoded=float(micros)/1e6
            if decoded<=0 or abs(decoded-profile.seconds)>max(.3,profile.seconds*.005):raise ValueError(tr('解密音频的实际解码时长与文件信息不一致'))
        st=path.stat()
        with self.hash_lock:self.hash_cache[(str(path),st.st_size,st.st_mtime_ns)]=digest
        return digest

    def encoded_hash(self, path, cancel):
        st = path.stat()
        key = ("packets", str(path), st.st_size, st.st_mtime_ns)
        with self.hash_lock:
            if key in self.hash_cache:
                return self.hash_cache[key]
        raw = self.ff(["-i", path, "-map", "0:a:0", "-c:a", "copy", "-bsf:a", "aac_adtstoasc", "-f", "hash", "-hash", "sha256", "-"], cancel)
        result = raw.decode("ascii").strip().split("=")[-1]
        if not re.fullmatch(r"[0-9a-fA-F]{64}", result):
            raise ValueError(tr('编码音频校验未返回有效结果'))
        with self.hash_lock:
            self.hash_cache[key] = result
        return result


def canonical(tags):
    result = {}
    for key, values in tags.items():
        key = KEY_ALIASES.get(key.casefold(), key.casefold())
        if key in FIELDS and (value := first(values)):
            result[key] = value
    return result


def tag_view(audio, ext):
    tags = audio.tags or {}
    if ext == ".flac":
        return canonical(tags)
    if ext in (".m4a", ".m4b", ".alac"):
        result = {field: first(tags.get(atom, [])) for field, atom in MP4_FIELDS.items()}
        for field, atom in (("tracknumber", "trkn"), ("discnumber", "disk")):
            if value := tags.get(atom):
                result[field] = "/".join(str(n) for n in value[0] if n)
        for field in ("label", "catalognumber", "barcode", "isrc"):
            values = tags.get("----:com.apple.iTunes:" + field.upper(), [])
            if values:
                result[field] = clean_text(bytes(values[0]).decode("utf-8", "replace"))
        return {k: v for k, v in result.items() if v}
    if ext == ".mp3":
        result = {field: first(getattr(tags.get(frame), "text", [])) for field, frame in ID3_FIELDS.items()}
        for field in ("catalognumber", "barcode"):
            result[field] = first(getattr(tags.get("TXXX:" + field.upper()), "text", []))
        return {k: v for k, v in result.items() if v}
    return canonical(tags)


def images(audio, ext):
    if ext == ".flac":
        return [(int(pic.type), pic.data) for pic in audio.pictures]
    if ext in (".m4a", ".m4b", ".alac"):
        return [(3, bytes(data)) for data in audio.get("covr", [])]
    if ext == ".mp3" and audio.tags:
        return [(int(pic.type), pic.data) for pic in audio.tags.getall("APIC")]
    if getattr(audio, "pictures", None):
        return [(int(pic.type), pic.data) for pic in audio.pictures]
    if audio.tags and hasattr(audio.tags, "getall"):
        return [(int(pic.type), pic.data) for pic in audio.tags.getall("APIC")]
    if audio.tags:
        result = []
        for key in ("Cover Art (Front)", "cover art (front)"):
            value = audio.tags.get(key)
            if value is not None:
                try:
                    data = bytes(value.value)
                    result.append((3, data.split(b"\0", 1)[1]))
                except (TypeError, ValueError, IndexError, AttributeError):
                    pass
        for value in audio.tags.get("metadata_block_picture", []):
            try:
                pic = Picture(base64.b64decode(value))
                result.append((int(pic.type), pic.data))
            except (ValueError, TypeError):
                pass
        return result
    return []


def read_audio(path, tools, cancel):
    cancel.check()
    ext = path.suffix.casefold()
    readers = {".flac": FLAC, ".mp3": MP3, ".m4a": MP4}
    try:
        audio = readers[ext](path) if ext in readers else MutagenFile(path)
        if audio is None or not hasattr(audio, "info"):
            raise ValueError(tr('需要探测格式'))
        info = audio.info
        codec = {".flac": "flac", ".mp3": "mp3"}.get(ext, str(getattr(info, "codec", "")))
        codec_profile=""
        if codec.startswith("mp4a"):
            codec_profile="LC" if codec=="mp4a.40.2" else str(getattr(info,"codec_description",""))
            codec = "aac"
        if not codec or ext not in NATIVE:
            profile, probed = tools.probe(path, cancel)
        else:
            profile = Profile(codec, int(getattr(info, "sample_rate", 0)),
                              int(getattr(info, "channels", 0)), int(getattr(info, "bits_per_sample", 0)),
                              float(info.length),bitrate=int(getattr(info,"bitrate",0) or 0),codec_profile=codec_profile)
            probed = {}
        tags = probed | tag_view(audio, ext)
        has_cover = any(data and kind in (0, 3, 6) for kind, data in images(audio, ext))
        return profile, tags, has_cover
    except Cancelled:
        raise
    except Exception:
        profile, tags = tools.probe(path, cancel)
        return profile, tags, False


def make_cover(data, source):
    if len(data) > 25 * 1024**2:
        raise ValueError(tr('封面文件超过 25 MB'))
    with Image.open(io.BytesIO(data)) as picture:
        if min(picture.size) < 48 or max(picture.size) > 20000:
            raise ValueError(tr('图片尺寸不适合作为封面'))
        picture.load()
        transformed = ImageOps.exif_transpose(picture)
        if picture.format in ("JPEG", "PNG") and max(picture.size) <= 1600 and transformed.size == picture.size:
            mime = "image/jpeg" if picture.format == "JPEG" else "image/png"
            return Cover(data, mime, picture.width, picture.height, source)
        rgb = transformed.convert("RGB")
        rgb.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        rgb.save(output, "JPEG", quality=93)
        return Cover(output.getvalue(), "image/jpeg", rgb.width, rgb.height, source)


def embedded_cover(path):
    try:
        audio = MutagenFile(path)
        candidates = images(audio, path.suffix.casefold()) if audio else []
        for desired in (3, 0, 6):
            for kind, data in candidates:
                if kind == desired:
                    try:
                        return make_cover(data, tr('原文件内嵌图片'))
                    except (ValueError, OSError):
                        continue
    except (ValueError, OSError):
        pass
    return None


def platform_cleanup(audio, ext):
    tags = audio.tags or {}
    if ext == ".mp3":
        for key, frame in list(tags.items()):
            if frame.FrameID in ("COMM", "TXXX", "TENC", "WXXX", "WOAR"):
                vals = getattr(frame, "text", [])
                desc = getattr(frame, "desc", "")
                if PLATFORM.match(desc) or any(PLATFORM.match(str(v).strip()) for v in vals):
                    del tags[key]
        return
    for key in list(tags.keys()):
        if key in STORE_ATOMS or PLATFORM.match(key):
            del tags[key]
            continue
        if key.casefold() in ("comment", "description", "encodedby", "encoded_by", "source", "\xa9cmt", "\xa9too"):
            if any(PLATFORM.match(str(v).strip()) for v in tags[key]):
                del tags[key]


def picture_frame(cover):
    pic = Picture()
    pic.type = 3
    pic.mime = cover.mime
    pic.width, pic.height, pic.depth = cover.width, cover.height, 24
    pic.data = cover.data
    return pic


def patch_tags(path, values, cover, id3_version="preserve"):
    ext = path.suffix.casefold()
    audio = {".flac": FLAC, ".mp3": MP3, ".m4a": MP4}[ext](path)
    if audio.tags is None:
        audio.add_tags()
    platform_cleanup(audio, ext)
    values = {key: value for key, v in values.items() if key in FIELDS and (value := clean_text(v))}
    if ext == ".flac":
        for key, value in values.items():
            audio[key] = [value]
        if cover:
            previous = [p for p in audio.pictures if p.data != cover.data and p.type not in (0, 3, 6)]
            audio.clear_pictures()
            audio.add_picture(picture_frame(cover))
            for pic in previous:
                audio.add_picture(pic)
        audio.save(deleteid3=True)
    elif ext == ".mp3":
        for key, value in values.items():
            frame = ID3_FIELDS.get(key)
            if frame:
                audio.tags.delall(frame)
                audio.tags.add(id3.Frames[frame](encoding=3, text=[value]))
            else:
                audio.tags["TXXX:" + key.upper()] = id3.TXXX(encoding=3, desc=key.upper(), text=[value])
        if cover:
            for frame in audio.tags.getall("APIC"):
                if frame.type in (0, 3, 6):
                    audio.tags.pop(frame.HashKey, None)
            audio.tags.add(id3.APIC(encoding=3, type=3, desc="Front cover", mime=cover.mime, data=cover.data))
        version = int(id3_version) if id3_version in ("3","4") else 3 if audio.tags.version[:2] == (2, 3) else 4
        audio.save(v1=0, v2_version=version)
    else:
        for key, value in values.items():
            if key in ("tracknumber", "discnumber"):
                audio["trkn" if key == "tracknumber" else "disk"] = [number(value)]
            elif key in MP4_FIELDS:
                audio[MP4_FIELDS[key]] = [value]
            else:
                audio["----:com.apple.iTunes:" + key.upper()] = [MP4FreeForm(value.encode("utf-8"))]
        if cover:
            fmt = MP4Cover.FORMAT_JPEG if cover.mime == "image/jpeg" else MP4Cover.FORMAT_PNG
            audio["covr"] = [MP4Cover(cover.data, fmt)]
        audio.save()
    verified = {".flac": FLAC, ".mp3": MP3, ".m4a": MP4}[ext](path)
    roundtrip = tag_view(verified, ext)
    for key, value in values.items():
        if roundtrip.get(key) != value:
            raise ValueError(tr('标签写入校验失败 {0}').format(key))
    if cover and not any(data == cover.data and kind == 3 for kind, data in images(verified, ext)):
        raise ValueError(tr('封面写入校验失败'))


def payload_hash(path, cancel):
    digest = hashlib.sha256()
    ext = path.suffix.casefold()
    with path.open("rb") as handle:
        length = path.stat().st_size

        def block(size):
            while size > 0:
                cancel.check()
                data = handle.read(min(size, 4 * 1024**2))
                if not data:
                    raise ValueError(tr('音频数据提前结束'))
                digest.update(data)
                size -= len(data)

        first_header = handle.read(10)
        start = 0
        if first_header[:3] == b"ID3" and len(first_header) == 10:
            start = 10 + sum(value << (7 * i) for i, value in enumerate(reversed(first_header[6:10])))
            if first_header[3] == 4 and first_header[5] & 0x10:
                start += 10
        if ext in (".mp3", ".flac"):
            if length >= 128:
                handle.seek(length - 128)
                if handle.read(3) == b"TAG":
                    length -= 128
            handle.seek(start)
            if ext == ".flac":
                if handle.read(4) != b"fLaC":
                    raise ValueError(tr('无法定位 FLAC 音频块'))
                while True:
                    tag = handle.read(4)
                    if len(tag) != 4:
                        raise ValueError(tr('FLAC 元数据不完整'))
                    handle.seek(int.from_bytes(tag[1:], "big"), 1)
                    if tag[0] & 128:
                        break
            if not 0 <= handle.tell() < length:
                raise ValueError(tr('音频块范围无效'))
            block(length - handle.tell())
        elif ext == ".m4a":
            handle.seek(0)
            media = 0
            while handle.tell() < length:
                pos = handle.tell()
                header = handle.read(8)
                if len(header) != 8:
                    raise ValueError(tr('MP4 数据块不完整'))
                size, atom = struct.unpack(">I4s", header)
                if size == 1:
                    size = int.from_bytes(handle.read(8), "big")
                if size == 0:
                    size = length - pos
                end = pos + size
                if not handle.tell() <= end <= length:
                    raise ValueError(tr('MP4 数据块长度无效'))
                if atom == b"mdat":
                    block(end - handle.tell())
                    media += 1
                handle.seek(end)
            if not media:
                raise ValueError(tr('MP4 音频块缺失'))
        else:
            raise ValueError(tr('不支持直接校验的容器 {0}').format(ext))
    return digest.hexdigest()


def output_ext(track,settings=None):
    if settings is not None:
        from conversion import plan_audio
        return plan_audio(track,settings).ext
    if track.profile.codec == "mp3" and track.path.suffix.casefold() == ".mp3":
        return ".mp3"
    if track.profile.codec == "aac":
        return ".m4a"
    return ".flac" if track.profile.lossless else ".m4a"


def render(track, dest, cover, tools, settings, cancel):
    from conversion import encoding_args,plan_audio
    track.source.check()
    plan=plan_audio(track,settings)
    if plan.mode=="copy":
        before = payload_hash(track.path, cancel)
        shutil.copyfile(track.path, dest)
    else:
        args = ["-y", "-i", track.path, "-map", "0:a:0", "-vn", "-sn", "-dn", "-map_metadata", "-1"]
        args += encoding_args(track,settings,plan)
        tools.ff([*args, "-threads", "1", dest], cancel)
        after_profile, _, _ = read_audio(dest, tools, cancel)
        if after_profile.codec!=plan.codec or after_profile.rate!=plan.rate or after_profile.channels!=plan.channels or abs(after_profile.seconds-track.profile.seconds)>0.18 or plan.bits and after_profile.bits!=plan.bits:
            raise ValueError(tr('转换后的声道数或时长未通过校验'))
        if plan.mode=="remux" and tools.encoded_hash(track.path, cancel) != tools.encoded_hash(dest, cancel):
            raise ValueError(tr('AAC 封装前后的编码音频不一致'))
        if settings.verify_pcm and track.profile.lossless and plan.codec in ("flac","alac") and plan.pcm_unchanged:
            if tools.decoded_hash(track.path, cancel) != tools.decoded_hash(dest, cancel):
                raise ValueError(tr('无损转换前后的 PCM 校验不一致'))
        elif settings.verify_pcm:
            tools.decoded_hash(dest,cancel)
        before = payload_hash(dest, cancel)
    from apple import device_settings,compatibility_issue
    patch_tags(dest, track.tags, cover,device_settings(settings).id3_version)
    if payload_hash(dest, cancel) != before:
        raise ValueError(tr('写入标签后音频数据发生变化'))
    if settings.output_profile!="library":
        profile,_,_=read_audio(dest,tools,cancel)
        if issue:=compatibility_issue(profile,settings,dest.suffix):raise ValueError(issue)
    track.source.check()
    return before
