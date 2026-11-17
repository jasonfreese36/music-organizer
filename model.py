from i18n import tr
import csv
import hashlib
import io
import json
import math
import os
import re
import stat
import threading
import unicodedata
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from opencc import OpenCC
from platform_formats import ENCRYPTED_EXTS


APP_NAME = "Music Organizer"
VERSION = "1.5.0"
ALBUMS = "Albums"
ARCHIVES = "Disc Archives"
REVIEW = "Needs Review"
RECORDS = "Library Records"
PLAYLISTS = "Playlists"

NATIVE = {".mp3", ".flac", ".m4a"}
SUPPORTED = NATIVE | {
    ".aac", ".alac", ".ape", ".aif", ".aiff", ".wav", ".wave", ".wv", ".tta",
    ".wma", ".ogg", ".oga", ".opus", ".mpc", ".mp2", ".m4b", ".mka", ".tak",
    ".ac3", ".dts", ".dsf", ".dff", ".ncm", ".iso", ".cue",
}
SUPPORTED |= ENCRYPTED_EXTS
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
SIDECARS = IMAGE_EXTS | {".log", ".md5", ".sfv", ".accurip", ".txt", ".pdf"}
LOSSLESS_CODECS = {"flac", "alac", "ape", "wavpack", "tta", "tak", "wmalossless", "als", "shorten", "mlp", "truehd"}
FIELDS = ("title", "artist", "album", "albumartist", "tracknumber", "discnumber",
          "date", "genre", "composer", "label", "catalognumber", "barcode", "isrc")
PLATFORM = re.compile(
    r"^(?:163\s*key\s*\(don't modify\)|(?:xiami|netease|cloudmusic|qqmusic|kuwo|kugou)"
    r"(?:[:_/-]|(?:track|album|song|music)?id\b)|\d{4,}[_-]\d{4,}(?:[_-][a-z0-9]+)*$)", re.I)
DISC_FOLDER = re.compile(r"^(?:cd|disc|disk)[ _.-]*0*(\d+)(?:\b.*|$)", re.I)
LP = re.compile(r"(?<![\w])(?:vinyl(?:[ _-]rip)?|lp[ _-]rip|needle[ _-]?drop)(?![\w])|黑[胶膠]", re.I)
EDITION = re.compile(
    r"(?<!\w)(?:mono|remaster(?:ed)?|deluxe|expanded|anniversary|hi[ -]?res|24[ -]?bit|"
    r"first press(?:ing)?|original master|mobile fidelity|mfsl|sacd|shm[ -]?cd|xr[ -]?cd)(?!\w)", re.I)
TRACK_PREFIX = re.compile(r"^\s*(\d{1,3})\s*(?:[-._–—]\s*|\s+)(?=\S)")
_BAD_PATH = re.compile(r"[\x00-\x1f<>:\"/\\|?*]+")
_RESERVED = re.compile(r"^(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)", re.I)
_CHINESE = OpenCC("t2s")
_CHINESE.convert("張學友")  # Initialize dictionaries before scanner/lookup worker threads start.


class Cancelled(Exception):
    pass


class Cancel:
    def __init__(self):
        self.event = threading.Event()

    def check(self):
        if self.event.is_set():
            raise Cancelled(tr('已停止'))

    def stop(self):
        self.event.set()


