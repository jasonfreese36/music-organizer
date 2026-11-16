"""Opt-in advanced preferences. Defaults preserve the 1.1 workflow."""
import io
import json
import tkinter as tk
from dataclasses import asdict,replace
from pathlib import Path
from tkinter import filedialog,messagebox

import customtkinter as ctk

from conversion import plan_audio
from inventory import infer_track
from model import Settings,VERSION,csv_bytes,write_atomic
from naming import album_folder,track_relative
from theme import ACCENTS,BASES,MODES,color,resolved
from ui import ACCENT,BG,FONT,HOVER,INK,LINE,MUTED,TINT,WHITE,button,card,label,tree

RATES={str(n):n for n in (8000,16000,22050,24000,32000,44100,48000,88200,96000,176400,192000,352800,384000)}
FOLDER_PRESETS={"艺术家 / 年份 - 专辑":"Albums/{albumartist}/{year_prefix}{album}{edition}",
                "艺术家 / 专辑":"Albums/{albumartist}/{album}{edition}",
                "风格 / 艺术家 / 专辑":"Albums/{genre}/{albumartist}/{year_prefix}{album}{edition}",
                "年份 / 艺术家 / 专辑":"Albums/{year}/{albumartist}/{album}{edition}",
                "专辑 - 艺术家":"Albums/{album} - {albumartist}{edition}"}
FILE_PRESETS={"轨号在前":"{track:02d} - {title}","歌名在前":"{title} - {track:02d}",
              "歌名 - 艺术家":"{title} - {artist}","艺术家 - 歌名":"{artist} - {title}",
              "轨号 - 艺术家 - 歌名":"{track:02d} - {artist} - {title}","仅歌名":"{title}"}


class Choice(ctk.CTkOptionMenu):
    def __init__(self,master,variable,choices,width=190,command=None):
        self.raw,self.choices=variable,dict(choices)
        self.view=tk.StringVar(master)
        self.extra_command=command
        self._sync()
        super().__init__(master,variable=self.view,values=list(self.choices),command=self._choose,width=width,height=35,
                         fg_color=color("#F2F0FA"),button_color=color("#E9E5F7"),button_hover_color=color("#DED7F3"),
                         text_color=INK,dropdown_fg_color=WHITE,dropdown_text_color=INK,dropdown_hover_color=TINT,font=(FONT,12),dropdown_font=(FONT,12),corner_radius=8)
        self._trace=self.raw.trace_add("write",lambda *a:self._sync())

    def _sync(self):
        value=self.raw.get()
        self.view.set(next((k for k,v in self.choices.items() if v==value or str(v)==str(value)),str(value)))

    def _choose(self,value):
        selected=self.choices[value]
        self.raw.set(str(selected) if isinstance(self.raw,tk.StringVar) else selected)
        if self.extra_command:self.extra_command()

    def destroy(self):
        try:self.raw.trace_remove("write",self._trace)
        except (tk.TclError,AttributeError):pass
        super().destroy()


def section(master,title,description=None):
    frame=card(master)
    frame.pack(fill="x",pady=(0,14))
    label(frame,title,size=16,bold=True).pack(anchor="w",padx=22,pady=(19,5 if description else 16))
    if description:label(frame,description,size=12,color=MUTED,wraplength=880,justify="left").pack(anchor="w",padx=22,pady=(0,15))
    return frame


