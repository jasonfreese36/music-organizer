"""Fetch pinned upstream tools, keep checksums/licenses, and create build resources."""
import hashlib
import importlib.metadata
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent
RES = ROOT / "resources"
DOWNLOADS = ROOT / "_downloads"
TOOLS = RES / "tools"
LICENSES = RES / "Licenses"
ASSETS = {
    "FFmpeg": dict(version="n8.1.3-34-ga35157abb9-20261109 LGPLv3 shared",
        url="https://github.com/FFmpeg-Builds/FFmpeg-Builds/releases/download/autobuild-2026-11-09-12-42/ffmpeg-n8.1.3-34-ga35157abb9-win64-lgpl-shared-8.1.zip",
        sha256="5e1b1ee3d9f85c2c2dedbe9db0036b9232f1f9bdd1a5e644fc7128e4bfcb6877",
        archive="ffmpeg.zip", source="https://github.com/FFmpeg/FFmpeg/tree/a35157abb9",
        build="https://github.com/FFmpeg-Builds/FFmpeg-Builds/releases/tag/autobuild-2026-11-09-12-42"),
    "ncmdump": dict(version="1.5.1", url="https://github.com/taurusxin/ncmdump/releases/download/1.5.1/ncmdump-1.5.1-windows-amd64.zip",
        sha256="bb849221c06b8fdbff42aefb86baea9c07256568658d80f4be72a39a2a1632dc", archive="ncmdump.zip",
        source="https://github.com/taurusxin/ncmdump/tree/1.5.1"),
    "SACD Extract": dict(version="0.9.0", url="https://github.com/dev-zetta/sacd_extract2/releases/download/v0.9.0/sacd_extract-windows-x86_64.zip",
        sha256="e89f666725104662da11506721153d97adc2cac351d94b601cb2afe70648ac81", archive="sacd.zip",
        source="https://github.com/dev-zetta/sacd_extract2/tree/v0.9.0"),
}


def fetch(url, path):
    request = urllib.request.Request(url, headers={"User-Agent": "MusicOrganizer-Build/1.0"})
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(request, timeout=45) as response, path.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while data := handle.read(4*1024**2):
            h.update(data)
    return h.hexdigest()


def prepare():
    TOOLS.mkdir(parents=True, exist_ok=True)
    LICENSES.mkdir(parents=True, exist_ok=True)
    from build_platform_audio import build_platform_audio
    native_reader=build_platform_audio()
    for name, asset in ASSETS.items():
        archive = DOWNLOADS / asset["archive"]
        if not archive.is_file() or digest(archive) != asset["sha256"]:
            fetch(asset["url"], archive)
        if digest(archive) != asset["sha256"]:
            raise ValueError(f"Checksum mismatch: {name}")
        with zipfile.ZipFile(archive) as package:
            for member in package.infolist():
                path = Path(member.filename)
                filename = path.name
                native = filename.casefold() in {"ffmpeg.exe", "ffprobe.exe", "ncmdump.exe", "sacd_extract.exe"} or (name == "FFmpeg" and filename.casefold().endswith(".dll"))
                legal = any(token in filename.casefold() for token in ("license", "copying", "notice"))
                if member.is_dir() or not (native or legal):
                    continue
                target = TOOLS / filename if native else LICENSES / name / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(package.read(member))
    texts = {
        "Application-GPL-3.0.txt": "https://raw.githubusercontent.com/FFmpeg/FFmpeg/a35157abb9/COPYING.GPLv3",
        "ncmdump/LICENSE.txt": "https://raw.githubusercontent.com/taurusxin/ncmdump/1.5.1/LICENSE.txt",
        "FFmpeg/LGPL-3.0.txt": "https://raw.githubusercontent.com/FFmpeg/FFmpeg/a35157abb9/COPYING.LGPLv3",
        "FFmpeg/BUILD.md": "https://raw.githubusercontent.com/FFmpeg-Builds/FFmpeg-Builds/master/README.md",
        "TagLib/COPYING.LGPL": "https://raw.githubusercontent.com/taglib/taglib/v2.0.2/COPYING.LGPL",
        "TagLib/COPYING.MPL": "https://raw.githubusercontent.com/taglib/taglib/v2.0.2/COPYING.MPL",
        "Tcl/license.terms": "https://raw.githubusercontent.com/tcltk/tcl/core-8-6-16/license.terms",
    }
    for rel, url in texts.items():
        target = LICENSES / rel
        if not target.exists():
            fetch(url, target)
    packages = ("mutagen", "Pillow", "certifi", "opencc-python-reimplemented", "customtkinter", "darkdetect", "packaging", "pyinstaller", "nuitka", "zstandard", "ordered-set")
    for package in packages:
        dist = importlib.metadata.distribution(package)
        for entry in dist.files or []:
            if any(part.casefold() in {"licenses", "license", "license.txt", "copying", "copying.txt", "authors", "notice", "notice.txt"}
                   for part in entry.parts):
                src = Path(dist.locate_file(entry))
                if src.is_file() and src.suffix not in {".py", ".pyc", ".pyo"}:
                    target = LICENSES / package / Path(*entry.parts[1:])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, target)
    for rel in ("LICENSE.txt", "tcl/tcl8.6/license.terms", "tcl/tk8.6/license.terms", "tcl/tcl8/license.terms"):
        src = Path(sys.base_prefix) / rel
        if src.is_file():
            target = LICENSES / "Python and Tcl-Tk" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, target)
    manifest = {"native": ASSETS,"platform_audio":native_reader,"python": sys.version, "python_packages": {p: importlib.metadata.version(p) for p in packages},
                "bundled_native_sha256": {p.name: digest(p) for p in sorted(TOOLS.iterdir()) if p.is_file()}}
    (RES / "Dependencies.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copyfile(ROOT / "THIRD_PARTY_NOTICES.md", LICENSES / "THIRD_PARTY_NOTICES.md")
    shutil.copyfile(ROOT / "LICENSE", LICENSES / "Application-MIT.txt")
    shutil.copyfile(ROOT / "LICENSE", ROOT / "COPYING")
    image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, 248, 248), radius=54, fill="#6556DC")
    draw.line([(107, 173), (107, 70), (189, 51), (189, 150)], fill="white", width=15)
    draw.line([(110, 88), (187, 70)], fill="white", width=20)
    draw.ellipse((64, 153, 115, 191), fill="white")
    draw.ellipse((146, 132, 197, 170), fill="white")
    image.save(RES / "app.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(json.dumps(dict(tools=len(manifest["bundled_native_sha256"]), licenses=len(list(LICENSES.rglob("*")))), indent=2))


if __name__ == "__main__":
    prepare()
