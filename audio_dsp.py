"""Actual FFmpeg DSP options, shared by planning, encoding and device limits."""
import math
from functools import lru_cache

from i18n import tr
from model import Settings


DSP_FIELDS = (
    "resample_cutoff_enabled","resample_cutoff","soxr_precision","soxr_cheby",
    "swr_filter_type","swr_filter_size","swr_phase_shift","swr_kaiser_beta","swr_exact_rational",
    "dither_scale","gain_db","downmix_normalize","dsd_advanced","dsd_pcm_bits",
    "dsd_gain_db","dsd_lowpass_hz","dsd_lowpass_order","dsd_remove_dc",
)


def target_rate(rate,settings):
    if settings.resample_mode=="fixed":return settings.sample_rate
    if settings.resample_mode=="limit":return min(rate,settings.sample_rate)
    if settings.resample_mode=="family":
        ceiling=min(rate,settings.sample_rate)
        rates=(11025,22050,44100,88200,176400,352800) if rate%11025==0 else (8000,16000,32000,48000,96000,192000,384000) if rate%8000==0 else ()
        return max((r for r in rates if r<=ceiling),default=ceiling)
    return rate


def waveform_processing(profile,settings,channels):
    return bool(settings.gain_db or settings.downmix_normalize and channels<profile.channels
                or profile.codec.startswith("dsd") and settings.dsd_advanced)


def dsd_cutoff(profile,settings):
    return min(settings.dsd_lowpass_hz,int(profile.rate*.49))


@lru_cache(maxsize=1)
def defaults():
    return Settings()


def processing_signature(profile,settings,channels):
    baseline=defaults()
    fields=["resample_cutoff_enabled"]
    if settings.resample_cutoff_enabled:fields.append("resample_cutoff")
    fields+=["soxr_precision","soxr_cheby"] if settings.resampler=="soxr" else [
        "swr_filter_type","swr_filter_size","swr_phase_shift","swr_kaiser_beta","swr_exact_rational"]
    fields+=["dither_scale","gain_db"]
    if channels<profile.channels:fields.append("downmix_normalize")
    if profile.codec.startswith("dsd") and settings.dsd_advanced:
        # Record every active DSD setting, including the defaults of the new path.
        return {**{k:getattr(settings,k) for k in fields if getattr(settings,k)!=getattr(baseline,k)},
                **{k:getattr(settings,k) for k in DSP_FIELDS if k.startswith("dsd_")}}
    return {k:getattr(settings,k) for k in fields if getattr(settings,k)!=getattr(baseline,k)}


def validate_dither(settings,rate):
    """Match the shaping tables in the pinned libswresample; no silent fallback."""
    tables={
        "shibata":(48000,44100,37800,32000,22050,16000,11025,8000),
        "low_shibata":(48000,44100),"high_shibata":(44100,),"lipshitz":(44100,),
        "f_weighted":(46000,),"modified_e_weighted":(46000,),"improved_e_weighted":(46000,),
    }
    supported=tables.get(settings.dither)
    if settings.dither_scale and supported and not any(abs(rate-r)*20<=r for r in supported):
        raise ValueError(tr('{0} 噪声整形不支持 {1} Hz；请选择三角抖动或更改目标采样率').format(settings.dither,rate))


def filter_chain(profile,settings,plan):
    """Double precision DSP precedes final rate conversion and quantization."""
    filters=[]
    dsd=profile.codec.startswith("dsd") and settings.dsd_advanced
    if dsd:
        if settings.dsd_remove_dc:
            filters.append("highpass=f=5:p=2:precision=f64")
        if settings.dsd_lowpass_hz:
            cutoff=dsd_cutoff(profile,settings)
            order=settings.dsd_lowpass_order
            for stage in range(order//2):
                q=1/(2*math.cos((2*stage+1)*math.pi/(2*order)))
                filters.append(f"lowpass=f={cutoff:g}:p=2:t=q:w={q:.12g}:precision=f64")
    gain=settings.gain_db+(settings.dsd_gain_db if dsd else 0)
    if gain:filters.append(f"volume={gain:g}dB:precision=double")
    resample=f"aresample={plan.rate}:resampler={settings.resampler}"
    if settings.resampler=="soxr":
        resample+=f":precision={settings.soxr_precision}:cheby={int(settings.soxr_cheby)}"
    else:
        resample+=(f":filter_type={settings.swr_filter_type}:filter_size={settings.swr_filter_size}"
                   f":phase_shift={settings.swr_phase_shift}:kaiser_beta={settings.swr_kaiser_beta:g}"
                   f":exact_rational={int(settings.swr_exact_rational)}")
    if settings.resample_cutoff_enabled:resample+=f":cutoff={settings.resample_cutoff/100:.8g}"
    if plan.channels!=profile.channels:
        resample+=":ochl="+("mono" if plan.channels==1 else "stereo")
        if settings.downmix_normalize:resample+=":rematrix_maxval=1"
    if plan.codec in ("flac","alac") and (plan.bits<profile.bits or not plan.pcm_unchanged):
        fmt="s16" if plan.bits==16 else "s32"
        resample+=f":osf={fmt}:output_sample_bits={plan.bits}:dither_method={settings.dither}:dither_scale={settings.dither_scale:g}"
    filters.append(resample)
    return ",".join(filters)
