"""Check bundled-tool extraction, repair, path bounds and explicit replacement."""
import argparse
import hashlib
import json
import os
import zipfile
from pathlib import Path

from runtime_tools import unpack_tools


def run(root):
    root.mkdir(parents=True,exist_ok=True)
    previous=os.environ.get("LOCALAPPDATA");override=os.environ.pop("MUSIC_ORGANIZER_TOOLS",None)
    try:
        os.environ["LOCALAPPDATA"]=str(root/"State")
        data=b"generated native tool placeholder"
        bundle=root/"NativeTools.zip"
        with zipfile.ZipFile(bundle,"w") as package:
            package.writestr("Manifest.json",json.dumps({"ffmpeg.exe":hashlib.sha256(data).hexdigest()}));package.writestr("ffmpeg.exe",data)
        folder=unpack_tools(bundle);assert (folder/"ffmpeg.exe").read_bytes()==data
        # New process/cache lookup detects a changed tool and restores the verified bundle.
        (folder/"ffmpeg.exe").write_bytes(b"corrupted")
        unpack_tools.cache_clear();assert (unpack_tools(bundle)/"ffmpeg.exe").read_bytes()==data
        invalid=root/"Invalid.zip"
        with zipfile.ZipFile(invalid,"w") as package:
            package.writestr("Manifest.json",json.dumps({"../escape.exe":hashlib.sha256(data).hexdigest()}));package.writestr("../escape.exe",data)
        try:unpack_tools(invalid)
        except ValueError:pass
        else:raise AssertionError("Unsafe archive accepted")
        assert not (root/"escape.exe").exists()
        os.environ["MUSIC_ORGANIZER_TOOLS"]=str(root/"Modified tools")
        from media import resource
        assert resource("tools/ffmpeg.exe")==root/"Modified tools/ffmpeg.exe"
        print(json.dumps(dict(passed=True,extraction_verified=True,corruption_repaired=True,path_escape_rejected=True,modified_tools_supported=True),indent=2))
    finally:
        unpack_tools.cache_clear()
        if previous is None:os.environ.pop("LOCALAPPDATA",None)
        else:os.environ["LOCALAPPDATA"]=previous
        if override is None:os.environ.pop("MUSIC_ORGANIZER_TOOLS",None)
        else:os.environ["MUSIC_ORGANIZER_TOOLS"]=override


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--root",type=Path,required=True);run(parser.parse_args().root.resolve())
