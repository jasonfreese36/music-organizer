"""Optional device exports; the default remains the regular library workflow."""
from i18n import tr
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from advanced_ui import Choice,section
from apple import export_locations,profile_description
from ui import ACCENT,FONT,INK,LINE,MUTED,WHITE,button,label


class ApplePanel:
    def __init__(self,host,panel):
        self.app=panel.app
        pane=section(host,tr('苹果设备输出'),tr('先选择输出预设，再选择独立的目标目录。默认仍使用常规曲库设置。设备预设会优先应用兼容限制，条件规则无法输出不受支持的格式。'))
        panel.setting(pane,tr('输出预设'),"output_profile",{tr('常规曲库'):"library","iPod":"ipod","iPhone / iPad":"ios"})
        self.model=panel.setting(pane,tr('iPod 机型'),"ipod_model",{tr('通用兼容 · MP3'):"universal","classic / nano · AAC / ALAC":"classic_nano","shuffle · MP3":"shuffle"},tr('不确定机型时请选择通用兼容。classic / nano 为保守的 16-bit / 44.1 kHz ALAC 预设；具体支持范围仍以机型规格为准。'))
        self.quality=panel.setting(pane,tr('设备音质'),"apple_quality",{tr('标准 · 256 kbps'):"standard",tr('节省空间 · 192 kbps'):"compact",tr('保留无损 · ALAC'):"lossless"},tr('无损源按选择转换。有损源兼容时保留原编码，超出设备范围时才重新编码；节省空间会降低高于 192 kbps 的有损码率。'))
        self.summary=tk.StringVar()
        label(pane,variable=self.summary,size=12,color=ACCENT,wraplength=830,justify="left").pack(anchor="w",padx=22,pady=(0,20))
        pane=section(host,tr('原盘独立归档'),tr('原盘归档可包含 DSD / SACD ISO、CUE 整轨、平台加密文件及普通音频原件。归档与设备导入目录分开；源目录中的文件始终保留。'))
        self.archive=panel.setting(pane,tr('原盘处理'),"apple_archive_mode",{tr('不另存原盘'):"none",tr('另存到独立文件夹'):"separate"})
        row=ctk.CTkFrame(pane,fg_color="transparent");row.pack(fill="x",padx=22,pady=(0,16))
        self.path=ctk.CTkEntry(row,textvariable=self.app.advanced_values["apple_archive_folder"],height=36,fg_color=WHITE,text_color=INK,border_color=LINE,font=(FONT,12))
        self.path.pack(side="left",fill="x",expand=True,padx=(0,10))
        self.browse=button(row,tr('选择归档目录'),self.choose_archive,width=140);self.browse.pack(side="right")
        self.app.setting_widgets.extend((self.path,self.browse))
        self.locations=tk.StringVar()
        label(pane,variable=self.locations,size=11,color=MUTED,wraplength=830,justify="left").pack(anchor="w",padx=22,pady=(0,20))
        pane=section(host,tr('导入与同步'),tr('设备导入目录只包含兼容的 MP3 / M4A 音轨，封面内嵌为 JPEG。报告、索引和播放列表放在目标旁的独立 Records 文件夹。'))
        label(pane,tr('将整理后的 Albums 文件夹导入 Apple Music 或 iTunes，再通过 Apple Devices / iTunes 同步到设备。本程序不直接写入 iPod 数据库。WAV / FLAC / DSD 等会转换；不会把原盘放进设备目录。'),size=12,color=MUTED,wraplength=830,justify="left").pack(anchor="w",padx=22,pady=(0,20))
        for key in ("output_profile","ipod_model","apple_quality","apple_archive_mode","apple_archive_folder"):
            self.app.advanced_values[key].trace_add("write",self.refresh)
        self.app.source.trace_add("write",self.refresh);self.app.dest.trace_add("write",self.refresh)
        self.refresh()

    def choose_archive(self):
        path=filedialog.askdirectory(parent=self.app,title=tr('选择独立的原盘归档目录'),mustexist=False,initialdir=self.app.advanced_values["apple_archive_folder"].get() or None)
        if path:self.app.advanced_values["apple_archive_folder"].set(path)

    def refresh(self,*_):
        values=self.app.advanced_values
        ipod=values["output_profile"].get()=="ipod"
        device=values["output_profile"].get()!="library"
        limited=ipod and values["ipod_model"].get()!="classic_nano"
        if limited and values["apple_quality"].get()=="lossless":values["apple_quality"].set("standard")
        qualities={tr('标准 · 256 kbps'):"standard",tr('节省空间 · 192 kbps'):"compact"}
        if not limited:qualities[tr('保留无损 · ALAC')]="lossless"
        self.quality.choices=qualities;self.quality.configure(values=list(qualities));self.quality._sync()
        busy=self.app.busy
        for widget,active in ((self.model,ipod),(self.quality,device),(self.archive,device),(self.path,device and values["apple_archive_mode"].get()=="separate"),(self.browse,device and values["apple_archive_mode"].get()=="separate")):
            widget.configure(state="normal" if active and not busy else "disabled")
        try:
            settings=self.app._settings_value();self.summary.set(profile_description(settings))
            if device and self.app.source.get() and self.app.dest.get():
                from pathlib import Path
                records,archive=export_locations(Path(self.app.source.get()).resolve(),Path(self.app.dest.get()).resolve(),settings)
                self.locations.set(tr('报告目录：')+str(records)+"\n"+(tr('原盘归档：')+str(archive) if archive else tr('不另存原盘；源文件保留。')))
            else:self.locations.set(tr('原盘目录、报告目录与设备导入目录必须彼此独立。'))
        except (ValueError,tk.TclError) as exc:self.locations.set(str(exc))