class AdvancedPanel(ctk.CTkFrame):
    def __init__(self,master,app,help_text):
        super().__init__(master,fg_color="transparent")
        self.app=app
        self._preview_job=None
        self.tabs=ctk.CTkTabview(self,fg_color="transparent",corner_radius=12,
                               segmented_button_fg_color=color("#F2F0FA"),segmented_button_selected_color=TINT,
                               segmented_button_selected_hover_color=color("#E2DAF6"),segmented_button_unselected_color=color("#F8F7FC"),
                               segmented_button_unselected_hover_color=color("#E8E3F7"),text_color=INK,segmented_button_font=(FONT,13))
        self.tabs.pack(fill="both",expand=True)
        self.scrollers={}
        for name in ("外观","目录与命名","音频转换","条件规则","平台音频","配置与工具"):
            tab=self.tabs.add(name)
            if name=="条件规则":continue
            scroll=ctk.CTkScrollableFrame(tab,fg_color="transparent",corner_radius=0)
            scroll.pack(fill="both",expand=True)
            self.scrollers[name]=scroll
        self.build_appearance();self.build_naming();self.build_audio();self.build_tools(help_text)
        from rule_ui import RuleManager
        self.rules=RuleManager(self.tabs.tab("条件规则"),app)
        self.rules.pack(fill="both",expand=True)
        from platform_ui import PlatformPanel
        self.platform_panel=PlatformPanel(self.scrollers["平台音频"],self)
        self.tabs.set("外观")
        for variable in self.app.advanced_values.values():variable.trace_add("write",lambda *a:self.queue_preview())
        self.queue_preview()

    def build_appearance(self):
        host=self.scrollers["外观"]
        pane=section(host,"为你的曲库选择外观","默认沿用 v1.1 的浅色紫色主题。外观即时生效，音频与整理规则不会改变。")
        row=ctk.CTkFrame(pane,fg_color="transparent");row.pack(fill="x",padx=22,pady=(0,22))
        label(row,"颜色模式",size=13).pack(side="left",padx=(0,24))
        Choice(row,self.app.appearance,{k:v for k,v in MODES.items()},width=210).pack(side="left")
        palette=section(host,"主题色","主题色与浅色、深色模式可以自由搭配。")
        row=ctk.CTkFrame(palette,fg_color="transparent");row.pack(fill="x",padx=22,pady=(0,22))
        for name,key in ACCENTS.items():
            swatch=ctk.CTkFrame(row,fg_color="transparent");swatch.pack(side="left",padx=(0,18))
            sample=ctk.CTkButton(swatch,text="",width=82,height=45,corner_radius=12,fg_color=BASES[key],hover_color=BASES[key],
                          command=lambda k=key:self.app.accent.set(k))
            sample._fixed_accent=True;sample.pack()
            label(swatch,name,size=12,color=MUTED).pack(pady=(8,0))
        self.theme_caption=tk.StringVar()
        label(palette,variable=self.theme_caption,size=12,color=ACCENT).pack(anchor="w",padx=22,pady=(0,20))
        self.app.accent.trace_add("write",lambda *a:self.theme_caption.set("当前主题色："+next((k for k,v in ACCENTS.items() if v==self.app.accent.get()),"鸢尾紫")))
        self.theme_caption.set("当前主题色："+next((k for k,v in ACCENTS.items() if v==self.app.accent.get()),"鸢尾紫"))

    def setting(self,pane,title,key,choices,description=None):
        row=ctk.CTkFrame(pane,fg_color="transparent");row.pack(fill="x",padx=22,pady=(0,14))
        text=ctk.CTkFrame(row,fg_color="transparent");text.pack(side="left",fill="x",expand=True,padx=(0,20))
        label(text,title,size=13).pack(anchor="w")
        if description:label(text,description,size=11,color=MUTED,wraplength=590,justify="left").pack(anchor="w",pady=(3,0))
        widget=Choice(row,self.app.advanced_values[key],choices,width=220)
        widget.pack(side="right");self.app.setting_widgets.append(widget)
        return widget

    def check(self,pane,title,key):
        widget=ctk.CTkCheckBox(pane,text=title,variable=self.app.advanced_values[key],fg_color=ACCENT,hover_color=HOVER,
                              text_color=INK,checkbox_width=18,checkbox_height=18,font=(FONT,12),border_color=LINE)
        widget.pack(anchor="w",padx=22,pady=(0,16));self.app.setting_widgets.append(widget)

    def build_naming(self):
        host=self.scrollers["目录与命名"]
        pane=section(host,"用预设开始，再按习惯组合","命名只影响目标库。可以点选预设、插入字段或调整字段顺序；斜杠 / 表示一层文件夹。")
        self.naming_entries={}
        self.insert_target=tk.StringVar(value="filename_template")
        for title,key,presets in (("专辑文件夹","folder_template",FOLDER_PRESETS),("音轨文件名","filename_template",FILE_PRESETS)):
            row=ctk.CTkFrame(pane,fg_color="transparent");row.pack(fill="x",padx=22,pady=(0,8))
            label(row,title,size=13,bold=True).pack(side="left")
            chosen=tk.StringVar(value="选择预设…")
            menu=ctk.CTkOptionMenu(row,variable=chosen,values=list(presets),width=240,height=31,fg_color=TINT,
                                  text_color=INK,button_color=TINT,button_hover_color=TINT,font=(FONT,12),
                                  dropdown_fg_color=WHITE,dropdown_text_color=INK,
                                  command=lambda value,k=key,p=presets:self.app.advanced_values[k].set(p[value]))
            menu.pack(side="right");self.app.setting_widgets.append(menu)
            entry=ctk.CTkEntry(pane,textvariable=self.app.advanced_values[key],height=38,corner_radius=8,
                               fg_color=color("#F7F6FB"),border_color=LINE,text_color=INK,font=("Consolas",13))
            entry.pack(fill="x",padx=22,pady=(0,17))
            self.naming_entries[key]=entry;self.app.setting_widgets.append(entry)
        chips=ctk.CTkFrame(pane,fg_color="transparent");chips.pack(fill="x",padx=22,pady=(0,10))
        label(chips,"插入到",size=12,color=MUTED).pack(side="left",padx=(0,10))
        Choice(chips,self.insert_target,{"音轨文件名":"filename_template","专辑文件夹":"folder_template"},width=170).pack(side="left")
        chipbox=ctk.CTkFrame(pane,fg_color="transparent");chipbox.pack(fill="x",padx=22,pady=(0,20))
        fields=[("曲名","title"),("艺术家","artist"),("专辑艺术家","albumartist"),("专辑","album"),("年份","year"),("风格","genre"),
                ("轨号 01","track:02d"),("碟号 01","disc:02d"),("发行版本","edition"),("格式","codec"),("采样率","samplerate"),("位深","bits")]
        for i,(title,token) in enumerate(fields):
            w=button(chipbox,title,lambda t=token:self.insert_field(t),width=115)
            w.grid(row=i//6,column=i%6,padx=(0,8),pady=(0,7),sticky="ew");self.app.setting_widgets.append(w)
        pane=section(host,"多碟专辑")
        self.setting(pane,"多碟组织方式","multidisc",{"单独的碟目录":"subfolder","碟号放在文件名前":"prefix","所有音轨放在专辑目录":"flat"})
        row=ctk.CTkFrame(pane,fg_color="transparent");row.pack(fill="x",padx=22,pady=(0,20))
        label(row,"碟目录命名",size=13).pack(side="left")
        entry=ctk.CTkEntry(row,textvariable=self.app.advanced_values["disc_template"],width=220,height=35,text_color=INK,fg_color=color("#F7F6FB"),border_color=LINE)
        entry.pack(side="right");self.app.setting_widgets.append(entry)
        pane=section(host,"目标路径预览","以当前选中的音轨预览；未选择时使用示例资料。在线匹配、解密或分轨后的最终资料可能有所不同。")
        self.naming_preview=tk.StringVar(value="")
        self.naming_validation=tk.StringVar(value="")
        label(pane,variable=self.naming_preview,size=13,color=ACCENT,wraplength=850,justify="left").pack(anchor="w",padx=22,pady=(0,10))
        label(pane,variable=self.naming_validation,size=11,color=MUTED,wraplength=850,justify="left").pack(anchor="w",padx=22,pady=(0,15))
        w=button(pane,"预览已扫描曲库的规则与路径",self.app._preview_plan,width=240)
        w.pack(anchor="w",padx=22,pady=(0,20));self.app.setting_widgets.append(w)

    def insert_field(self,token):
        key=self.insert_target.get()
        if key=="folder_template" and token.split(":")[0] in ("title","track","disc","codec","samplerate","bits"):
            self.naming_validation.set("此字段适用于音轨文件名，请将“插入到”切换为音轨文件名。");return
        entry=self.naming_entries[key]
        entry.insert(tk.INSERT,"{"+token+"}");entry.focus_set()

    def queue_preview(self):
        if self._preview_job:self.after_cancel(self._preview_job)
        self._preview_job=self.after(150,self.refresh_preview)

    def refresh_preview(self):
        self._preview_job=None
        try:
            settings=self.app._settings_value()
            _,item=self.app._selected()
            if item is not None and item.profile and not item.error:
                track=infer_track(item);track.tags=self.app.effective_tags(item)
            else:
                from model import Item,Profile,Track
                dummy=Item(Path("Sample.flac"),Path("Sample.flac"),0,0,"audio")
                track=Track(dummy,dummy.path,Profile("flac",96000,2,24,240,bitrate=1800000),
                            dict(title="Sample Song",artist="Artist",albumartist="Artist",album="Sample Album",date="2024",tracknumber="3/12",discnumber="1/2",genre="Jazz"))
            plan=plan_audio(track,settings)
            rel=album_folder(track,settings)/track_relative(track,settings,plan,multidisc=True)
            self.naming_preview.set(str(rel))
            self.naming_validation.set(("规则："+plan.rule+" · " if plan.rule else "默认设置 · ")+plan.description)
        except Exception as exc:
            self.naming_preview.set("请调整命名或转换参数")
            self.naming_validation.set(str(exc))

    def build_audio(self):
        host=self.scrollers["音频转换"]
        pane=section(host,"默认转换策略","未命中条件规则时采用这些设置。默认与 v1.1 相同：无损转 FLAC，保留现有 MP3/AAC，其他有损转 AAC。")
        row=ctk.CTkFrame(pane,fg_color="transparent");row.pack(fill="x",padx=22,pady=(0,18))
        for name,key in (("保真默认","faithful"),("MP3 便携","mp3"),("AAC 便携","aac")):
            w=button(row,name,lambda k=key:self.audio_preset(k),width=125);w.pack(side="left",padx=(0,10));self.app.setting_widgets.append(w)
        self.setting(pane,"无损与 DSD 的播放版","lossless_format",{"FLAC":"flac","MP3":"mp3","AAC (.m4a)":"aac"})
        self.setting(pane,"有损来源的输出","lossy_format",{"保留 MP3/AAC，其余转 AAC":"preserve","全部转 MP3":"mp3","全部转 AAC":"aac"})
        self.check(pane,"目标编码相同时，也重新编码 MP3 / AAC","reencode_lossy")
        pane=section(host,"采样率、位深与声道","DSD 先按 DSD → PCM 采样率生成播放版。保留现有有损编码时，这里的采样率和声道设置不触发重新编码。")
        self.setting(pane,"PCM 采样率策略","resample_mode",{"保留原采样率":"preserve","仅降低高于上限的采样率":"limit","统一到指定采样率":"fixed"})
        self.setting(pane,"指定采样率 / 上限 (Hz)","sample_rate",RATES)
        self.setting(pane,"FLAC 位深","pcm_bits",{"保留原位深，DSD 默认 24 bit":0,"16 bit":16,"24 bit":24,"32 bit":32})
        self.setting(pane,"声道","channels",{"保留原声道":"preserve","立体声":"stereo","单声道":"mono"},"MP3 最多支持立体声，多声道来源会自动混缩并在预览中说明。")
        self.setting(pane,"重采样器","resampler",{"SWResample（快速）":"swr","SoXR（高精度）":"soxr"})
        self.setting(pane,"降低整数位深时的抖动","dither",{"三角抖动":"triangular","高通三角抖动":"triangular_hp","关闭":"none"})
        pane=section(host,"编码器详细参数")
        self.setting(pane,"FLAC 压缩级别","flac_compression",{str(n):n for n in range(13)},"级别更高通常更慢，音质相同；已有 FLAC 默认直接保留。")
        self.check(pane,"对已有 FLAC 也应用压缩级别并重新压缩","recompress_flac")
        self.setting(pane,"MP3 编码模式","mp3_mode",{"VBR 可变码率":"vbr","CBR 固定码率":"cbr"})
        self.setting(pane,"MP3 VBR 品质","mp3_vbr",{f"V{n}"+(" · 最高品质" if n==0 else ""):n for n in range(10)})
        self.setting(pane,"MP3 CBR (kbps)","mp3_kbps",{str(n):n for n in (64,96,128,160,192,224,256,320)})
        row=ctk.CTkFrame(pane,fg_color="transparent");row.pack(fill="x",padx=22,pady=(0,18))
        label(row,"AAC 目标码率 (kbps / 立体声)",size=13).pack(side="left")
        w=Choice(row,self.app.bitrate,{str(n):n for n in (96,128,160,192,224,256,320,384,448,512)},width=220)
        w.pack(side="right");self.app.setting_widgets.append(w)
        self.setting(pane,"MP3 ID3 标签版本","id3_version",{"保留原版本":"preserve","ID3v2.3（兼容旧播放器）":"3","ID3v2.4":"4"})
        pane=section(host,"DSD / SACD 与校验","DSD 和 SACD 原盘始终保留在 Disc Archives，原始音乐目录始终保留。")
        for title,var,choices in (("SACD 区域",self.app.area,{"双声道":"stereo","多声道":"multi","两个区域":"both"}),
                                  ("DSD → PCM (Hz)",self.app.rate,{"88200":88200,"176400":176400})):
            row=ctk.CTkFrame(pane,fg_color="transparent");row.pack(fill="x",padx=22,pady=(0,16))
            label(row,title,size=13).pack(side="left")
            w=Choice(row,var,choices,width=220);w.pack(side="right");self.app.setting_widgets.append(w)
        w=ctk.CTkCheckBox(pane,text="验证无损转换的 PCM；重采样或有损编码后验证完整解码",variable=self.app.verify,fg_color=ACCENT,text_color=INK,font=(FONT,12),checkbox_width=18,checkbox_height=18)
        w.pack(anchor="w",padx=22,pady=(0,20));self.app.setting_widgets.append(w)

    def audio_preset(self,key):
        defaults=Settings()
        fields=("lossless_format","lossy_format","reencode_lossy","recompress_flac","resample_mode","sample_rate","pcm_bits","channels","resampler","dither","flac_compression","mp3_mode","mp3_kbps","mp3_vbr")
        for name in fields:self.app.advanced_values[name].set(getattr(defaults,name))
        self.app.bitrate.set(256)
        if key in ("mp3","aac"):
            for name,value in (("lossless_format",key),("lossy_format",key),("resample_mode","limit"),("sample_rate",48000),("channels","stereo")):
                self.app.advanced_values[name].set(value)
        self.app.status.set("已应用音频预设；条件规则与命名设置保留，整理时生效。")

    def build_tools(self,help_text):
        host=self.scrollers["配置与工具"]
        pane=section(host,"整理配置","将外观、命名、转换参数与规则导出，之后整理其他曲库时直接导入。配置不包含音乐路径、音乐文件或手选的专辑资料。")
        row=ctk.CTkFrame(pane,fg_color="transparent");row.pack(fill="x",padx=22,pady=(0,20))
        for text,action in (("导出配置",self.export_profile),("导入配置",self.import_profile),("预览规则与路径",self.app._preview_plan)):
            w=button(row,text,action,width=140);w.pack(side="left",padx=(0,10));self.app.setting_widgets.append(w)
        self.profile_message=tk.StringVar(value="")
        label(pane,variable=self.profile_message,size=11,color=MUTED,wraplength=850).pack(anchor="w",padx=22,pady=(0,16))
        pane=section(host,"性能与附加文件")
        for title,var,choices in (("并行音频任务",self.app.workers,{str(n):n for n in (1,2,3,4,6,8,12,16)}),
                                  ("发行检索地区",self.app.country,{k:k for k in ("HK","CN","US","JP","TW","GB")})):
            row=ctk.CTkFrame(pane,fg_color="transparent");row.pack(fill="x",padx=22,pady=(0,16))
            label(row,title,size=13).pack(side="left")
            w=Choice(row,var,choices,width=220);w.pack(side="right");self.app.setting_widgets.append(w)
        self.check(pane,"封面内嵌的同时，另存 cover 图片","write_cover_file")
        self.check(pane,"生成全库 M3U8 播放列表","write_playlists")
        w=ctk.CTkCheckBox(pane,text="备份源目录中的图片与附页",variable=self.app.sidecars,fg_color=ACCENT,text_color=INK,font=(FONT,12),checkbox_width=18,checkbox_height=18)
        w.pack(anchor="w",padx=22,pady=(0,20));self.app.setting_widgets.append(w)
        pane=section(host,"工具与缓存")
        row=ctk.CTkFrame(pane,fg_color="transparent");row.pack(fill="x",padx=22,pady=(0,20))
        from media import resource
        from catalog import state_dir
        self.app.check_button=button(row,"检查内置工具",self.app._check_tools,width=133);self.app.check_button.pack(side="left",padx=(0,10))
        for text,action in (("依赖许可证",lambda:self.app._open(resource("Licenses"))),("查询缓存",lambda:self.app._open(state_dir())),("打开目标目录",lambda:self.app._open(self.app.dest.get()))):
            button(row,text,action,width=125).pack(side="left",padx=(0,10))
        pane=section(host,"使用说明")
        text=ctk.CTkTextbox(pane,fg_color=WHITE,text_color=MUTED,font=(FONT,12),height=430,wrap="word")
        text.pack(fill="x",padx=18,pady=(0,18));text.insert("1.0",help_text);text.configure(state="disabled")

    def export_profile(self):
        if not self.rules.commit_pending():return
        try:
            settings=self.app._settings_value()
            path=filedialog.asksaveasfilename(parent=self.app,title="导出整理配置",defaultextension=".json",initialfile="MusicOrganizer-Profile.json",filetypes=[("整理配置","*.json")])
            if not path:return
            public_settings=asdict(settings)
            public_settings.pop("platform_key_file",None)
            write_atomic(Path(path),json.dumps(dict(schema=1,version=VERSION,settings=public_settings,appearance=self.app.appearance.get(),accent=self.app.accent.get()),ensure_ascii=False,indent=2).encode("utf-8"))
            self.profile_message.set("配置已导出："+path)
        except Exception as exc:messagebox.showerror("无法导出配置",str(exc),parent=self.app)

    def import_profile(self):
        path=filedialog.askopenfilename(parent=self.app,title="导入整理配置",filetypes=[("整理配置","*.json")])
        if not path:return
        try:
            if Path(path).stat().st_size>2*1024**2:raise ValueError("配置文件超过 2 MB")
            data=json.loads(Path(path).read_text(encoding="utf-8-sig"))
            if data.get("schema")!=1:raise ValueError("不支持此配置版本")
            settings=Settings(**data["settings"])
            settings=replace(settings,platform_key_file=self.app.advanced_values["platform_key_file"].get())
            mode=data.get("appearance","light");accent=data.get("accent","violet")
            if mode not in MODES.values() or accent not in BASES:raise ValueError("外观选项无效")
            self.app._apply_settings(settings)
            self.app.appearance.set(mode);self.app.accent.set(accent)
            self.app._save();self.rules.reload();self.platform_panel.refresh()
            self.profile_message.set("已导入配置："+Path(path).name+"；整理时生效。")
        except Exception as exc:messagebox.showerror("无法导入配置",str(exc),parent=self.app)


def show_plan(app):
    if app.busy:return
    if not app.advanced.rules.commit_pending():return
    try:
        settings=app._settings_value()
        from preview import preview_rows
        rows=preview_rows(app.items,settings,app.effective_tags)
        if not rows:
            app.status.set("先只读扫描音乐目录，再在高级设置中预览规则与路径。")
            return
    except Exception as exc:messagebox.showerror("无法预览",str(exc),parent=app);return
    dialog=ctk.CTkToplevel(app);dialog.title("整理前预览 · 不写入文件");dialog.geometry("1080x680");dialog.minsize(860,550);dialog.configure(fg_color=BG);dialog.transient(app)
    header=ctk.CTkFrame(dialog,fg_color="transparent");header.pack(fill="x",padx=24,pady=(22,14))
    label(header,"整理前预览",size=23,bold=True).pack(side="left")
    summary=CounterForPreview(rows)
    label(header,summary,size=12,color=MUTED).pack(side="right")
    label(dialog,"基于当前标签与已保存规则；在线补全及 NCM / 原盘 / CUE 展开后资料可能改变。不同音频版本与同名冲突将在实际写入时核对。",size=11,color=MUTED,wraplength=1000,justify="left").pack(anchor="w",padx=24,pady=(0,14))
    panel=card(dialog);panel.pack(fill="both",expand=True,padx=24,pady=(0,16))
    table=tree(panel,[("source","源文件",220),("rule","命中规则",150),("conversion","处理结果",260),("target","目标路径",420),("note","提示",200)],app.scale)
    for i,row in enumerate(rows[:3000]):table.insert("","end",values=[row[k] for k in ("source","rule","conversion","target","note")],tags=("stripe",) if i%2 else ())
    actions=ctk.CTkFrame(dialog,fg_color="transparent");actions.pack(fill="x",padx=24,pady=(0,24))
    label(actions,"只读预览"+(" · 界面显示前 3,000 项，CSV 包含全部" if len(rows)>3000 else ""),size=11,color=MUTED).pack(side="left")
    def export():
        path=filedialog.asksaveasfilename(parent=dialog,title="导出路径与规则预览",initialfile="Organization-Preview.csv",defaultextension=".csv",filetypes=[("CSV","*.csv")])
        if path:
            write_atomic(Path(path),csv_bytes(["source","rule","conversion","target","note"],([r[k] for k in ("source","rule","conversion","target","note")] for r in rows)))
            app.status.set("预览已导出："+path)
    button(actions,"导出全部 CSV",export,width=140).pack(side="right",padx=(10,0))
    button(actions,"关闭",dialog.destroy,width=90).pack(side="right")
    dialog.bind("<Escape>",lambda e:dialog.destroy())
    from dialogs import center
    center(app,dialog)


def CounterForPreview(rows):
    count=sum(bool(r["target"]) for r in rows)
    rules=len({r["rule"] for r in rows if r["rule"] not in ("","默认设置","展开后匹配")})
    return f"{len(rows):,} 项 · {count:,} 个路径 · 命中 {rules} 条规则"
