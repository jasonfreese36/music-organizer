import dataclasses
import io
import json
import os
import queue
import threading
import tkinter as tk
import traceback
import urllib.parse
import webbrowser
from collections import Counter
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import customtkinter as ctk
from theme import color, resolved

from PIL import Image, ImageTk

from catalog import Catalog, HTTP, SOURCES, state_dir
from engine import Organizer
from inventory import infer_track, scan
from media import Tools, embedded_cover, make_cover, resource
from model import (APP_NAME, VERSION, Cancel, Cancelled, Settings, component,
                   short_hash, validated_roots, write_atomic)
from sources import manual_alignment, test_sources


HELP = """整理规则
• 目标结构：Albums / Disc Archives / Needs Review / Library Records / Playlists。
• FLAC、MP3、AAC（.m4a 容器）为播放库格式；MP3/AAC 尽量直接复制或封装，PCM 无损转 FLAC。
• Singles 与 Recovered Audio 按发行信息归入 Albums。保留原语言的艺术家、专辑和曲名。
• DSD（DSF/DFF）和 SACD ISO 原盘保留副本，生成 FLAC 播放版；CUE 整轨保留并按采样分轨。
• 平台加密音频先备份再自动解密；网易云、QQ、酷狗、酷我、咪咕的支持版本见高级设置 → 平台音频。
• 本地标签和内嵌/同目录封面优先；在线使用 MusicBrainz、Cover Art Archive 和 Apple iTunes。
• 用艺术家、专辑、曲名、轨序和时长核对在线匹配，记录来源。匹配不充分时保留信息并列出问题。
• 封面内嵌音轨，同时保存 cover 图片。163 key、QQ 等平台标识不写入整理后的播放库。
• 同一发行、相同音频只保留一份；不同录音/母带单独保留 Alternate 版本。
• 明确标有 LP rip / vinyl / 黑胶的目录保留 Vinyl Rip 版本；不会仅凭高采样率判定黑胶。

使用方式
1. 选择源文件夹和独立目标文件夹，点击“只读扫描”。扫描不会联网修改，也不会写入源目录。
2. 预览原始标签；可选中音轨更正标签、整张专辑指定本地封面或封面网址。
3. 点击“开始整理”。可随时停止；已完成的音轨保留，重新运行到同一目标目录可继续。
4. 查看整理结果和 Needs Review/Review.csv。修正预览信息后重跑即可更新已有音轨。

数据源与在线资料
• 在“数据源”分别启用标签和封面来源，选择优先顺序，并测试当前连接。
• 测试会绕过缓存，检查真实资料接口与图片下载，显示测试时间和用时。
• 选中音轨后点击“查找封面与标签”，比较多个来源、多个发行版本。
• 标签和封面可分别选用：例如 MusicBrainz 标签搭配 Apple iTunes 封面。
• 查看“发行资料”和“曲目对照”，选定后应用到预览；选择会按专辑保存。
• “整理时自动联网”控制自动处理；手动搜索和测试仍会联网。
• 已缓存的手选资料可离线应用，可用“清除手选”恢复自动匹配。

高级设置（按需使用）
• 初次打开保持 v1.1 默认外观、命名和转换行为，条件规则为空。
• 外观：浅色 / 深色 / 跟随系统，五种主题色。
• 目录与命名：点选结构与文件名预设、插入资料字段，实时预览；支持歌名在前与多碟命名。
• 音频转换：格式、采样率策略、位深、声道、重采样器、抖动、FLAC 压缩、MP3 / AAC 编码参数。
• 条件规则：点选格式、码率、采样率等条件与处理动作，可启停、复制与排序，无需写代码。
• 平台音频：自动处理开关、解密并行数、完整校验与本地密钥导入。密钥不写入导出配置。
• 规则从上到下采用第一条命中项，未命中沿用默认。相同 MP3/AAC 编码默认保留，主动启用重新编码才应用新的码率。
• 扫描后可预览每首歌的命中规则、转换和目标路径，并导出 CSV；配置可导出 / 导入复用。

速度与限制
默认 4 个音频任务并行；机械硬盘可选 2，SSD 可选 4–8。在线查询按专辑缓存，遵守服务限速。
首次运行 EXE 需解压内置运行时和工具；无需另装 Python、FFmpeg、ncmdump、平台解密核心或 SACD 工具。
QQ STag / musicex、酷狗 KGG / crypto v5 及部分 MG3D 需要对应的本地密钥；MGM 暂未支持。缺密钥和未支持版本会保留并报告。
建议目标磁盘预留播放库、DSD 原盘和最大一张整轨 PCM 临时空间。
SACD 严格处理读取错误；无法解码的原盘会保留并报告。非 SACD 的普通 ISO 只备份并报告。
PCM 无损转换默认做解码校验；DSD 转 PCM 属转换，原 DSD 永久保留在 Disc Archives。
非 MP3/AAC 的有损格式转 AAC 会再次有损，原文件始终保留在源目录。
名称相同但音频无法确认相同的文件会保留。所有分歧、失败和来源均在 Library Records 中记录。
外部音乐目录中的快捷方式、符号链接和重解析点跳过，避免跨目录操作。
在线服务可能缺少发行信息或封面；可手动选择封面/提供图片链接，不生成替代封面。

依赖与许可
应用源码及各依赖许可见随附 Source 和 Licenses。此程序不上传音频，在线查询仅发送发行检索词。
个人整理工具。网络服务和封面素材仍适用各自的使用条款。
"""


