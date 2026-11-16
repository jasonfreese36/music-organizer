"""Conservative Apple music-library export policies, independent of UI state."""
from i18n import tr
import io
from dataclasses import dataclass,replace
from pathlib import Path

from PIL import Image

from model import Cover,component,reparse,validated_roots


@dataclass(frozen=True)
class DevicePolicy:
    name:str
    encode_codec:str
    codecs:tuple
    rates:tuple=(32000,44100,48000)
    max_bits:int=16
    lossless_rate:int=44100
    artwork_size:int=600


def device_policy(settings):
    if settings.output_profile=="library":return None
    if settings.output_profile=="ios":
        return DevicePolicy("iPhone / iPad","aac",("aac","mp3","alac"),max_bits=24,lossless_rate=48000,artwork_size=1000)
    if settings.ipod_model=="classic_nano":
        return DevicePolicy("iPod classic / nano","aac",("aac","mp3","alac"))
    return DevicePolicy("iPod shuffle" if settings.ipod_model=="shuffle" else tr('iPod 通用兼容'),"mp3",("mp3",))


def device_settings(settings):
    if settings.output_profile=="library":return settings
    kbps=192 if settings.apple_quality=="compact" else 256
    return replace(settings,mp3_mode="cbr",mp3_kbps=kbps,aac_kbps=kbps,
                   id3_version="3" if settings.output_profile=="ipod" else settings.id3_version)


def compatibility_issue(profile,settings,extension=None):
    policy=device_policy(settings)
    if not policy:return ""
    if profile.codec not in policy.codecs:return tr('设备预设不支持此编码')
    if extension and extension.lower()!={"mp3":".mp3","aac":".m4a","alac":".m4a"}[profile.codec]:return tr('设备音频容器不兼容')
    if profile.channels not in (1,2):return tr('设备预设仅支持单声道或立体声')
    allowed=(44100,) if profile.codec=="alac" and settings.output_profile=="ipod" else policy.rates
    if profile.rate not in allowed:return tr('采样率超出设备预设范围')
    if profile.codec=="alac":
        if profile.bits not in (16,24) or profile.bits>policy.max_bits:return tr('ALAC 位深超出设备预设范围')
    else:
        if not 8000<=profile.bitrate<=320000:return tr('有损码率未知或超出 320 kbps 上限')
        if profile.codec=="aac" and profile.codec_profile.upper() not in ("LC","AAC LC","AAC-LC"):
            return tr('AAC 需要转换为兼容的 LC 配置')
    return ""


def source_can_copy(profile,path,settings):
    if compatibility_issue(profile,settings):return False
    if profile.lossless:return settings.apple_quality=="lossless"
    if settings.apple_quality=="compact" and profile.bitrate>192000:return False
    return True


def device_parameters(profile,settings,codec,base_rate):
    policy=device_policy(settings)
    rate=base_rate
    if settings.resample_mode=="fixed":rate=settings.sample_rate
    elif settings.resample_mode=="limit":rate=min(rate,settings.sample_rate)
    allowed=(44100,) if codec=="alac" and settings.output_profile=="ipod" else policy.rates
    if rate not in allowed:
        rate=44100 if 44100 in allowed and profile.rate%44100==0 else max(allowed)
    channels=min(2,max(1,profile.channels)) if settings.channels=="preserve" else 1 if settings.channels=="mono" else 2
    bits=0
    if codec=="alac":
        requested=settings.pcm_bits or (profile.bits if profile.bits in (16,24,32) else policy.max_bits)
        bits=16 if min(requested,policy.max_bits)<=16 else 24
    return rate,channels,bits


def export_locations(source,dest,settings):
    """Reports and optional archives are always outside a device's import folder."""
    if settings.output_profile=="library":return dest,dest
    if dest==dest.parent:raise ValueError(tr('请选择源目录和独立的目标目录'))
    records=(dest.parent/component(dest.name+" - Records",100)).resolve()
    archive=None
    if settings.apple_archive_mode=="separate":
        if not settings.apple_archive_folder.strip():raise ValueError(tr('请选择独立的原盘归档目录'))
        raw=Path(settings.apple_archive_folder).expanduser().absolute()
        if any(p.exists() and reparse(p) for p in (raw,*raw.parents)):raise ValueError(tr('设备导出路径不能经过链接或重解析点'))
        archive=raw.resolve()
        if archive==archive.parent:raise ValueError(tr('原盘归档不能使用磁盘根目录'))
    locations=[source,dest,records]+([archive] if archive else [])
    for i,left in enumerate(locations):
        for right in locations[i+1:]:
            if left.is_relative_to(right) or right.is_relative_to(left):
                raise ValueError(tr('源目录、设备导入目录、报告目录与原盘归档目录必须彼此独立'))
    for folder in locations[1:]:
        if folder.exists() and not folder.is_dir():raise ValueError(tr('设备导出相关路径必须是目录'))
        if any(p.exists() and reparse(p) for p in (folder,*folder.parents)):raise ValueError(tr('设备导出路径不能经过链接或重解析点'))
    return records,archive


def preflight_destination(dest,settings,tools,cancel):
    if settings.output_profile=="library" or not dest.exists():return
    from media import read_audio
    stack=[dest]
    while stack:
        cancel.check()
        for path in stack.pop().iterdir():
            if reparse(path):raise ValueError(tr('设备导入目录中存在链接或重解析点'))
            if path.is_dir():stack.append(path);continue
            if path.suffix.lower() not in (".mp3",".m4a"):
                raise ValueError(tr('目标含非设备音频文件，请为设备预设选择空目录：{0}').format(path.name))
            profile,_,_=read_audio(path,tools,cancel)
            issue=compatibility_issue(profile,settings,path.suffix)
            if issue:raise ValueError(tr('目标含不兼容音频，请为此设备预设选择新目录：{0} · {1}').format(path.name, issue))


def device_artwork(cover,settings):
    policy=device_policy(settings)
    if not cover or not policy:return cover
    with Image.open(io.BytesIO(cover.data)) as original:
        image=original.convert("RGBA")
        image.thumbnail((policy.artwork_size,policy.artwork_size),Image.Resampling.LANCZOS)
        background=Image.new("RGB",image.size,"white");background.paste(image,mask=image.getchannel("A"))
        buffer=io.BytesIO();background.save(buffer,"JPEG",quality=90,optimize=True)
        return Cover(buffer.getvalue(),"image/jpeg",image.width,image.height,cover.source)


def profile_description(settings):
    policy=device_policy(settings)
    if not policy:return tr('常规曲库 · 保留原有整理与原盘备份方式')
    codec="ALAC" if settings.apple_quality=="lossless" else policy.encode_codec.upper()
    details=tr('无损源转 ALAC，有损源保留兼容编码') if settings.apple_quality=="lossless" else "192 kbps" if settings.apple_quality=="compact" else tr('256 kbps；兼容的有损音轨可直接保留')
    return tr('{0} · {1} · {2} · 单声道 / 立体声；报告保存在导入目录之外').format(policy.name, codec, details)
