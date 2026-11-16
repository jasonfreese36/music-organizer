"""Safe path templates shared by live preview and the actual writer."""
from i18n import tr
import re
import string
from pathlib import Path,PureWindowsPath

from model import ARCHIVES,RECORDS,REVIEW,PLAYLISTS,component,number,year

FOLDER_FIELDS={"albumartist","artist","album","year","year_prefix","date","genre","label","edition"}
FILE_FIELDS=FOLDER_FIELDS|{"title","track","disc","codec","samplerate","bits"}
NUMBERS={"track","disc","samplerate","bits"}
FORMATTER=string.Formatter()
DEFAULT_FOLDER="Albums/{albumartist}/{year_prefix}{album}{edition}"
DEFAULT_FILE="{track:02d} - {title}"


def validate_template(template,allowed,folder=False):
    if not isinstance(template,str) or not template.strip() or len(template)>400:raise ValueError(tr('命名模板需为 1–400 个字符'))
    value=template.replace("\\","/")
    if PureWindowsPath(value).drive or value.startswith("/") or any(p in (".","..","") for p in value.split("/")):
        raise ValueError(tr('模板须为相对路径，不能含盘符、空层级或 . / ..'))
    if not folder and "/" in value:raise ValueError(tr('文件名或碟目录模板不能含目录分隔符'))
    found=set()
    try:
        for literal,field,spec,conversion in FORMATTER.parse(value):
            if re.search(r'[\x00-\x1f<>:"|?*]',literal):raise ValueError(tr('模板的固定文字含 Windows 路径禁用字符'))
            if field is None:continue
            if field not in allowed or conversion or spec and (field not in NUMBERS or spec not in ("d","02d","03d","04d")):
                raise ValueError(tr('不支持的模板字段或格式：{{{0}}}').format(field))
            found.add(field)
    except (KeyError,IndexError) as exc:raise ValueError(tr('模板括号不完整')) from exc
    if not found:raise ValueError(tr('模板至少需要一个资料字段'))
    return found


def validate_templates(folder,filename,disc):
    fields=validate_template(folder,FOLDER_FIELDS,True)
    if "album" not in fields:raise ValueError(tr('专辑目录模板必须包含 {album}，以分开不同专辑'))
    validate_template(filename,FILE_FIELDS)
    validate_template(disc,{"disc"})
    sample=render_parts(folder,{key:"Example" for key in FOLDER_FIELDS})
    if sample.parts[0].casefold() in {v.casefold() for v in (ARCHIVES,RECORDS,REVIEW,PLAYLISTS)}:
        raise ValueError(tr('播放库模板不能使用原盘备份、报告或播放列表的保留目录'))


def context(track,plan=None,position=1):
    tags=track.tags
    date=tags.get("date","")
    y=year(date)
    return dict(albumartist=tags.get("albumartist") or tags.get("artist") or "Unknown Artist",
                artist=tags.get("artist") or tags.get("albumartist") or "Unknown Artist",
                album=tags.get("album") or "Unknown Album",title=tags.get("title") or track.path.stem,
                year=y or "Unknown Year",year_prefix=(y+" - ") if y else "",date=date or "Unknown Date",
                genre=tags.get("genre") or "Unknown Genre",label=tags.get("label") or "Unknown Label",
                edition=f" [{track.variant}]" if track.variant else "",
                track=number(tags.get("tracknumber"))[0] or position,disc=number(tags.get("discnumber"))[0] or 1,
                codec=(plan.codec if plan else track.profile.codec).upper(),
                samplerate=plan.rate if plan else track.profile.rate,bits=plan.bits if plan else track.profile.bits)


def render_parts(template,values,limit=78):
    # Replace before sanitizing each part, so slashes inside a tag cannot add directories.
    parts=[]
    for part in template.replace("\\","/").split("/"):
        rendered=FORMATTER.vformat(part,(),values)
        parts.append(component(rendered,limit))
    return Path(*parts)


def album_folder(track,settings):
    values=context(track)
    if settings.folder_template==DEFAULT_FOLDER:
        rel=Path("Albums",component(values["albumartist"],50),component(values["year_prefix"]+values["album"]+values["edition"]))
    else:rel=render_parts(settings.folder_template,values)
    if track.variant and "{edition}" not in settings.folder_template:
        rel=rel.with_name(component(rel.name+f" [{track.variant}]"))
    if rel.parts[0].casefold() in {v.casefold() for v in (ARCHIVES,RECORDS,REVIEW,PLAYLISTS)}:
        raise ValueError(tr('资料生成的播放库路径与系统保留目录冲突'))
    if len(str(rel))>360:raise ValueError(tr('模板生成的目录过长，请减少层级或缩短模板'))
    return rel


def track_relative(track,settings,plan,position=1,multidisc=False):
    values=context(track,plan,position)
    name=str(render_parts(settings.filename_template,values,90))
    if multidisc and settings.multidisc=="prefix" and "{disc" not in settings.filename_template:
        name=component(f"{values['disc']:02d}-"+name,90)
    filename=Path(name+plan.ext)
    if multidisc and settings.multidisc=="subfolder":
        return render_parts(settings.disc_template,values)/filename
    return filename


def music_top(settings):
    first=settings.folder_template.replace("\\","/").split("/")[0]
    return first if "{" not in first and "}" not in first else ""
