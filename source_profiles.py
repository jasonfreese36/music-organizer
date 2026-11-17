"""Persist manual metadata per physical source, independent of batch membership."""
import json
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from inventory import infer_track
from model import short_hash,write_atomic


def profile_path(root,folder):
    # This is also the profile filename used before multi-source support.
    return folder/(short_hash(str(Path(root).resolve()))+".json")


def read_profile(root,folder):
    try:
        value=json.loads(profile_path(root,folder).read_text(encoding="utf-8"))
        if not isinstance(value,dict):return {}
        if any(not isinstance(value.get(k,{}),dict) for k in ("tags","covers","selections","tracks")):return {}
        return value
    except (ValueError,OSError):return {}


def edit_keys(items):
    result={}
    for item in items:
        if item.kind in ("audio","ncm","encrypted","cue","iso"):
            result[infer_track(item).edit_key]=infer_track(replace(item,namespace="")).edit_key
    return result


def load_profiles(items,folder):
    loaded={root:read_profile(root,folder) for root in {i.source_root for i in items}}
    overrides,covers,selections={},{},{}
    for root,document in loaded.items():
        members=[i for i in items if i.source_root==root]
        for runtime,local in edit_keys(members).items():
            for field,target in (("tags",overrides),("covers",covers),("selections",selections)):
                if local in document.get(field,{}):target[runtime]=document[field][local]
    updated=[]
    for item in items:
        edits=loaded[item.source_root].get("tracks",{}).get(str(item.rel),{})
        if not isinstance(edits,dict):edits={}
        updated.append(replace(item,tags=item.tags|edits,edits=edits))
    return updated,overrides,covers,selections


def save_profiles(items,folder,overrides,covers,selections):
    groups=defaultdict(list)
    for item in items:groups[item.source_root].append(item)
    for root,members in groups.items():
        document=read_profile(root,folder)
        keys=edit_keys(members)
        for field,values in (("tags",overrides),("covers",covers),("selections",selections)):
            saved=dict(document.get(field,{}))
            for runtime,local in keys.items():
                saved.pop(local,None)
                if runtime in values:saved[local]=values[runtime]
            document[field]=saved
        saved=dict(document.get("tracks",{}))
        for item in members:
            saved.pop(str(item.rel),None)
            if item.edits:saved[str(item.rel)]=item.edits
        document.update(schema=2,tracks=saved)
        write_atomic(profile_path(root,folder),json.dumps(document,ensure_ascii=False,indent=2).encode("utf-8"))
