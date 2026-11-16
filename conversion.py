"""Resolve one deterministic audio plan, used by rules, preview, encoding and resume."""
from i18n import tr
from dataclasses import dataclass

from rules import effective_settings
from apple import device_policy,device_settings,source_can_copy,device_parameters


def resolved_settings(track,settings):
    selected,rule=effective_settings(track,settings)
    return device_settings(selected),rule


@dataclass(frozen=True)
class AudioPlan:
    codec:str
    ext:str
    rate:int
    channels:int
    bits:int
    mode:str
    pcm_unchanged:bool
    signature:dict
    rule:str=""
    notes:tuple=()

    @property
    def description(self):
        audio=f"{self.codec.upper()} · {self.rate/1000:g} kHz · {self.channels} ch"
        if self.bits:audio+=f" · {self.bits} bit"
        mode={"copy":tr('保留音频编码'),"remux":tr('无损重新封装'),"encode":tr('重新编码')}[self.mode]
        return audio+" · "+mode+(" · "+"；".join(self.notes) if self.notes else "")


def plan_audio(track,settings):
    s,rule=resolved_settings(track,settings)
    p=track.profile;dsd=p.codec.startswith("dsd")
    codec=s.lossless_format if p.lossless else (p.codec if s.lossy_format=="preserve" and p.codec in ("aac","mp3") else "aac" if s.lossy_format=="preserve" else s.lossy_format)
    policy=device_policy(s)
    if policy:
        codec=("alac" if s.apple_quality=="lossless" else policy.encode_codec) if p.lossless else p.codec if source_can_copy(p,track.path,s) else policy.encode_codec
    ext={"flac":".flac","mp3":".mp3","aac":".m4a","alac":".m4a"}[codec]
    # Existing AAC/MP3 is bit-preserved until a different format or re-encode is selected.
    preserve=not p.lossless and p.codec==codec and not s.reencode_lossy
    if policy:preserve=not p.lossless and p.codec==codec and source_can_copy(p,track.path,s) and not s.reencode_lossy
    notes=[]
    rate=s.sacd_rate if dsd else p.rate
    channels=p.channels
    if not preserve:
        if s.resample_mode=="fixed":rate=s.sample_rate
        elif s.resample_mode=="limit":rate=min(rate,s.sample_rate)
        if s.channels!="preserve":channels=2 if s.channels=="stereo" else 1
        maximum=48000 if codec=="mp3" else 96000 if codec=="aac" else 655350
        if rate>maximum:
            rate=44100 if p.rate%44100==0 else 48000 if codec=="mp3" else 88200 if p.rate%44100==0 else 96000
            notes.append(tr('已适配编码器支持的采样率'))
        if codec=="mp3" and channels>2:
            channels=2;notes.append(tr('MP3 自动混缩为立体声'))
    elif s.resample_mode!="preserve" or s.channels!="preserve":
        notes.append(tr('保留现有有损编码，未重采样；可启用重新编码'))
    bits=(s.pcm_bits or (24 if dsd else p.bits if p.bits in (16,24,32) else 32)) if codec=="flac" else 0
    if policy:
        if preserve:rate,channels,bits=p.rate,p.channels,0
        else:rate,channels,bits=device_parameters(p,s,codec,s.sacd_rate if dsd else p.rate)
        notes.append(tr('已应用设备兼容格式、采样率、码率及声道限制'))
    unchanged=not dsd and rate==p.rate and channels==p.channels and (codec not in ("flac","alac") or bits>=p.bits and not p.codec.startswith("pcm_f"))
    if preserve:mode="copy" if track.path.suffix.casefold()==ext else "remux"
    elif codec=="flac" and p.codec=="flac" and track.path.suffix.casefold()==ext and rate==p.rate and channels==p.channels and bits==p.bits and not s.recompress_flac:mode="copy"
    elif codec=="alac" and p.codec=="alac" and track.path.suffix.casefold()==ext and rate==p.rate and channels==p.channels and bits==p.bits:mode="copy"
    else:mode="encode"
    signature=dict(codec=codec,rate=rate,channels=channels,bits=bits)
    if policy:signature.update(output_profile=s.output_profile,ipod_model=s.ipod_model if s.output_profile=="ipod" else "",apple_quality=s.apple_quality)
    if mode=="encode":
        signature.update(resampler=s.resampler,dither=s.dither)
        if codec=="flac":signature["compression"]=s.flac_compression
        elif codec=="mp3":signature.update(mp3_mode=s.mp3_mode,quality=s.mp3_vbr if s.mp3_mode=="vbr" else s.mp3_kbps)
        elif codec=="aac":signature["aac_kbps"]=s.aac_kbps*max(1,channels//2)
    if not p.lossless and codec!=p.codec:notes.append(tr('有损来源再次编码'))
    return AudioPlan(codec,ext,rate,channels,bits,mode,unchanged,signature,rule,tuple(notes))


def encoding_args(track,settings,plan):
    s,_=resolved_settings(track,settings)
    if plan.mode=="remux":return ["-c:a","copy"]
    args=[]
    p=track.profile
    if plan.codec in ("flac","alac"):
        filt=f"aresample={plan.rate}:resampler={s.resampler}"
        if s.resampler=="soxr":filt+=":precision=28"
        if plan.bits<p.bits or p.codec.startswith(("pcm_f","dsd")):
            fmt="s16" if plan.bits==16 else "s32"
            filt+=f":osf={fmt}:output_sample_bits={plan.bits}:dither_method={s.dither}"
        args += ["-af",filt,"-c:a",plan.codec]
        if plan.codec=="flac":args += ["-compression_level",str(s.flac_compression)]
        args += ["-sample_fmt",("s16p" if plan.bits==16 else "s32p") if plan.codec=="alac" else "s16" if plan.bits==16 else "s32","-bits_per_raw_sample",str(plan.bits)]
        if plan.bits==32 and plan.codec=="flac":args += ["-strict","experimental"]
    else:
        filt=f"aresample={plan.rate}:resampler={s.resampler}"
        if s.resampler=="soxr":filt+=":precision=28"
        args += ["-af",filt]
        if plan.codec=="mp3":
            args += ["-c:a","libmp3lame"]
            args += ["-q:a",str(s.mp3_vbr)] if s.mp3_mode=="vbr" else ["-b:a",f"{s.mp3_kbps}k"]
        else:args += ["-c:a","aac","-b:a",f"{s.aac_kbps*max(1,plan.channels//2)}k"]+(["-profile:a","aac_low"] if s.output_profile!="library" else [])
    return [*args,"-ar",str(plan.rate),"-ac",str(plan.channels)]


def needs_render(track,entry,settings):
    plan=plan_audio(track,settings);p=entry["profile"]
    if p.codec!=plan.codec or entry["path"].suffix.casefold()!=plan.ext or p.rate!=plan.rate or p.channels!=plan.channels or plan.bits and p.bits!=plan.bits:return True
    recorded=entry.get("record",{}).get("transform",{})
    if plan.mode!="encode":return bool(recorded.get("codec") and recorded!=plan.signature)
    s,_=effective_settings(track,settings)
    if plan.codec=="flac" and plan.pcm_unchanged and not s.recompress_flac:return False
    if recorded==plan.signature:return False
    # Resume libraries produced by 1.1 with the same legacy DSD / lossy settings.
    legacy=dict(sacd_rate=s.sacd_rate,aac_kbps=s.aac_kbps)
    if recorded==legacy and s.lossless_format=="flac" and s.lossy_format=="preserve" and s.resample_mode=="preserve" and not s.pcm_bits and s.channels=="preserve" and not s.reencode_lossy and not s.recompress_flac:return False
    return True