class App(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("light")
        super().__init__()
        self.title(f"{APP_NAME} · 音乐整理工具")
        self.scale = self.winfo_fpixels("1i") / 96
        width = min(1360, round(self.winfo_screenwidth()/self.scale)-48)
        height = min(920, round(self.winfo_screenheight()/self.scale)-70)
        self.geometry(f"{width}x{height}+24+24")
        self.minsize(min(1120, width), min(760, height))
        try:
            self.iconbitmap(resource("app.ico"))
        except tk.TclError:
            pass
        self.events, self.cancel, self.thread = queue.Queue(), Cancel(), None
        self.items, self.results, self.overrides, self.cover_overrides = [], [], {}, {}
        self.item_by_rel={}
        self.selections = {}
        self.network_results = {}
        self.source = tk.StringVar()
        self.dest = tk.StringVar()
        self.filter = tk.StringVar()
        self.status = tk.StringVar(value="选择音乐源目录，开始只读扫描")
        self.count = tk.StringVar(value="尚未扫描")
        self.detail = tk.StringVar(value="选中一条音轨查看标签和封面\n\n可在整理前更正专辑信息。")
        self.progress_text = tk.StringVar(value="准备就绪")
        self.online, self.verify, self.sidecars = tk.BooleanVar(value=True), tk.BooleanVar(value=True), tk.BooleanVar(value=True)
        self.workers, self.country = tk.IntVar(value=4), tk.StringVar(value="HK")
        self.area, self.rate, self.bitrate = tk.StringVar(value="stereo"), tk.IntVar(value=88200), tk.IntVar(value=256)
        self.tag_enabled = {key:tk.BooleanVar(value=True) for key in ("musicbrainz","itunes")}
        self.cover_enabled = {key:tk.BooleanVar(value=True) for key in ("coverartarchive","itunes")}
        self.tag_priority = tk.StringVar(value="MusicBrainz")
        self.cover_priority = tk.StringVar(value="Cover Art Archive")
        self.appearance=tk.StringVar(value="light")
        self.accent=tk.StringVar(value="violet")
        legacy={"online","workers","country","keep_sidecars","verify_pcm","sacd_area","sacd_rate","aac_kbps","tag_sources","cover_sources","rules"}
        defaults=Settings()
        self.advanced_values={}
        for field in dataclasses.fields(Settings):
            if field.name in legacy:continue
            value=getattr(defaults,field.name)
            kind=tk.BooleanVar if isinstance(value,bool) else tk.IntVar if isinstance(value,int) else tk.StringVar
            self.advanced_values[field.name]=kind(value=value)
        self.custom_rules=[]
        self.busy, self.closing, self.scanned_source = False, False, None
        self.cover_photo = None
        self.config_path = state_dir() / "Settings.json"
        self._load()
        from theme import set_accent
        set_accent(self.accent.get())
        ctk.set_appearance_mode(self.appearance.get())
        self._styles()
        self._build()
        for variable in (*self.tag_enabled.values(), *self.cover_enabled.values(), self.tag_priority, self.cover_priority):
            variable.trace_add("write", lambda *a:self._update_source_summary())
        self._update_source_summary()
        for variable in (self.appearance,self.accent):variable.trace_add("write",lambda *a:self._apply_theme())
        try:
            saved = json.loads((state_dir()/"NetworkStatus.json").read_text(encoding="utf-8"))
            for value in saved.values():self._show_source_test(value, persist=False)
        except (ValueError,OSError,TypeError,KeyError):
            pass
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(80, self._pump)

    def _styles(self):
        from ui import styles
        styles(self)

    def _build(self):
        from ui import build
        self.setting_widgets = []
        build(self, HELP)

    def show_page(self, key):
        from ui import show_page
        if key=="settings" and hasattr(self,"advanced"):self.advanced.platform_panel.refresh()
        if key == "online" and hasattr(self, "lookup_panel"):
            _, item = self._selected()
            if item is not None and infer_track(item).edit_key not in self.lookup_panel.keys:
                self.lookup_panel.set_context(self._album_items(item))
        show_page(self, key)

    def _load(self):
        try:
            values = json.loads(self.config_path.read_text(encoding="utf-8"))
            self.source.set(values.get("source", ""))
            self.dest.set(values.get("dest", ""))
            for key in ("online", "verify", "sidecars", "workers", "country", "area", "rate", "bitrate"):
                if key in values:
                    getattr(self, key).set(values[key])
            for field,mapping,priority in (("tag_sources",self.tag_enabled,self.tag_priority),("cover_sources",self.cover_enabled,self.cover_priority)):
                if field in values:
                    selected=values[field]
                    for key,variable in mapping.items():variable.set(key in selected)
                    if selected and selected[0] in SOURCES:priority.set(SOURCES[selected[0]]["name"])
            for key,variable in self.advanced_values.items():
                if key in values.get("advanced",{}):variable.set(values["advanced"][key])
            from rules import validate_rules
            self.custom_rules=validate_rules(values.get("rules",[]))
            from theme import BASES,MODES
            if values.get("appearance") in MODES.values():self.appearance.set(values["appearance"])
            if values.get("accent") in BASES:self.accent.set(values["accent"])
        except (ValueError, OSError, tk.TclError):
            pass

    def _save(self):
        values = {key: getattr(self, key).get() for key in ("source", "dest", "online", "verify", "sidecars", "workers", "country", "area", "rate", "bitrate")}
        values.update(tag_sources=self._ordered_sources(self.tag_enabled,self.tag_priority),cover_sources=self._ordered_sources(self.cover_enabled,self.cover_priority),
                      advanced={k:v.get() for k,v in self.advanced_values.items()},rules=self.custom_rules,
                      appearance=self.appearance.get(),accent=self.accent.get())
        write_atomic(self.config_path, json.dumps(values, ensure_ascii=False, indent=2).encode("utf-8"))

    def _profile_path(self):
        return state_dir() / "Profiles" / (short_hash(str(Path(self.source.get()).resolve())) + ".json")

    def _load_profile(self):
        self.overrides, self.cover_overrides, self.selections = {}, {}, {}
        try:
            values = json.loads(self._profile_path().read_text(encoding="utf-8"))
            self.overrides, self.cover_overrides = values.get("tags", {}), values.get("covers", {})
            self.selections=values.get("selections",{})
            track_tags = values.get("tracks", {})
            self.items = [dataclasses.replace(i, tags=i.tags | track_tags.get(str(i.rel), {}), edits=track_tags.get(str(i.rel), {})) for i in self.items]
        except (ValueError, OSError):
            pass

    def _save_profile(self):
        write_atomic(self._profile_path(), json.dumps(dict(tags=self.overrides, covers=self.cover_overrides,
                                                         selections=self.selections,
                                                         tracks={str(i.rel): i.edits for i in self.items if i.edits}), ensure_ascii=False, indent=2).encode("utf-8"))

    def _browse_source(self):
        path = filedialog.askdirectory(title="选择音乐源目录", initialdir=self.source.get() or None)
        if path:
            self.source.set(path)
            self.dest.set(str(Path(path).with_name(component(Path(path).name + "_Organized", 70))))
            self.items, self.scanned_source = [], None
            self.run_button.configure(state="disabled")
            self._show_items()

    def _browse_dest(self):
        path = filedialog.askdirectory(title="选择独立的目标目录，可新建", initialdir=self.dest.get() or None, mustexist=False)
        if path:
            self.dest.set(path)

    def _settings_value(self):
        return Settings(online=self.online.get(), workers=self.workers.get(), country=self.country.get(),
                        keep_sidecars=self.sidecars.get(), verify_pcm=self.verify.get(), sacd_area=self.area.get(),
                        sacd_rate=self.rate.get(), aac_kbps=self.bitrate.get(),
                        tag_sources=self._ordered_sources(self.tag_enabled,self.tag_priority),cover_sources=self._ordered_sources(self.cover_enabled,self.cover_priority),
                        **{k:v.get() for k,v in self.advanced_values.items()},rules=tuple(self.custom_rules))

    def _ordered_sources(self,mapping,priority):
        selected=[key for key,variable in mapping.items() if variable.get()]
        selected.sort(key=lambda key:SOURCES[key]["name"]!=priority.get())
        return tuple(selected)

    def _apply_settings(self,settings):
        for field,alias in (("online","online"),("workers","workers"),("country","country"),("keep_sidecars","sidecars"),
                            ("verify_pcm","verify"),("sacd_area","area"),("sacd_rate","rate"),("aac_kbps","bitrate")):
            getattr(self,alias).set(getattr(settings,field))
        for key,variable in self.advanced_values.items():variable.set(getattr(settings,key))
        for field,mapping,priority in (("tag_sources",self.tag_enabled,self.tag_priority),("cover_sources",self.cover_enabled,self.cover_priority)):
            selected=getattr(settings,field)
            for key,variable in mapping.items():variable.set(key in selected)
            if selected:priority.set(SOURCES[selected[0]]["name"])
        self.custom_rules=list(settings.rules)

    def _apply_theme(self):
        from theme import set_accent,refresh_native
        set_accent(self.accent.get(),self)
        ctk.set_appearance_mode(self.appearance.get())
        refresh_native(self)
        self.show_page(getattr(self,"current_page","settings"))
        self._save()

    def _set_appearance_mode(self,mode):
        super()._set_appearance_mode(mode)
        if hasattr(self,"preview"):
            from theme import refresh_native
            refresh_native(self)

    def _preview_plan(self):
        from advanced_ui import show_plan
        show_plan(self)

    def _update_source_summary(self):
        if hasattr(self,"source_summary"):
            self.source_summary.set(f"{sum(v.get() for v in self.tag_enabled.values())} 个标签源 · {sum(v.get() for v in self.cover_enabled.values())} 个封面源")
        if hasattr(self,"lookup_panel"):self.lookup_panel.refresh_buttons()

    def _test_sources(self, providers=None):
        if self.busy:return
        settings=self._settings_value()
        self.show_page("sources")
        def perform():
            http=HTTP()
            try:
                results=test_sources(http,settings,self.cancel,self._emit,providers)
                self._emit("network_done",results)
            finally:http.close()
        self._start(perform,"正在实时测试数据源连接…")

    def _show_source_test(self,result,persist=True):
        key=result.get('source')
        if key not in self.source_cards:return
        self.network_results[key]=result
        item=self.source_cards[key]
        state=result.get('state','error')
        title={"ok":"连接可用","partial":"部分可用","error":"连接失败"}.get(state,"未测试")
        colors={"ok":(color('#E7F4ED'),color('#348467')),"partial":(color('#FFF3DD'),color('#A57D35')),"error":(color('#FCEBEF'),color('#AD5F73'))}
        bg,fg=colors.get(state,(color('#F3F1F8'),color('#9D96AE')))
        item['status'].configure(text=f"  {title}  ·  {result.get('milliseconds',0)/1000:.1f} s  ",fg_color=bg,text_color=fg)
        when=str(result.get('checked_at',''))[11:19]
        item['detail'].configure(text=f"上次测试 {when}  ·  {str(result.get('detail',''))[:180]}")
        if persist:
            write_atomic(state_dir()/"NetworkStatus.json",json.dumps(self.network_results,ensure_ascii=False,indent=2).encode('utf-8'))

    def effective_tags(self,item):
        track=infer_track(item);tags=dict(track.tags)
        choice=self.selections.get(track.edit_key,{}).get('metadata')
        if choice:
            for key in ('album','albumartist','date','label','catalognumber','barcode'):
                if choice.get(key):tags[key]=choice[key]
            if item.profile:
                aligned=manual_alignment([track],choice)
                song=aligned.get(0)
                if song:
                    for key in ('title','artist','genre'):
                        if song.get(key):tags[key]=song[key]
                    from model import count_tag
                    tags['tracknumber']=count_tag(song['track'],song.get('total',0))
                    tags['discnumber']=count_tag(song['disc'],song.get('disctotal',0))
        tags.update(self.overrides.get(track.edit_key,{}));tags.update(item.edits)
        return tags

    def _album_items(self,item):
        key=infer_track(item).edit_key
        members=[i for i in self.items if i.kind in {'audio','ncm','encrypted','iso','cue'} and infer_track(i).edit_key==key]
        if item.kind=='cue':
            try:
                from formats import parse_cue,resolve_cue_file
                _,parts=parse_cue(item.path)
                refs={resolve_cue_file(item.path,p.file,self.scanned_source) for p in parts}
                members += [i for i in self.items if i.path in refs and i not in members]
            except (ValueError,OSError):pass
        return members

    def _open_lookup(self):
        if self.busy:return
        _,item=self._selected()
        if item is not None:self.lookup_panel.set_context(self._album_items(item))
        self.show_page("online")

    def _start(self, function, operation):
        if self.busy:
            return
        self._save()
        self.busy, self.cancel = True, Cancel()
        self.status.set(operation)
        self.progress.configure(value=0)
        self._state()

        def work():
            try:
                function()
            except Cancelled:
                self.events.put(("log", "已停止当前操作"))
            except Exception as exc:
                self.events.put(("failure", str(exc)))
                self.events.put(("log", traceback.format_exc()))
            finally:
                self.events.put(("done", None))
        self.thread = threading.Thread(target=work, name="organizer-ui-worker", daemon=False)
        self.thread.start()

    def _emit(self, kind, value):
        self.events.put((kind, value))

    def _scan(self):
        try:
            source, dest = validated_roots(self.source.get(), self.dest.get())
            settings = self._settings_value()
        except Exception as exc:
            messagebox.showerror("无法扫描", str(exc), parent=self)
            return
        self.items, self.results, self.scanned_source = [], [], None
        self.result_tree.delete(*self.result_tree.get_children())
        self._show_items()

        def perform():
            tools = Tools()
            tools.verify(self.cancel)
            items, skipped = scan(source, tools, self.cancel, settings.workers, self._emit,settings=settings)
            self._emit("scanned", (source, items, skipped))
        self._start(perform, "正在只读扫描，源目录不会改动")

    def _run(self):
        if not self.advanced.rules.commit_pending():
            self.show_page("settings");self.advanced.tabs.set("条件规则");return
        try:
            source, dest = validated_roots(self.source.get(), self.dest.get())
            if source != self.scanned_source:
                raise ValueError("源目录已改变，请先重新扫描")
            if self.lookup_panel.dirty and self.lookup_panel.items:self.lookup_panel.apply()
            settings = self._settings_value()
            items = tuple(self.items)
            overrides, cover_overrides, selections = dict(self.overrides), dict(self.cover_overrides), dict(self.selections)
        except Exception as exc:
            messagebox.showerror("无法开始", str(exc), parent=self)
            return
        self.results = []
        self.result_tree.delete(*self.result_tree.get_children())
        self.notebook.select(1)

        def perform():
            Organizer(source, dest, items, settings, Tools(), self.cancel, self._emit,
                      overrides=overrides, cover_overrides=cover_overrides, selections=selections).run()
        self._start(perform, "正在整理到目标目录，原文件保留在源目录")

    def _check_tools(self):
        def perform():
            for key, value in Tools().verify(self.cancel).items():
                self._emit("log", f"{key}: {value.splitlines()[0]}")
            self._emit("toolcheck", None)
        self.notebook.select(2)
        self._start(perform, "正在检查内置依赖")

    def _refresh_platform_keys(self):
        if self.busy:return
        from platform_audio import KeyStore,probe_platform
        settings=self._settings_value();snapshot=[(i,item) for i,item in enumerate(self.items) if item.crypto]
        if not snapshot:
            self.advanced.platform_panel.refresh();self._save();return
        def perform():
            keys=KeyStore(settings.platform_key_file)
            for n,(i,item) in enumerate(snapshot,1):
                self.cancel.check();item.check()
                info=probe_platform(item.path,item.crypto.get("family"),keys)
                self._emit("platform_probed",(i,info));self._emit("progress",("重查平台密钥",n,len(snapshot)))
            self._emit("platform_keys_done",len(snapshot))
        self._start(perform,"正在重新核对平台音频的本地密钥…")

    def _state(self):
        for widget in (self.scan_button, self.src_entry, self.dst_entry, self.src_button, self.dst_button,
                       self.edit_button, self.cover_button, self.lookup_button, self.check_button, self.test_sources_button,
                       *(c['button'] for c in self.source_cards.values()), *self.setting_widgets):
            widget.configure(state="disabled" if self.busy else "readonly" if isinstance(widget, (ttk.Combobox,ctk.CTkComboBox)) else "normal")
        self.run_button.configure(state="normal" if not self.busy and self.scanned_source else "disabled")
        self.cancel_button.configure(state="normal" if self.busy else "disabled")
        self.lookup_panel.refresh_buttons()
        self.advanced.rules.set_busy(self.busy)

    def _cancel(self):
        self.cancel.stop()
        self.status.set("正在停止，等待工具退出并保存报告…")
        self.cancel_button.configure(state="disabled")

    def _show_items(self):
        if not hasattr(self, "preview"):
            return
        self.preview.delete(*self.preview.get_children())
        query = self.filter.get().strip().casefold()
        shown = 0
        relevant = [i for i in self.items if i.kind in {"audio","ncm","encrypted","iso","cue"}]
        for index, item in enumerate(self.items):
            if item.kind not in {"audio","ncm","encrypted","iso","cue"}:
                continue
            tags = self.effective_tags(item)
            if query:
                from model import match_name
                corpus=str(item.rel)+" "+" ".join(tags.values())
                if query not in corpus.casefold() and match_name(query) not in match_name(corpus):continue
            self.preview.insert("", "end", iid=str(index), values=(tags.get("title", item.path.name), tags.get("artist", ""),
                                tags.get("album", item.rel.parent.name), item.profile.codec.upper() if item.profile else item.crypto.get("name",item.kind.upper()),
                                "已选" if self.selections.get(infer_track(item).edit_key,{}).get('cover') or self.cover_overrides.get(infer_track(item).edit_key) else "有" if item.has_cover else "待查"),tags=("stripe",) if shown%2 else ())
            shown += 1
            if shown >= 6000:
                break
        self.count.set(f"{len(relevant):,} 个音频/原盘项目  ·  {sum(i.size for i in self.items)/1024**3:.2f} GB" + ("  ·  预览前 6,000 条，可筛选" if shown >= 6000 else ""))
        if hasattr(self,"summary_files"):
            self.summary_files.set(f"{len(relevant):,}")
            groups={(self.effective_tags(i).get('albumartist',''),self.effective_tags(i).get('album','')) for i in relevant}
            self.summary_albums.set(f"{len(groups):,}")
            size=sum(i.size for i in self.items)
            self.summary_size.set(f"{size/1024**3:.2f} GB" if size>=1024**3 else f"{size/1024**2:.1f} MB")
            if relevant:self.empty_state.place_forget()
            else:self.empty_state.place(relx=.5,rely=.5,anchor="center")

    def _selected(self):
        values = self.preview.selection()
        return (int(values[0]), self.items[int(values[0])]) if values else (None, None)

    def _selection(self, event=None):
        index, item = self._selected()
        if item is None:
            return
        if hasattr(self,"advanced"):self.advanced.queue_preview()
        track = infer_track(item)
        tags = self.effective_tags(item)
        self.inspector_title.set(tags.get('album',item.path.name))
        selected=self.selections.get(track.edit_key,{})
        metadata=selected.get('metadata',{}).get('provider')
        artwork=selected.get('cover',{}).get('provider')
        self.selection_sources.set(f"标签 · {SOURCES.get(metadata,{}).get('name','本地资料')}\n封面 · {SOURCES.get(artwork,{}).get('name','本地优先')}")
        self.detail.set(f"{tags.get('artist','—')}\n\n发行  {tags.get('date') or '待补充'}\n轨序 {tags.get('tracknumber','—')}  ·  碟序 {tags.get('discnumber','—')}\n\n{item.rel}"+(f"\n\n读取问题：{item.error[:180]}" if item.error else ""))
        if item.crypto:
            from platform_audio import STATUS
            self.detail.set(self.detail.get()+f"\n\n{item.crypto.get('name','')} · {item.crypto.get('version','')}\n{STATUS.get(item.crypto.get('state'),'待处理')}\n{item.crypto.get('detail','')}")
        cover = None
        custom = selected.get('cover',{}).get('path') or self.cover_overrides.get(track.edit_key)
        try:
            cover = make_cover(Path(custom).read_bytes(), "用户指定") if custom else embedded_cover(item.path) if item.has_cover else None
        except Exception:
            pass
        if cover:
            image = Image.open(io.BytesIO(cover.data))
            image.thumbnail((round(148*self.scale), round(148*self.scale)), Image.Resampling.LANCZOS)
            self.cover_photo = ImageTk.PhotoImage(image)
            self.art_label.configure(image=self.cover_photo, text="")
        else:
            self.cover_photo = None
            self.art_label.configure(image=self.placeholder_photo, text="")

    def _edit(self):
        from dialogs import edit
        edit(self)

    def _cover_dialog(self):
        from dialogs import cover
        cover(self)

    def _open(self, path):
        try:
            target = Path(path)
            if not str(path) or not target.exists():
                raise ValueError("该目录尚不存在，整理开始后会自动创建")
            os.startfile(target)
        except Exception as exc:
            messagebox.showinfo("打开目录", str(exc), parent=self)

    def _open_result(self, event=None):
        selected = self.result_tree.selection()
        if selected:
            result = self.results[int(selected[0])]
            self._open(Path(self.dest.get()) / result["target"])

    def _log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        if int(self.log.index("end-1c").split(".")[0]) > 8000:
            self.log.delete("1.0", "1000.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _pump(self):
        try:
            for _ in range(250):
                kind, value = self.events.get_nowait()
                if kind == "lookup_event":
                    self.lookup_panel.event(*value)
                elif kind == "lookup_cover":
                    self.lookup_panel.cover_event(*value)
                elif kind == "source_test":
                    self._show_source_test(value)
                    self._log(f"{value['name']} · {value['state']} · {value['detail']}")
                elif kind == "source_testing":
                    self.source_cards[value]['status'].configure(text="  测试中…  ",fg_color=color('#EEEBFC'),text_color=color('#6556DC'))
                    self.source_cards[value]['detail'].configure(text="正在通过真实请求验证资料接口与图片服务。")
                    self.progress_text.set("连接测试 · "+SOURCES[value]['name'])
                elif kind == "network_done":
                    good=sum(r['state']=='ok' for r in value)
                    partial=sum(r['state']=='partial' for r in value)
                    failed=sum(r['state']=='error' for r in value)
                    self.status.set(f"连接测试完成 · {good} 可用 · {partial} 部分可用 · {failed} 失败")
                    self.progress_text.set("已通过真实请求检查资料接口与图片下载")
                    self.progress.configure(value=100)
                elif kind == "log":
                    self._log(value)
                elif kind == "platform_probed":
                    index,info=value
                    if 0<=index<len(self.items):self.items[index]=dataclasses.replace(self.items[index],crypto=info)
                elif kind == "platform_keys_done":
                    self.status.set(f"本地密钥匹配已更新 · {value:,} 个平台文件。可查看支持状态并开始整理。")
                    self.progress_text.set("密钥匹配完成")
                    self.progress.configure(value=100)
                elif kind == "platform":
                    index=self.item_by_rel.get(value.get("source"))
                    if index is not None:
                        self.items[index]=dataclasses.replace(self.items[index],crypto={**self.items[index].crypto,**value})
                    from platform_audio import STATUS
                    self._log(f"{value.get('name','平台音频')} · {STATUS.get(value.get('state'),'待处理')} · {value.get('source','')} · {value.get('detail','')}")
                elif kind == "progress":
                    label, done, total = value
                    self.progress_text.set(f"{label} · {done:,} / {total:,}")
                    self.progress.configure(value=done/max(1, total)*100)
                elif kind == "scanned":
                    source, self.items, skipped = value
                    self.item_by_rel={str(item.rel):i for i,item in enumerate(self.items)}
                    self.scanned_source = source
                    self._load_profile()
                    self._show_items()
                    self.advanced.platform_panel.refresh()
                    self.status.set(f"只读扫描完成 · {len(self.items):,} 个文件 · 跳过 {len(skipped)} 项。可预览、更正标签与封面，然后开始整理。")
                    self.progress.configure(value=100)
                    self.progress_text.set("扫描完成")
                    for path, issue in skipped:
                        self._log(f"跳过 · {path} · {issue}")
                elif kind == "result":
                    index = len(self.results)
                    self.results.append(value)
                    labels = {"written":"已写入","reused":"已复用","converted":"已转换","duplicate":"已去重"}
                    if index < 10000:
                        self.result_tree.insert("", "end", iid=str(index), values=(labels.get(value["status"], value["status"]), value["title"], value["album"], value["target"], value["issues"],value['metadata_source'],value['cover_source']),tags=("stripe",) if index%2 else ())
                elif kind == "summary":
                    label = {"completed": "整理完成", "completed_with_errors": "整理完成，部分项目失败", "cancelled": "已停止", "failed": "任务失败"}.get(value["status"], value["status"])
                    changed=f" · 转换 {value.get('converted',0)}" if value.get('converted') else ""
                    self.status.set(f"{label} · 新增 {value['written']} · 复用 {value['reused']}{changed} · 去重 {value['duplicates']} · 有提示 {value['tracks_with_issues']} · 错误 {value['errors']} · {value['elapsed_seconds']:.1f} 秒")
                    self.progress_text.set("报告已保存到 Library Records；待处理事项见 Needs Review")
                    self.progress.configure(value=100 if value["status"].startswith("completed") else 0)
                    self._log(self.status.get())
                elif kind == "manualcover":
                    groups, cover = value
                    if isinstance(groups,str):groups=[groups]
                    path = state_dir() / "Manual Covers" / (short_hash(cover.data.hex()) + (".jpg" if cover.mime == "image/jpeg" else ".png"))
                    write_atomic(path, cover.data)
                    for group in groups:
                        self.cover_overrides[group] = str(path)
                        if group in self.selections:self.selections[group].pop('cover',None)
                    self._save_profile()
                    self._selection()
                    self.status.set("封面已加入预览配置；整理时将内嵌整张专辑。")
                elif kind == "toolcheck":
                    self.status.set("FFmpeg、FFprobe、ncmdump、平台音频核心、SACD Extract 内置依赖检查通过")
                    self.progress_text.set("内置依赖可用")
                elif kind == "failure":
                    self.status.set("操作失败："+value[:300])
                    if not self.closing:
                        messagebox.showerror("操作失败", value[:1500], parent=self)
                elif kind == "done":
                    self.busy = False
                    if self.lookup_panel.search_busy:
                        self.lookup_panel.search_busy=False
                        if self.cancel.event.is_set():
                            self.lookup_panel.message.set("查询已停止，已取得的发行仍可选用。")
                            self.status.set("查询已停止。")
                    self._state()
                    if self.closing:
                        self.destroy()
                        return
                    self.advanced.platform_panel.refresh()
                    self._selection()
        except queue.Empty:
            pass
        except Exception:
            if self.closing:return
            self.status.set("界面更新出现问题，可查看运行日志并重试操作。")
            self._log(traceback.format_exc())
        self.after(80, self._pump)

    def _close(self):
        self._save()
        if self.busy:
            self.closing = True
            self._cancel()
            self.status.set("正在停止并关闭；已完成的音轨和报告将保留。")
        else:
            self.destroy()

    def destroy(self):
        self.closing=True
        if hasattr(self,'lookup_panel'):self.lookup_panel.close()
        super().destroy()


def launch():
    # Per-monitor v2 DPI awareness falls back on older Windows versions.
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    App().mainloop()
