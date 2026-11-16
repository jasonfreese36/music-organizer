"""Container identification only. Importable without audio or GUI dependencies."""
import re
from pathlib import Path

KGM_MAGIC=bytes.fromhex("7cd532eb86027f4ba8afa68e0fff9914")
VPR_MAGIC=bytes.fromhex("0528bc96e9e45a4391aabdd07af53631")
PLATFORMS={"netease":"网易云音乐","qq":"QQ 音乐","kugou":"酷狗音乐","kuwo":"酷我音乐","migu":"咪咕音乐"}
ARCHIVE_NAMES={"netease":"NetEase Music","qq":"QQ Music","kugou":"Kugou Music","kuwo":"Kuwo Music","migu":"Migu Music"}
FAMILY_PLATFORM={"ncm":"netease","netease_uc":"netease","qq":"qq","qq_tm":"qq","kugou":"kugou","kuwo":"kuwo","migu":"migu","migu_mgm":"migu"}
_TOKEN=r"(?:ncm|uc|qmc(?:[0-9]|flac|ogg|ra)?|mflac[0-9ahlm]*|mgg[0-9ahlm]*|mmp4|tkm|bkc(?:mp3|m4a|flac|wav|ape|ogg|wma)|tm[0236]|kgm|kgma|vpr|kgg|kwm|kwma|mg3d|mgm|666c6163|6d7033|6f6767|6d3461|776176)"
ENCRYPTED_NAME=re.compile(r"\.((?:"+_TOKEN+r"))(?:\.(?:flac|ogg|mp3|m4a))?$",re.I)
ENCRYPTED_EXTS={".ncm",".uc",".qmc",".qmcflac",".qmcogg",".qmcra",".mflac",".mgg",".mmp4",".tkm",".kgm",".kgma",".vpr",".kgg",".kwm",".kwma",".mg3d",".mgm"}
ENCRYPTED_EXTS|={".qmc"+str(i) for i in range(10)}|{"."+a+b for a in ("mflac","mgg") for b in list("0123456789ahlm")}
ENCRYPTED_EXTS|={".bkc"+ext for ext in ("mp3","m4a","flac","wav","ape","ogg","wma")}|{".tm0",".tm2",".tm3",".tm6"}


def suffix_family(path):
    match=ENCRYPTED_NAME.search(Path(path).name)
    if not match:return ""
    ext=match[1].lower()
    if ext=="ncm":return "ncm"
    if ext=="uc":return "netease_uc"
    if ext.startswith("tm"):return "qq_tm"
    if ext in ("kgm","kgma","vpr","kgg"):return "kugou"
    if ext in ("kwm","kwma"):return "kuwo"
    if ext=="mg3d":return "migu"
    if ext=="mgm":return "migu_mgm"
    return "qq"


def sniff_plain(data):
    if data.startswith((b"fLaC",b"ID3",b"OggS",b"MAC ",b"wvpk")):return True
    if len(data)>=12 and (data[:4]==b"RIFF" and data[8:12]==b"WAVE" or data[4:8]==b"ftyp"):return True
    return len(data)>=4 and data[0]==255 and data[1]&0xE0==0xE0


def detect_platform(path):
    family=suffix_family(path)
    if not family and Path(path).suffix.lower() not in (".flac",".mp3",".m4a",".wav",".ogg",".aac"):return ""
    with Path(path).open("rb") as handle:
        head=handle.read(64)
        if head.startswith(b"CTENFDAM"):return "ncm"
        if head[:16] in (KGM_MAGIC,VPR_MAGIC):return "kugou"
        if head.startswith(b"yeelion-kuwo"):return "kuwo"
        if head.startswith(b"QQMU"):return "qq_tm"
        if family:return family
        if not sniff_plain(head):
            handle.seek(0,2)
            if handle.tell()>=16:
                handle.seek(-16,2);tail=handle.read(16)
                if tail.endswith((b"musicex\x00",b"STag",b"QTag")):return "qq"
    return ""


def original_stem(path):
    name=Path(path).name
    match=ENCRYPTED_NAME.search(name)
    return name[:match.start()] if match else Path(path).stem