def normalize(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def match_name(value):
    return _match_key(normalize(value))


@lru_cache(maxsize=32768)
def _match_key(value):
    if any("\u3400" <= c <= "\u9fff" for c in value):
        value = _CHINESE.convert(value)
    return "".join(c for c in value if c.isalnum())


def clean_text(value):
    value = unicodedata.normalize("NFC", str(value or "")).strip("\x00 \t\r\n")
    return value if value and not PLATFORM.match(value) else ""


def short_hash(value):
    return hashlib.sha256(str(value).encode("utf-8", "surrogatepass")).hexdigest()[:8]


def component(value, limit=78):
    value = _BAD_PATH.sub(" - ", unicodedata.normalize("NFC", str(value or "")))
    value = " ".join(value.split()).strip(" .") or "Unknown"
    if _RESERVED.match(value):
        value = "_" + value
    if len(value) > limit:
        value = value[:limit-11].rstrip(" .") + " [" + short_hash(value) + "]"
    return value


def number(value):
    match = re.match(r"\s*(\d{1,4})(?:\s*/\s*(\d{1,4}))?", str(value or ""))
    return tuple(int(n or 0) for n in match.groups()) if match else (0, 0)


def count_tag(current, total=0):
    return f"{current}/{total}" if total and current else str(current) if current else ""


def year(value):
    match = re.search(r"(?<!\d)((?:18|19|20)\d{2})(?!\d)", str(value or ""))
    return match[1] if match else ""


def first(values):
    if isinstance(values, (list, tuple)):
        return next((cleaned for value in values if (cleaned := clean_text(value))), "")
    return clean_text(values)


def bytes_hash(path, cancel, limit=None):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while limit is None or limit > 0:
            cancel.check()
            block = handle.read(4 * 1024**2 if limit is None else min(limit, 4 * 1024**2))
            if not block:
                break
            digest.update(block)
            if limit is not None:
                limit -= len(block)
    if limit:
        raise ValueError(tr('未读到预期的文件长度'))
    return digest.hexdigest()


def reparse(path):
    return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) &
                                     getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def validated_roots(source, dest):
    if not str(source).strip() or not str(dest).strip():
        raise ValueError(tr('请选择源目录和独立的目标目录'))
    src = Path(source).expanduser().resolve(strict=True)
    out = Path(dest).expanduser().resolve()
    if not src.is_dir():
        raise ValueError(tr('源路径必须是目录'))
    if out.exists() and not out.is_dir():
        raise ValueError(tr('目标路径必须是目录'))
    if src.is_relative_to(out) or out.is_relative_to(src):
        raise ValueError(tr('源目录与目标目录必须彼此独立'))
    if len(str(out)) > 120:
        raise ValueError(tr('目标路径过长，请选择更靠近磁盘根目录的位置'))
    return src, out


def source_roots(sources):
    """Canonical, disjoint roots; the caller's order is the duplicate priority."""
    if isinstance(sources, (str, os.PathLike)):
        sources = [sources]
    roots = []
    for source in sources:
        if not str(source).strip():
            raise ValueError(tr('请选择至少一个源文件夹'))
        root = Path(source).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError(tr('源路径必须是目录'))
        if root in roots:
            continue
        if any(root.is_relative_to(p) or p.is_relative_to(root) for p in roots):
            raise ValueError(tr('源文件夹不能互相包含，请只添加最上层目录'))
        roots.append(root)
    if not roots:
        raise ValueError(tr('请选择至少一个源文件夹'))
    return tuple(roots)


def validated_sources(sources, dest):
    roots = source_roots(sources)
    for root in roots:
        _, out = validated_roots(root, dest)
    return roots, out


def source_label(root):
    return component(root.name, 55) + " [" + short_hash(os.path.normcase(str(root))) + "]"


def at(root, rel):
    rel = Path(rel)
    if rel.anchor or ".." in rel.parts:
        raise ValueError(tr('无效路径 {0}').format(rel))
    target = root / rel
    if not target.resolve().is_relative_to(root):
        raise ValueError(tr('路径超出已选目录 {0}').format(rel))
    return target


@contextmanager
def stage(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".pending-{uuid.uuid4().hex[:16]}{path.suffix}")
    try:
        yield temp
    finally:
        temp.unlink(missing_ok=True)


def write_atomic(path, data):
    with stage(path) as temp:
        temp.write_bytes(data)
        os.replace(temp, path)


