"""Opt-in DSP controls; only parameters supported by the bundled engines."""
import tkinter as tk

import customtkinter as ctk

from advanced_ui import section
from audio_dsp import DSP_FIELDS
from i18n import tr
from model import Settings
from ui import ACCENT,MUTED,button,label


class DSPPanel:
    def __init__(self,host,panel):
        self.app=panel.app;self.groups={}
        pane=section(host,tr('重采样精调'),tr('这些参数只在音轨需要重新编码时生效。仅调整滤波参数不会让保留原采样率的 FLAC 重新处理；请在“音频转换”中选择采样率策略。'))
        row=ctk.CTkFrame(pane,fg_color="transparent");row.pack(fill="x",padx=22,pady=(0,18))
        for title,key in ((tr('恢复默认'),"default"),("SoXR HQ","hq"),("SoXR VHQ","vhq"),("SoXR 33 bit","33")):
            w=button(row,title,lambda k=key:self.preset(k),width=140)
            w.pack(side="left",padx=(0,10));self.app.setting_widgets.append(w)
        panel.setting(pane,tr('重采样引擎'),"resampler",{"SWResample":"swr","SoXR":"soxr"})
        panel.check(pane,tr('自定义 cutoff 截止比例'),"resample_cutoff_enabled")
        self.groups["cutoff"]=[panel.number(pane,tr('cutoff (%)'),"resample_cutoff",
            tr('80–99.7；开启自定义后的初始值为 98%。SWR 为 −6 dB 截止点，SoXR 为 0 dB 通带点；关闭时沿用引擎默认。'))]
        pane=section(host,tr('SoXR 精度'),tr('HQ 为 20 bit，VHQ 为 28 bit；也可选 15–33 bit。这里是计算精度，输出文件位深在“音频转换”中设置。'))
        self.groups["soxr"]=[
            panel.number(pane,tr('计算精度 (bit)'),"soxr_precision",tr('15–33；更高精度通常需要更多处理时间。')),
            panel.check(pane,tr('Chebyshev：平坦通带与高精度无理数比率近似'),"soxr_cheby")]
        pane=section(host,tr('SWR 滤波器'),tr('Kaiser 与 Blackman–Nuttall 使用加窗 sinc；Cubic 提供速度优先的三次插值。以下参数只作用于 SWR。相位表精度不是最小相位 / 线性相位切换。'))
        self.groups["swr"]=[
            panel.setting(pane,tr('滤波算法'),"swr_filter_type",{"Kaiser windowed sinc":"kaiser","Blackman–Nuttall windowed sinc":"blackman_nuttall","Cubic":"cubic"}),
            panel.number(pane,tr('滤波长度'),"swr_filter_size",tr('4–256；默认 32。更长的滤波器通常更慢。')),
            panel.number(pane,tr('相位表精度'),"swr_phase_shift",tr('0–16；默认 10。提高此值会增加内存占用。')),
            panel.check(pane,tr('优先使用精确有理数采样比'),"swr_exact_rational")]
        self.groups["kaiser"]=[panel.number(pane,tr('Kaiser β'),"swr_kaiser_beta",tr('2–16；默认 9，仅 Kaiser 滤波使用。'))]
        pane=section(host,tr('量化与电平'),tr('不自动归一化响度。降低位深、重采样或处理整数 PCM 时，抖动位于最后的整数输出阶段。保留 MP3/AAC 编码时，电平调整不生效。'))
        panel.setting(pane,tr('抖动 / 噪声整形'),"dither",{
            tr('关闭'):"none",tr('矩形抖动'):"rectangular",tr('三角抖动'):"triangular",tr('高通三角抖动'):"triangular_hp",
            "Shibata":"shibata","Low Shibata":"low_shibata","High Shibata":"high_shibata","Lipshitz":"lipshitz",
            "F-weighted":"f_weighted","Modified E-weighted":"modified_e_weighted","Improved E-weighted":"improved_e_weighted"},
            tr('噪声整形取决于目标采样率；不支持的组合会报错，不会静默替换。三角抖动可用于任意采样率。'))
        panel.number(pane,tr('抖动幅度'),"dither_scale",tr('0–4；默认 1，0 表示不添加抖动噪声。'))
        panel.number(pane,tr('输出增益 / 预留余量 (dB)'),"gain_db",tr('−24 至 +6；默认 0。负值预留余量，正值可能导致削波；不会自动限幅。'))
        panel.check(pane,tr('多声道混缩时归一化混音矩阵，预留峰值余量'),"downmix_normalize")
        pane=section(host,tr('DSD → PCM 高级处理'),tr('启用后，DSF / DFF 与 SACD ISO 使用同一条 FFmpeg DSD 解码及后处理链路；ISO 先提取 DSD。解码器本身使用固定 FIR，以下低通、去直流和增益作用于解码后的 PCM，随后重采样、量化。'))
        panel.check(pane,tr('启用 DSD 高级处理'),"dsd_advanced")
        self.groups["dsd"]=[
            panel.setting(pane,tr('DSD 的 PCM 输出位深'),"dsd_pcm_bits",{"16 bit":16,"24 bit":24,"32 bit":32},tr('用于 FLAC / ALAC；苹果设备限制仍优先生效。')),
            panel.number(pane,tr('DSD 独立增益 (dB)'),"dsd_gain_db",tr('−24 至 +12；与输出增益相加。默认 0，不自动补偿 6 dB。')),
            panel.number(pane,tr('DSD 超声低通截止 (Hz)'),"dsd_lowpass_hz",tr('0 为关闭；否则 20000–100000，默认 30000。滤波在最终降采样之前进行。')),
            panel.setting(pane,tr('低通阶数'),"dsd_lowpass_order",{tr('2 阶 · 12 dB/oct'):2,tr('4 阶 · 24 dB/oct'):4,tr('6 阶 · 36 dB/oct'):6,tr('8 阶 · 48 dB/oct'):8},tr('双精度 Butterworth IIR；更高阶滚降更陡，也会改变相位响应。')),
            panel.check(pane,tr('去除直流：5 Hz 二阶高通'),"dsd_remove_dc")]
        self.summary=tk.StringVar()
        label(pane,variable=self.summary,size=11,color=ACCENT,wraplength=850,justify="left").pack(anchor="w",padx=22,pady=(0,20))
        for name in ("resampler","swr_filter_type","resample_cutoff_enabled","dsd_advanced","dsd_lowpass_hz"):
            self.app.advanced_values[name].trace_add("write",self.refresh)
        self.refresh()

    def refresh(self,*_):
        values=self.app.advanced_values
        active={"cutoff":values["resample_cutoff_enabled"].get(),"soxr":values["resampler"].get()=="soxr",
                "swr":values["resampler"].get()=="swr","kaiser":values["resampler"].get()=="swr" and values["swr_filter_type"].get()=="kaiser",
                "dsd":values["dsd_advanced"].get()}
        for group,widgets in self.groups.items():
            for widget in widgets:widget.configure(state="normal" if active[group] and not self.app.busy else "disabled")
        self.summary.set(tr('高级处理已启用；源文件与原盘归档策略保持原样。') if active["dsd"] else tr('高级处理未启用，沿用原有 DSD 转换行为。'))

    def preset(self,key):
        values=self.app.advanced_values;defaults=Settings()
        if key=="default":
            for name in DSP_FIELDS:values[name].set(getattr(defaults,name))
            values["resampler"].set(defaults.resampler);values["dither"].set(defaults.dither)
        else:
            values["resampler"].set("soxr")
            values["soxr_precision"].set({"hq":20,"vhq":28,"33":33}[key])
            values["soxr_cheby"].set(False)
        self.refresh()
