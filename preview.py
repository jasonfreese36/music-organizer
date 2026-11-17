"""Read-only plan using the same naming and conversion functions as the writer."""
from i18n import tr
from collections import Counter,defaultdict
from pathlib import Path

from conversion import plan_audio
from inventory import infer_track
from model import number
from naming import album_folder,track_relative


def preview_rows(items,settings,tags_for=None):
    tracks=[];rows=[];groups=defaultdict(list)
    cue_images=set()
    from formats import parse_cue,resolve_cue_file
    for item in items:
        if item.kind=="cue":
            try:
                source_root=item.source_root
                _,parts=parse_cue(item.path)
                cue_images.update(resolve_cue_file(item.path,p.file,source_root) for p in parts)
            except (ValueError,OSError):pass
    for item in items:
        if item.kind not in ("audio","ncm","encrypted","iso","cue"):continue
        if item.kind in ("ncm","encrypted","iso","cue") or item.path in cue_images:
            if item.crypto:
                from platform_audio import STATUS
                rows.append(dict(source=str(item.library_rel),rule=tr('解密后匹配'),conversion=item.crypto.get("name","")+" · "+STATUS.get(item.crypto.get("state"),tr('待处理')),target="",note=item.crypto.get("detail","")));continue
            rows.append(dict(source=str(item.library_rel),rule=tr('展开后匹配'),conversion=tr('解密、提取或 CUE 分轨后确定'),target="",note=tr('此预览不会解密或展开原盘')));continue
        if not item.profile or item.error:
            rows.append(dict(source=str(item.library_rel),rule="",conversion=tr('无法规划'),target="",note=item.error));continue
        track=infer_track(item)
        if tags_for:track.tags=dict(tags_for(item))
        tracks.append(track)
    compilations=defaultdict(list)
    for track in tracks:compilations[(str(track.source_group),track.tags.get("album"))].append(track)
    for members in compilations.values():
        if len({t.tags.get("artist") for t in members})>1 and not any(t.source.tags.get("albumartist") for t in members) and all(t.tags.get("albumartist")==t.tags.get("artist") for t in members):
            for track in members:track.tags["albumartist"]="Various Artists"
    for track in tracks:groups[(str(track.source_group),track.tags.get("albumartist"),track.tags.get("album"),track.variant)].append(track)
    for members in groups.values():
        multidisc=len({number(t.tags.get("discnumber"))[0] or 1 for t in members})>1 or any(number(t.tags.get("discnumber"))[1]>1 for t in members)
        members.sort(key=lambda t:(number(t.tags.get("discnumber"))[0],number(t.tags.get("tracknumber"))[0],str(t.path)))
        for i,track in enumerate(members,1):
            plan=plan_audio(track,settings)
            rel=album_folder(members[0],settings)/track_relative(track,settings,plan,i,multidisc)
            note=""
            if plan.codec=="flac" and not track.profile.lossless:note=tr('有损来源转 FLAC 不恢复音质')
            rows.append(dict(source=str(track.source.library_rel),rule=plan.rule or tr('默认设置'),conversion=plan.description,target=str(rel),note=note))
    counts=Counter(r["target"].casefold() for r in rows if r["target"])
    for row in rows:
        if row["target"] and counts[row["target"].casefold()]>1:row["note"]+=("；" if row["note"] else "")+tr('存在同名目标，写入时校验去重或添加后缀')
    return sorted(rows,key=lambda r:r["source"].casefold())