def csv_bytes(header, rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(header)
    for row in rows:
        writer.writerow(
            "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value
            for value in row
        )
    return stream.getvalue().encode("utf-8-sig")


@dataclass(frozen=True)
class Profile:
    codec: str
    rate: int
    channels: int
    bits: int
    seconds: float
    layout: str = ""
    bitrate: int = 0
    codec_profile: str = ""

    @property
    def lossless(self):
        return self.codec in LOSSLESS_CODECS or self.codec.startswith(("pcm_", "dsd"))


@dataclass(frozen=True)
class Item:
    path: Path
    rel: Path
    size: int
    mtime: int
    kind: str
    profile: Profile | None = None
    tags: dict = field(default_factory=dict)
    has_cover: bool = False
    error: str = ""
    edits: dict = field(default_factory=dict)
    crypto: dict = field(default_factory=dict)
    root: Path | None = None
    namespace: str = ""

    @property
    def source_root(self):
        if self.root is not None:
            return self.root
        root = self.path
        for _ in self.rel.parts:
            root = root.parent
        return root

    @property
    def library_rel(self):
        return Path(self.namespace) / self.rel if self.namespace else self.rel

    def check(self):
        st = self.path.stat()
        if (st.st_size, st.st_mtime_ns) != (self.size, self.mtime) or reparse(self.path):
            raise ValueError(tr('源文件自扫描后发生变化 {0}').format(self.rel))


@dataclass
class Track:
    source: Item
    path: Path
    profile: Profile
    tags: dict
    variant: str = ""
    has_cover: bool = False
    expected_title: bool = True
    issues: list = field(default_factory=list)
    metadata_source: str = ""
    origin_id: str = ""

    @property
    def source_group(self):
        parent = self.source.library_rel.parent
        if DISC_FOLDER.match(parent.name):
            parent = parent.parent
        return parent

    @property
    def edit_key(self):
        # A mixed directory can contain several releases. Never apply one release's edits to all.
        local_group=self.source.rel.parent
        if DISC_FOLDER.match(local_group.name):local_group=local_group.parent
        parent = local_group.name
        generic = {"music", "albums", "album", "singles", "single", "flac", "mp3", "aac", "wav", "lossless", "recovered audio", "needs review", "audio", "tracks", "songs"}
        album = self.source.tags.get("album")
        if not album:
            album = ("folder:"+str(self.source_group) if parent and parent.casefold() not in generic
                     and self.source.kind not in {"ncm","encrypted","iso"} else self.source.path.stem)
        return str(self.source_group) + "|" + match_name(album)


@dataclass(frozen=True)
class Cover:
    data: bytes
    mime: str
    width: int
    height: int
    source: str


@dataclass(frozen=True)
class Settings:
    online: bool = True
    workers: int = 4
    country: str = "HK"
    keep_sidecars: bool = True
    verify_pcm: bool = True
    sacd_area: str = "stereo"
    sacd_rate: int = 88200
    aac_kbps: int = 256
    tag_sources: tuple = ("musicbrainz", "itunes")
    cover_sources: tuple = ("coverartarchive", "itunes")
    folder_template: str = "Albums/{albumartist}/{year_prefix}{album}{edition}"
    filename_template: str = "{track:02d} - {title}"
    multidisc: str = "subfolder"
    disc_template: str = "Disc {disc:02d}"
    lossless_format: str = "flac"
    lossy_format: str = "preserve"
    reencode_lossy: bool = False
    recompress_flac: bool = False
    resample_mode: str = "preserve"
    sample_rate: int = 44100
    pcm_bits: int = 0
    channels: str = "preserve"
    resampler: str = "swr"
    dither: str = "triangular"
    flac_compression: int = 5
    mp3_mode: str = "vbr"
    mp3_kbps: int = 320
    mp3_vbr: int = 0
    id3_version: str = "preserve"
    write_cover_file: bool = True
    write_playlists: bool = True
    rules: tuple = ()
    decrypt_enabled: bool = True
    decrypt_workers: int = 2
    decrypt_verify: bool = True
    platform_key_file: str = ""
    output_profile: str = "library"
    ipod_model: str = "universal"
    apple_quality: str = "standard"
    apple_archive_mode: str = "none"
    apple_archive_folder: str = ""
    resample_cutoff_enabled: bool = False
    resample_cutoff: float = 98.0
    soxr_precision: int = 28
    soxr_cheby: bool = False
    swr_filter_type: str = "kaiser"
    swr_filter_size: int = 32
    swr_phase_shift: int = 10
    swr_kaiser_beta: float = 9.0
    swr_exact_rational: bool = True
    dither_scale: float = 1.0
    gain_db: float = 0.0
    downmix_normalize: bool = False
    dsd_advanced: bool = False
    dsd_pcm_bits: int = 24
    dsd_gain_db: float = 0.0
    dsd_lowpass_hz: int = 30000
    dsd_lowpass_order: int = 4
    dsd_remove_dc: bool = False

    def __post_init__(self):
        for name in ("workers","sacd_rate","aac_kbps","sample_rate","pcm_bits","flac_compression","mp3_kbps","mp3_vbr","decrypt_workers",
                     "soxr_precision","swr_filter_size","swr_phase_shift","dsd_pcm_bits","dsd_lowpass_hz","dsd_lowpass_order"):
            if type(getattr(self,name)) is not int:raise ValueError(tr('{0} 需要整数').format(name))
        for name in ("online","keep_sidecars","verify_pcm","reencode_lossy","recompress_flac","write_cover_file","write_playlists","decrypt_enabled","decrypt_verify",
                     "resample_cutoff_enabled","soxr_cheby","swr_exact_rational","downmix_normalize","dsd_advanced","dsd_remove_dc"):
            if type(getattr(self,name)) is not bool:raise ValueError(tr('{0} 需要开关值').format(name))
        for name,lower,upper in (("resample_cutoff",80,99.7),("swr_kaiser_beta",2,16),("dither_scale",0,4),
                                 ("gain_db",-24,6),("dsd_gain_db",-24,12)):
            value=getattr(self,name)
            if type(value) not in (int,float) or not math.isfinite(value) or not lower<=value<=upper:
                raise ValueError(tr('{0} 必须是 {1} 到 {2} 之间的有限数值').format(name,lower,upper))
        object.__setattr__(self, "tag_sources", tuple(dict.fromkeys(self.tag_sources)))
        object.__setattr__(self, "cover_sources", tuple(dict.fromkeys(self.cover_sources)))
        if set(self.tag_sources) - {"musicbrainz", "itunes"} or set(self.cover_sources) - {"coverartarchive", "itunes"}:
            raise ValueError(tr('未知的标签或封面来源'))
        if not 1 <= self.workers <= 16 or self.sacd_rate not in (44100,48000,88200,96000,176400,192000,352800,384000):
            raise ValueError(tr('并行数或 SACD 采样率无效'))
        if self.sacd_area not in ("stereo", "multi", "both") or not 96 <= self.aac_kbps <= 512:
            raise ValueError(tr('SACD 声道选项或 AAC 比特率无效'))
        if self.lossless_format not in ("flac", "mp3", "aac") or self.lossy_format not in ("preserve", "flac", "mp3", "aac"):
            raise ValueError(tr('输出格式必须为 FLAC、MP3 或 AAC'))
        if self.resample_mode not in ("preserve", "limit", "fixed", "family") or self.sample_rate not in (8000,16000,22050,24000,32000,44100,48000,88200,96000,176400,192000,352800,384000):
            raise ValueError(tr('采样率设置无效'))
        if self.pcm_bits not in (0,16,24,32) or self.channels not in ("preserve","stereo","mono"):
            raise ValueError(tr('位深或声道设置无效'))
        if self.resampler not in ("swr","soxr") or self.dither not in ("none","rectangular","triangular","triangular_hp","shibata","low_shibata","high_shibata","lipshitz","f_weighted","modified_e_weighted","improved_e_weighted"):
            raise ValueError(tr('重采样或抖动设置无效'))
        if not 15<=self.soxr_precision<=33 or self.swr_filter_type not in ("kaiser","blackman_nuttall","cubic") or not 4<=self.swr_filter_size<=256 or not 0<=self.swr_phase_shift<=16:
            raise ValueError(tr('重采样滤波参数无效'))
        if self.dsd_pcm_bits not in (16,24,32) or self.dsd_lowpass_hz!=0 and not 20000<=self.dsd_lowpass_hz<=100000 or self.dsd_lowpass_order not in (2,4,6,8):
            raise ValueError(tr('DSD 高级转换参数无效'))
        if not 0 <= self.flac_compression <= 12 or self.mp3_mode not in ("vbr","cbr") or not 0 <= self.mp3_vbr <= 9 or self.mp3_kbps not in (64,96,128,160,192,224,256,320):
            raise ValueError(tr('FLAC 压缩级别或 MP3 编码设置无效'))
        if self.id3_version not in ("preserve","3","4") or self.multidisc not in ("subfolder","prefix","flat"):
            raise ValueError(tr('标签版本或多碟命名方式无效'))
        if not 1<=self.decrypt_workers<=8 or not isinstance(self.platform_key_file,str) or len(self.platform_key_file)>32768:
            raise ValueError(tr('平台音频并行数或密钥文件路径无效'))
        if self.output_profile not in {"library","ipod","ios"} or self.ipod_model not in {"universal","classic_nano","shuffle"}:
            raise ValueError(tr('设备输出预设无效'))
        if self.apple_quality not in {"standard","compact","lossless"} or self.apple_archive_mode not in {"none","separate"}:
            raise ValueError(tr('苹果设备品质或原盘归档选项无效'))
        if not isinstance(self.apple_archive_folder,str) or len(self.apple_archive_folder)>32768:
            raise ValueError(tr('原盘归档目录无效'))
        if self.output_profile=="ipod" and self.ipod_model!="classic_nano" and self.apple_quality=="lossless":
            raise ValueError(tr('通用 iPod / shuffle 预设使用 MP3；ALAC 无损选项适用于 classic / nano 或 iPhone / iPad'))
        from naming import validate_templates
        from rules import validate_rules
        validate_templates(self.folder_template,self.filename_template,self.disc_template)
        object.__setattr__(self,"rules",tuple(validate_rules(self.rules)))


class Journal:
    def __init__(self, root):
        self.path = at(root, Path(RECORDS, "Operations.jsonl"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def put(self, action, source, **details):
        row = {"action": action, "source": str(source), **details}
        encoded = (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
        with self.lock, self.path.open("ab") as handle:
            handle.write(encoded)
