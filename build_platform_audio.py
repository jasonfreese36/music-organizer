"""Build the reviewed, vendored offline native reader with a pinned Go SDK."""
import hashlib
import json
import os
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/"native/platformaudio"
SDK=dict(version="go1.27.4",filename="go1.27.4.windows-amd64.zip",
         sha256="178ab98950ac69ab25069307dc6ade79f3816e414cce95b4da166a115cde1e7e")


def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as handle:
        while data:=handle.read(4*1024**2):h.update(data)
    return h.hexdigest()


def build_platform_audio(force=False):
    inputs=hashlib.sha256()
    for path in sorted(SOURCE.rglob("*")):
        if path.is_file():inputs.update(path.relative_to(SOURCE).as_posix().encode());inputs.update(path.read_bytes())
    inputs.update(SDK["version"].encode())
    fingerprint=inputs.hexdigest()
    target=ROOT/"resources/tools/platformaudio.exe"
    metadata=ROOT/"resources/PlatformAudio.json"
    if not force and target.is_file() and metadata.is_file():
        old=json.loads(metadata.read_text(encoding="utf-8"))
        if old.get("source_sha256")==fingerprint and old.get("binary_sha256")==sha(target):return old
    downloads=ROOT/"_downloads";downloads.mkdir(exist_ok=True)
    archive=downloads/SDK["filename"]
    if not archive.is_file() or sha(archive)!=SDK["sha256"]:
        with urllib.request.urlopen("https://go.dev/dl/"+SDK["filename"],timeout=60) as response,archive.open("wb") as out:shutil.copyfileobj(response,out)
    if sha(archive)!=SDK["sha256"]:raise ValueError("Go SDK checksum mismatch")
    folder=downloads/SDK["version"]
    compiler=folder/"go/bin/go.exe"
    if not compiler.is_file():
        with zipfile.ZipFile(archive) as package:
            for entry in package.infolist():
                rel=Path(entry.filename)
                if rel.is_absolute() or ".." in rel.parts:raise ValueError("Unsafe Go archive")
            package.extractall(folder)
    env=dict(os.environ,CGO_ENABLED="0",GOTOOLCHAIN="local",GOTELEMETRY="off",GOOS="windows",GOARCH="amd64")
    subprocess.run([compiler,"test","-mod=vendor","./..."],cwd=SOURCE,env=env,check=True)
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_suffix(".new.exe")
    try:
        subprocess.run([compiler,"build","-mod=vendor","-buildvcs=false","-trimpath","-ldflags=-s -w","-o",temp,"."],cwd=SOURCE,env=env,check=True)
        subprocess.run([temp,"--self-test"],check=True,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        os.replace(temp,target)
    finally:temp.unlink(missing_ok=True)
    legal=ROOT/"resources/Licenses/PlatformAudio";legal.mkdir(parents=True,exist_ok=True)
    for name in ("LICENSE-Unlock-Music","LICENSE-MusicUnlock","LICENSE-TuneWeave","LICENSE-KGG-Dec","NOTICES-MusicUnlock.md","README.md"):
        shutil.copyfile(SOURCE/name,legal/name)
    shutil.copyfile(folder/"go/LICENSE",legal/"LICENSE-Go")
    shutil.copyfile(SOURCE/"vendor/golang.org/x/crypto/LICENSE",legal/"LICENSE-Go-Crypto")
    info=dict(version="1.4.0",compiler=SDK,source_sha256=fingerprint,binary_sha256=sha(target),
              sources=dict(unlock_music="lishanxin/unlockMusic@380ed78b6b0bcc70250e9a97ed5189795c4466f2",
                           legacy_kgm="Lin-M11/MusicUnlock@58c4f9b6e13ffc8dd8bd86273f39fe9f585ec428",
                           kgg="lizipeng0013/kgg-dec.mirror@b3bb5cb15933fb6c2c859665041d728e24777ca9",
                           mg3d="MOPELotus/TuneWeave@84bc7b34935198caa40f612876f4624a17b40221"))
    metadata.write_text(json.dumps(info,indent=2),encoding="utf-8")
    return info


if __name__=="__main__":print(json.dumps(build_platform_audio(),indent=2))
