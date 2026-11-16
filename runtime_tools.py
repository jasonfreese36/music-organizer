"""Verified native-tool cache for compiled single-file releases."""
import hashlib
import json
import os
import shutil
import tempfile
import time
import zipfile
from functools import lru_cache
from pathlib import Path


def digest(path):
    value=hashlib.sha256()
    with path.open("rb") as handle:
        while chunk:=handle.read(4*1024**2):value.update(chunk)
    return value.hexdigest()


def _safe_folder(path):
    from model import reparse
    if any(p.exists() and reparse(p) for p in (path,*path.parents)):
        raise ValueError("Runtime cache path contains a link or reparse point")


@lru_cache(maxsize=1)
def unpack_tools(bundle):
    bundle=Path(bundle);identity=digest(bundle)
    root=Path(os.environ.get("LOCALAPPDATA",str(Path.home()/"AppData/Local")))/"MusicOrganizer/RuntimeTools"
    _safe_folder(root);root.mkdir(parents=True,exist_ok=True)
    dest=root/identity[:24];_safe_folder(dest)
    import msvcrt
    with (root/(identity[:24]+".lock")).open("a+b") as lock:
        if not lock.tell():lock.write(b"0");lock.flush()
        started=time.monotonic()
        while True:
            lock.seek(0)
            try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1);break
            except OSError:
                if time.monotonic()-started>120:raise TimeoutError("Timed out waiting for native tool extraction")
                time.sleep(.1)
        try:
            with zipfile.ZipFile(bundle) as package:
                manifest=json.loads(package.read("Manifest.json"))
                if not isinstance(manifest,dict) or not manifest:raise ValueError("Invalid native tool manifest")
                expected=set(manifest)|{"Manifest.json"}
                if set(package.namelist())!=expected or len(package.namelist())!=len(expected):raise ValueError("Invalid native tool bundle")
                for name,sha in manifest.items():
                    if Path(name).name!=name or name in (".","..") or ":" in name or "/" in name or "\\" in name or len(sha)!=64:
                        raise ValueError("Invalid native tool filename or digest")
                ready=dest/"Ready.json"
                try:
                    stamps=json.loads(ready.read_text(encoding="utf-8"));valid=stamps.get("bundle")==identity
                    for name,sha in manifest.items():
                        path=dest/name;_safe_folder(path);st=path.stat()
                        if stamps.get(name)!=[st.st_size,st.st_mtime_ns] and digest(path)!=sha:valid=False;break
                    if valid:return dest
                except (OSError,ValueError,KeyError,TypeError):pass
                if dest.exists():
                    # App-owned fingerprinted cache, never a music directory.
                    _safe_folder(dest)
                    if dest.parent.resolve()!=root.resolve():raise ValueError("Invalid runtime cache target")
                    shutil.rmtree(dest)
                with tempfile.TemporaryDirectory(prefix="extract-",dir=root) as temp:
                    stage=Path(temp)/"tools";stage.mkdir();stamps={"bundle":identity}
                    for name,sha in manifest.items():
                        path=stage/name
                        with package.open(name) as src,path.open("wb") as out:shutil.copyfileobj(src,out,4*1024**2)
                        if digest(path)!=sha:raise ValueError("Native tool checksum mismatch: "+name)
                        st=path.stat();stamps[name]=[st.st_size,st.st_mtime_ns]
                    (stage/"Ready.json").write_text(json.dumps(stamps),encoding="utf-8");stage.rename(dest)
            return dest
        finally:lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
