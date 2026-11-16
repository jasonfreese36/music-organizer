import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from prepare import ROOT, RES, digest, prepare


def build(output):
    prepare()
    output.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed", "--noupx",
               "--name", "MusicOrganizer", "--distpath", str(output), "--workpath", str(ROOT/"_build"),
               "--specpath", str(ROOT), "--icon", str(RES/"app.ico"),
               "--version-file", str(ROOT/"version.txt"), "--manifest", str(ROOT/"app.manifest"),
               "--add-data", str(RES)+os.pathsep+"resources", "--collect-all", "mutagen",
               "--collect-data", "certifi", "--collect-data", "opencc", "--collect-data", "customtkinter",
               "--hidden-import", "PIL._tkinter_finder", str(ROOT/"main.py")]
    subprocess.run(command, cwd=ROOT, check=True)
    target = output / "MusicOrganizer.exe"
    shutil.copyfile(ROOT / "README.zh-CN.md", output / "使用说明.md")
    for name in ("README.md","LICENSE","THIRD_PARTY_NOTICES.md"):
        shutil.copyfile(ROOT/name,output/name)
    with zipfile.ZipFile(output/"MusicOrganizer-Source.zip", "w", zipfile.ZIP_DEFLATED, compresslevel=9) as package:
        for path in sorted(ROOT.iterdir()):
            if path.is_file() and (path.suffix in {".py", ".md", ".txt", ".manifest"} or path.name in {"COPYING","LICENSE",".gitignore",".gitattributes"}):
                package.write(path, "MusicOrganizer-Source/"+path.name)
        for path in RES.rglob("*"):
            if path.is_file() and "tools" not in path.relative_to(RES).parts and "__pycache__" not in path.parts and path.suffix not in {".pyc",".pyo"}:
                package.write(path, "MusicOrganizer-Source/resources/"+path.relative_to(RES).as_posix())
        for path in (ROOT/"native").rglob("*"):
            if path.is_file():package.write(path,"MusicOrganizer-Source/native/"+path.relative_to(ROOT/"native").as_posix())
        for folder in ("docs",".github"):
            for path in (ROOT/folder).rglob("*"):
                if path.is_file():package.write(path,"MusicOrganizer-Source/"+path.relative_to(ROOT).as_posix())
    checks = {p.name: digest(p) for p in (target, output/"MusicOrganizer-Source.zip")}
    (output/"SHA256.txt").write_text("\n".join(sha+"  "+name for name, sha in checks.items())+"\n", encoding="utf-8")
    print(json.dumps(dict(exe=str(target), size=target.stat().st_size, sha256=checks[target.name]), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path.cwd()/"dist")
    args = parser.parse_args()
    build(args.output.resolve())
