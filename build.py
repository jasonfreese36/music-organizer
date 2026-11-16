"""Optimized Nuitka/GCC release build with a PyInstaller fallback."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from model import VERSION
from prepare import ROOT,RES,digest,prepare


def source_files():
    for path in sorted(ROOT.iterdir()):
        if path.is_file() and (path.suffix in {".py",".md",".txt",".manifest"} or path.name in {"COPYING","LICENSE",".gitignore",".gitattributes"}):yield path
    for folder in ("resources","native","docs",".github"):
        for path in sorted((ROOT/folder).rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".pyc",".pyo"}:continue
            if folder=="resources" and "tools" in path.relative_to(RES).parts:continue
            yield path


def source_identity():
    value=hashlib.sha256()
    for path in source_files():
        value.update(path.relative_to(ROOT).as_posix().encode());value.update(bytes.fromhex(digest(path)))
    return value.hexdigest()


def bundle_native(folder):
    folder.mkdir(parents=True,exist_ok=True)
    shutil.copytree(RES,folder,dirs_exist_ok=True,ignore=shutil.ignore_patterns("tools","NativeTools.zip"))
    files=sorted(p for p in (RES/"tools").iterdir() if p.is_file())
    manifest={p.name:digest(p) for p in files}
    with zipfile.ZipFile(folder/"NativeTools.zip","w",zipfile.ZIP_STORED) as package:
        package.writestr("Manifest.json",json.dumps(manifest,sort_keys=True))
        for path in files:package.write(path,path.name)


def build(output,compiler="nuitka",jobs=8):
    prepare();output.mkdir(parents=True,exist_ok=True);identity=source_identity()
    if compiler=="nuitka":
        data=ROOT/"_build/nuitka-data";bundle_native(data)
        command=[sys.executable,"-m","nuitka","--standalone","--onefile","--mingw64","--experimental=force-mingw64",
                 "--lto=yes",f"--jobs={jobs}","--assume-yes-for-downloads","--show-scons","--enable-plugin=tk-inter",
                 "--onefile-no-dll","--onefile-cache-mode=temporary",
                 "--windows-console-mode=disable","--output-filename=MusicOrganizer.exe",f"--output-dir={ROOT/'_build/nuitka'}",
                 f"--onefile-tempdir-spec={{TEMP}}/MusicOrganizer/{VERSION}-{identity[:12]}-{{PID}}-{{TIME_US}}",
                 f"--include-data-dir={data}=resources","--include-package=mutagen","--include-package-data=certifi",
                 "--include-package-data=opencc","--include-package-data=customtkinter","--include-module=PIL._tkinter_finder",
                 f"--windows-icon-from-ico={RES/'app.ico'}","--company-name=Music Organizer Contributors",
                 "--product-name=Music Organizer",f"--product-version={VERSION}",f"--file-version={VERSION}",
                 "--file-description=Music Organizer - Audio Library Tool",f"--report={output/'Compilation.xml'}",str(ROOT/"main.py")]
    else:
        command=[sys.executable,"-m","PyInstaller","--noconfirm","--clean","--onefile","--windowed","--noupx",
                 "--name","MusicOrganizer","--distpath",str(output),"--workpath",str(ROOT/"_build/pyinstaller"),
                 "--specpath",str(ROOT),"--icon",str(RES/"app.ico"),"--version-file",str(ROOT/"version.txt"),
                 "--manifest",str(ROOT/"app.manifest"),"--add-data",str(RES)+os.pathsep+"resources",
                 "--collect-all","mutagen","--collect-data","certifi","--collect-data","opencc",
                 "--collect-data","customtkinter","--hidden-import","PIL._tkinter_finder",str(ROOT/"main.py")]
    log=output/"Build.log"
    with log.open("w",encoding="utf-8") as stream:subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,check=True)
    target=output/"MusicOrganizer.exe"
    if compiler=="nuitka":
        text=log.read_text(encoding="utf-8")
        if "-O3" not in text or "-flto" not in text:raise ValueError("Build log did not confirm GCC -O3 and LTO")
        shutil.copyfile(ROOT/"_build/nuitka/MusicOrganizer.exe",target)
    for name in ("README.md","README.zh-CN.md","LICENSE","THIRD_PARTY_NOTICES.md"):shutil.copyfile(ROOT/name,output/name)
    with zipfile.ZipFile(output/"MusicOrganizer-Source.zip","w",zipfile.ZIP_DEFLATED,compresslevel=9) as package:
        for path in source_files():package.write(path,"MusicOrganizer-Source/"+path.relative_to(ROOT).as_posix())
    manifest=dict(version=VERSION,compiler=compiler,optimization="GCC -O3 + LTO" if compiler=="nuitka" else "Python bytecode / optimized native tools",
                  nuitka=importlib.metadata.version("nuitka") if compiler=="nuitka" else None,source_sha256=identity,
                  python=sys.version,exe_sha256=digest(target),native_tools={p.name:digest(p) for p in sorted((RES/"tools").iterdir()) if p.is_file()})
    (output/"Build.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    refresh_checksums(output)
    print(json.dumps(dict(exe=str(target),size=target.stat().st_size,sha256=manifest["exe_sha256"],optimization=manifest["optimization"]),indent=2))


def refresh_checksums(output):
    files=[p for p in sorted(output.iterdir()) if p.is_file() and p.name not in {"SHA256.txt","Build.log","Compilation.xml"}]
    (output/"SHA256.txt").write_text("\n".join(digest(p)+"  "+p.name for p in files)+"\n",encoding="utf-8")


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,default=Path.cwd()/"dist")
    parser.add_argument("--compiler",choices=("nuitka","pyinstaller"),default="nuitka");parser.add_argument("--jobs",type=int,default=8)
    args=parser.parse_args()
    if not 1<=args.jobs<=64:parser.error("--jobs must be 1–64")
    build(args.output.resolve(),args.compiler,args.jobs)
