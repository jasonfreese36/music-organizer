"""Catalog coverage, placeholder compatibility and metadata isolation."""
import ast
import json
from pathlib import Path
from string import Formatter

from i18n import select_language,tr


def run():
    root=Path(__file__).parent
    catalog=json.loads((root/"resources/i18n/en.json").read_text(encoding="utf-8"))
    used=set()
    for path in root.glob("*.py"):
        if path.name.startswith("test_"):continue
        tree=ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=="tr":
                assert len(node.args)==1 and isinstance(node.args[0],ast.Constant),path
                key=node.args[0].value;used.add(key)
                assert key in catalog and catalog[key],(path,key)
                fields=lambda value:[(field,spec,conversion) for _,field,spec,conversion in Formatter().parse(value) if field is not None]
                assert sorted(fields(key))==sorted(fields(catalog[key])),(key,catalog[key])
    select_language("en")
    assert tr("高级设置")=="Advanced"
    from model import Settings,match_name
    from inventory import infer_track
    from conversion import plan_audio
    from model import Item,Profile
    item=Item(Path("Sample.flac"),Path("Sample.flac"),100,0,"audio",Profile("flac",96000,2,24,60),dict(title="中文歌名",artist="張學友",album="真情流露"))
    track=infer_track(item)
    assert track.tags["title"]=="中文歌名" and track.tags["artist"]=="張學友" and track.tags["album"]=="真情流露"
    assert match_name("張學友")==match_name("张学友")
    assert "Device" not in plan_audio(track,Settings()).description
    try:Settings(output_profile="invalid")
    except ValueError as exc:assert str(exc)=="Invalid device output preset",str(exc)
    else:raise AssertionError("validation missing")
    select_language("zh_CN");assert tr("高级设置")=="高级设置"
    print(json.dumps(dict(catalog_entries=len(catalog),translated_messages=len(used),placeholders=True,metadata_unchanged=True),indent=2))


if __name__=="__main__":run()
