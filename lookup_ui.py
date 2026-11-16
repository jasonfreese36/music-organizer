import copy
import hashlib
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tkinter as tk

import customtkinter as ctk
from theme import color, resolved
from PIL import Image

from catalog import Catalog, HTTP, SOURCES, state_dir
from inventory import infer_track
from media import make_cover
from model import Cancel, Cancelled, write_atomic
from sources import manual_alignment, artwork_source
from ui import ACCENT, BG, FONT, HOVER, INK, LINE, MUTED, TINT, WHITE, button, card, label, tree


class LookupPanel(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.items, self.tracks, self.keys = [], [], []
        self.candidates, self.row_keys = {}, []
        self.cover_cache = {}
        self.tag_pick, self.cover_pick = None, None
        self.generation, self.search_busy, self.dirty = 0, False, False
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="art-preview")
        self.cover_cancel, self.cover_future = Cancel(), None
        self.artist, self.album = tk.StringVar(), tk.StringVar()
        self.provider = tk.StringVar(value="全部启用来源")
        self.context_title = tk.StringVar(value="先在曲库中选择专辑，也可直接输入名称检索。")
        self.count = tk.StringVar(value="发行版本")
        self.message = tk.StringVar(value="检索后，可分别选用标签与封面。")
        self.preview_title = tk.StringVar(value="选择一个发行版本")
        self.preview_source = tk.StringVar(value="比较原资料，确认适合的版本。")
        self.cover_status = tk.StringVar(value="")
        self.tag_caption = tk.StringVar(value="标签：自动匹配")
        self.cover_caption = tk.StringVar(value="封面：本地优先 / 自动匹配")
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)
        context = ctk.CTkFrame(self, fg_color="transparent")
        context.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 13))
        label(context, variable=self.context_title, size=13, color=color('#817994'), wraplength=820, justify="left").pack(side="left")
        button(context, "选择专辑", lambda:self.app.show_page("library"), width=95).pack(side="right")
        query = card(self)
        query.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 15))
        query.grid_columnconfigure(1, weight=1)
        for col, title in enumerate(("艺术家", "专辑名称", "来源")):
            label(query, title, size=11, color=MUTED).grid(row=0, column=col, sticky="w", padx=(18, 10), pady=(14, 5))
        self.artist_entry = ctk.CTkEntry(query, textvariable=self.artist, width=190, height=36, corner_radius=8, fg_color=color('#F7F6FB'), border_width=0, font=(FONT,13))
        self.artist_entry.grid(row=1,column=0,sticky="ew",padx=(18,10),pady=(0,16))
        self.album_entry = ctk.CTkEntry(query, textvariable=self.album, height=36, corner_radius=8, fg_color=color('#F7F6FB'), border_width=0, font=(FONT,13))
        self.album_entry.grid(row=1,column=1,sticky="ew",padx=(0,10),pady=(0,16))
        self.provider_menu=ctk.CTkOptionMenu(query,variable=self.provider,values=["全部启用来源","MusicBrainz","Apple iTunes"],width=154,height=36,
                                           fg_color=color('#F1EFF9'),button_color=color('#E9E4F7'),button_hover_color=color('#DED6F1'),text_color=color('#73668E'),font=(FONT,12))
        self.provider_menu.grid(row=1,column=2,padx=(0,12),pady=(0,16))
        self.search_button=button(query,"搜索资料",self.search,primary=True,width=108)
        self.search_button.grid(row=1,column=3,padx=(0,18),pady=(0,16))
        self.artist.trace_add("write",lambda *a:self.refresh_buttons())
        self.album.trace_add("write",lambda *a:self.refresh_buttons())

        listing=card(self)
        listing.grid(row=2,column=0,sticky="nsew",padx=(0,15))
        listing.grid_columnconfigure(0,weight=1);listing.grid_rowconfigure(1,weight=1)
        label(listing,variable=self.count,size=14,bold=True).grid(row=0,column=0,sticky="w",padx=20,pady=(17,13))
        holder=ctk.CTkFrame(listing,fg_color=WHITE,corner_radius=0)
        holder.grid(row=1,column=0,sticky="nsew",padx=12)
        self.tree=tree(holder,[("source","来源",105),("album","发行版本",210),("date","年份",65),("format","格式 / 地区",110),("match","曲目对应",75),("picked","选用",75)],self.app.scale)
        self.tree.bind("<<TreeviewSelect>>",lambda e:self._select())
        label(listing,variable=self.message,size=11,color=MUTED,wraplength=530,justify="left").grid(row=2,column=0,sticky="ew",padx=20,pady=(10,15))

        preview=card(self,width=360)
        preview.grid(row=2,column=1,sticky="ns");preview.grid_propagate(False)
        preview.grid_columnconfigure(0,weight=1);preview.grid_rowconfigure(0,weight=1)
        content=ctk.CTkScrollableFrame(preview,fg_color=WHITE,corner_radius=0,scrollbar_button_color=color('#D1CFDF'))
        content.grid(row=0,column=0,sticky="nsew",padx=12,pady=(12,0));content.grid_columnconfigure(0,weight=1)
        hero=ctk.CTkFrame(content,fg_color="transparent")
        hero.grid(row=0,column=0,padx=8,pady=(12,12),sticky="ew");hero.grid_columnconfigure(1,weight=1)
        self.empty_photo=ctk.CTkImage(light_image=Image.new('RGB',(106,106),resolved(color('#F8F6FD'),'light')),dark_image=Image.new('RGB',(106,106),resolved(color('#F8F6FD'),'dark')),size=(106,106))
        self.preview_photo=self.empty_photo
        self.art=ctk.CTkLabel(hero,text="暂无预览",image=self.empty_photo,width=106,height=106,text_color=color('#B0A6C8'),font=(FONT,11),fg_color=color('#F8F6FD'),corner_radius=10,wraplength=100,compound='center')
        self.art.grid(row=0,column=0,rowspan=2,padx=(0,12),sticky="n")
        label(hero,variable=self.preview_title,size=14,bold=True,wraplength=150,height=54,justify="left").grid(row=0,column=1,sticky="sw")
        label(hero,variable=self.preview_source,size=11,color=MUTED,wraplength=150,height=40,justify="left").grid(row=1,column=1,pady=(6,0),sticky="nw")
        self.detail_tab=ctk.CTkSegmentedButton(content,values=["发行资料","曲目对照"],command=lambda value:self._render_details(),
                                               selected_color=TINT,selected_hover_color=color('#E2DAF6'),unselected_color=color('#F7F5FB'),unselected_hover_color=color('#E8E1F7'),text_color=color('#655580'),font=(FONT,11),height=28)
        self.detail_tab.grid(row=1,column=0,padx=8,pady=(0,8),sticky="ew");self.detail_tab.set("发行资料")
        self.details=ctk.CTkTextbox(content,fg_color=WHITE,text_color=color('#81768F'),font=(FONT,12),wrap="word",height=160)
        self.details.grid(row=2,column=0,sticky="ew",padx=4);self.details.configure(state="disabled")
        label(content,variable=self.cover_status,size=10,color=color('#A297B2'),wraplength=290,justify="left").grid(row=3,column=0,sticky="ew",padx=8,pady=(6,10))
        actions=ctk.CTkFrame(preview,fg_color="transparent")
        actions.grid(row=1,column=0,sticky="ew",padx=20,pady=(10,18));actions.grid_columnconfigure((0,1),weight=1)
        self.tag_button=button(actions,"选用此标签",self.pick_tags,width=120)
        self.tag_button.grid(row=0,column=0,sticky="ew",padx=(0,5))
        self.cover_button=button(actions,"选用此封面",self.pick_cover,width=120)
        self.cover_button.grid(row=0,column=1,sticky="ew",padx=(5,0))
        self.both_button=button(actions,"同时选用标签与封面",self.pick_both,primary=True,width=250)
        self.both_button.grid(row=1,column=0,columnspan=2,sticky="ew",pady=(9,0))

        choice=card(self)
        choice.grid(row=3,column=0,columnspan=2,sticky="ew",pady=(15,0));choice.grid_columnconfigure(0,weight=1)
        label(choice,variable=self.tag_caption,size=12,color=color('#74688C'),wraplength=670).grid(row=0,column=0,sticky="w",padx=20,pady=(14,4))
        label(choice,variable=self.cover_caption,size=12,color=color('#74688C'),wraplength=670).grid(row=1,column=0,sticky="w",padx=20,pady=(0,14))
        self.clear_button=button(choice,"清除手选",self.clear_choices,width=88)
        self.clear_button.grid(row=0,column=1,rowspan=2,padx=(8,10))
        self.apply_button=button(choice,"应用到预览",self.apply,primary=True,width=126)
        self.apply_button.grid(row=0,column=2,rowspan=2,padx=(0,20))
        self.refresh_buttons()

    def close(self):
        self.cover_cancel.stop()
        if self.cover_future:self.cover_future.cancel()
        self.executor.shutdown(wait=False,cancel_futures=True)

    def set_context(self,items):
        keys=list(dict.fromkeys(infer_track(i).edit_key for i in items))
        if keys==self.keys and items:
            return
        if self.search_busy:
            self.app.cancel.stop()
        self.generation+=1;self.cover_cancel.stop();self.search_busy=False
        self.items=list(items);self.keys=keys
        self.tracks=[]
        for item in items:
            if item.profile and not item.error:
                track=infer_track(item)
                track.tags.update(self.app.overrides.get(track.edit_key,{}))
                self.tracks.append(track)
        self.candidates.clear();self.row_keys=[];self.tree.delete(*self.tree.get_children())
        self.cover_cache.clear();self._reset_preview()
        if items:
            track=infer_track(items[0]);tags=self.app.effective_tags(items[0])
            self.artist.set(tags.get('albumartist',tags.get('artist','')))
            self.album.set(tags.get('album',''))
            self.context_title.set(f"{tags.get('albumartist','')}  /  {tags.get('album','')}    ·    {len(self.tracks)} 条可比较音轨")
            selected=next((self.app.selections[k] for k in keys if k in self.app.selections),{})
            self.tag_pick=copy.deepcopy(selected.get('metadata'))
            self.cover_pick=copy.deepcopy(selected.get('cover'))
        else:
            self.tag_pick,self.cover_pick=None,None
        self.dirty=False;self.count.set("发行版本");self.message.set("可修改检索词，比较同一专辑的不同发行。")
        self._captions();self.refresh_buttons()

    def _reset_preview(self):
        self.preview_title.set("选择一个发行版本");self.preview_source.set("比较原资料，确认适合的版本。")
        self._set_art(None,"暂无预览");self.cover_status.set("")
        self.details.configure(state="normal");self.details.delete("1.0","end");self.details.configure(state="disabled")

    def search(self):
        if self.app.busy:return
        try:settings=self.app._settings_value()
        except Exception as exc:self.message.set(str(exc));return
        artist,album=self.artist.get().strip(),self.album.get().strip()
        provider={"MusicBrainz":("musicbrainz",),"Apple iTunes":("itunes",)}.get(self.provider.get())
        self.generation+=1;generation=self.generation;self.cover_cancel.stop()
        self.candidates.clear();self.row_keys=[];self.tree.delete(*self.tree.get_children());self._reset_preview()
        self.search_busy=True;self.message.set("正在从启用的来源查找发行…");self.count.set("检索发行版本")
        tracks=list(self.tracks)
        def perform():
            http=HTTP()
            def emit(kind,value):self.app._emit("lookup_event",(generation,kind,value))
            try:
                result=Catalog(http,settings,self.app.cancel,emit).search_candidates(artist,album,tracks,provider)
                self.app._emit("lookup_event",(generation,"lookup_done",result))
            finally:
                http.close()
        self.app._start(perform,"正在比较在线发行资料…")

    def event(self,generation,kind,value):
        if generation!=self.generation:return
        if kind=="lookup_progress":self.message.set(str(value)[:220])
        elif kind=="candidate":
            self.candidates[value['key']]=value;self._insert(value)
            self.count.set(f"{len(self.candidates)} 个发行版本")
            if not self.tree.selection():
                self.tree.selection_set(value['key']);self._select()
        elif kind=="lookup_done":
            self.search_busy=False
            selected=self.current_key()
            self.tree.delete(*self.tree.get_children())
            for candidate in value['candidates']:self._insert(candidate)
            if selected in self.candidates:self.tree.selection_set(selected)
            elif self.candidates:self.tree.selection_set(value['candidates'][0]['key'])
            self.count.set(f"{len(self.candidates)} 个发行版本")
            error="；".join(value.get('errors',[]))
            self.message.set((f"{len(self.candidates)} 个版本。分别选用标签与封面，再应用到预览。" if self.candidates else "没有找到发行。可简化名称、切换地区或检查数据源连接。")+("  "+error[:180] if error else ""))
            self.app.status.set(f"资料查询完成 · {len(self.candidates)} 个发行版本")
            self.app.progress_text.set("可分别选择标签与封面来源，应用到预览后整理。")
            self.app.progress.configure(value=100)
            self._select()
        self.refresh_buttons()

    def _insert(self,row):
        r=row['release'];key=row['key']
        if self.tree.exists(key):self.tree.delete(key)
        matched=f"{row['matched']}/{row['local_tracks']}" if row['local_tracks'] else "—"
        picked=[]
        if self.tag_pick and self._release_key(self.tag_pick)==key:picked.append("标签")
        if self.cover_pick and self.cover_pick.get('release_key')==key:picked.append("封面")
        self.tree.insert("","end",iid=key,values=(SOURCES[row['provider']]['name'],r.get('album',''),r.get('date','')[:4],
                                                    (r.get('format','')+" · "+r.get('country','')).strip(' ·'),matched," / ".join(picked)),
                         tags=("stripe",) if len(self.tree.get_children())%2 else ())

    @staticmethod
    def _release_key(release):
        return f"{release.get('provider','')}:{release.get('id','')}:{release.get('country','')}"

    def current_key(self):
        values=self.tree.selection();return values[0] if values else None

    def current(self):return self.candidates.get(self.current_key())

    def _select(self):
        if self.app.closing:return
        row=self.current()
        if not row:return
        r=row['release'];key=row['key']
        self.preview_title.set(r.get('album',''))
        self.preview_source.set("  ·  ".join(v for v in (SOURCES[row['provider']]['name'],r.get('country',''),r.get('format','')) if v))
        self._render_details()
        if self.cover_future and not self.cover_future.done() and getattr(self,'active_cover',None)==(self.generation,key):
            self.refresh_buttons();return
        self.cover_cancel.stop()
        if self.cover_future:self.cover_future.cancel()
        self.cover_cancel=Cancel()
        if key in self.cover_cache:
            self._display_cover(key,self.cover_cache[key])
        elif r.get('cover') and r.get('cover_provider') in self.app._settings_value().cover_sources:
            self._set_art(None,"正在读取封面…")
            self.cover_status.set("通过发行来源下载并验证图片。")
            generation,cancel,url=self.generation,self.cover_cancel,r['cover']
            self.active_cover=(generation,key)
            def work():
                http=None
                try:
                    http=HTTP()
                    data=http.fetch(url,cancel)
                    if not data:raise ValueError("此发行暂未提供可下载封面")
                    cover=make_cover(data,artwork_source(r))
                    self.app._emit("lookup_cover",(generation,key,cover,""))
                except Cancelled:pass
                except Exception as exc:self.app._emit("lookup_cover",(generation,key,None,str(exc)[:220]))
                finally:
                    if http:http.close()
            self.cover_future=self.executor.submit(work)
        else:
            self._set_art(None,"此发行没有可用封面" if not r.get('cover') else "此封面来源未启用")
            self.cover_status.set("可选用标签，或从另一个版本选用封面。")
        self.refresh_buttons()

    def cover_event(self,generation,key,cover,error):
        if generation!=self.generation:return
        if cover:self.cover_cache[key]=cover
        if key==self.current_key():
            if cover:self._display_cover(key,cover)
            else:
                self._set_art(None,"暂时无法读取封面")
                self.cover_status.set(error)
        self.refresh_buttons()

    def _display_cover(self,key,cover):
        image=Image.open(io.BytesIO(cover.data));image.thumbnail((106,106),Image.Resampling.LANCZOS)
        photo=ctk.CTkImage(light_image=image,dark_image=image,size=image.size)
        self._set_art(photo,"")
        self.cover_status.set(f"{cover.width} × {cover.height}  ·  {len(cover.data)/1024:.0f} KB  ·  可内嵌音轨")

    def _set_art(self,photo,text):
        # Keep the displayed Tcl image alive until the label has switched to its replacement.
        photo=photo or self.empty_photo
        self.art.configure(image=photo,text=text)
        self.preview_photo=photo

    def _render_details(self):
        row=self.current()
        if not row:return
        r=row['release'];lines=[]
        if self.detail_tab.get()=="曲目对照":
            mapping=manual_alignment(self.tracks,r)
            if self.tracks:
                for index,track in enumerate(self.tracks):
                    song=mapping.get(index)
                    lines.append(f"{track.tags.get('title','')}\n  → {song['title'] if song else '未对应，保留原曲名与轨序'}")
            else:
                lines=[f"{s['disc']:02}-{s['track']:02}  {s['title']}  ({int(s.get('seconds',0))//60}:{int(s.get('seconds',0))%60:02})" for s in r.get('songs',[])]
        else:
            local=self.app.effective_tags(self.items[0]) if self.items else {}
            for key,title in (("album","专辑名称"),("albumartist","专辑艺术家"),("date","发行日期"),("label","厂牌"),("catalognumber","目录号")):
                before,after=local.get(key,"—"),r.get(key) or "—"
                lines.append(f"{title}   {after}"+(f"\n  当前：{before}" if before!=after else ""))
            lines.append(f"曲目数   {len(r.get('songs',[]))}  ·  可对应 {row['matched']}/{row['local_tracks']}" if row['local_tracks'] else f"曲目数   {len(r.get('songs',[]))}")
        self.details.configure(state="normal");self.details.delete("1.0","end");self.details.insert("1.0","\n\n".join(lines));self.details.configure(state="disabled")

    def pick_tags(self):
        row=self.current()
        if not row or row['provider'] not in self.app._settings_value().tag_sources:return
        self.tag_pick=copy.deepcopy(row['release']);self.dirty=True;self._choices_changed()

    def pick_cover(self):
        row=self.current()
        if not row or row['key'] not in self.cover_cache or row.get('cover_provider') not in self.app._settings_value().cover_sources:return
        cover=self.cover_cache[row['key']]
        path=state_dir()/"Selected Covers"/(hashlib.sha256(cover.data).hexdigest()+(".jpg" if cover.mime=="image/jpeg" else ".png"))
        write_atomic(path,cover.data)
        r=row['release']
        self.cover_pick=dict(path=str(path),source=cover.source,url=r.get('cover',''),provider=row['cover_provider'],release_key=row['key'],
                             edition={k:r.get(k,'') for k in ('album','albumartist','date','country','format','id','provider')})
        self.dirty=True;self._choices_changed()

    def pick_both(self):self.pick_tags();self.pick_cover()

    def _choices_changed(self):
        selected=self.current_key()
        for row in self.candidates.values():self._insert(row)
        if selected and self.tree.exists(selected):self.tree.selection_set(selected)
        self._captions();self.refresh_buttons()

    def _captions(self):
        if self.tag_pick:
            r=self.tag_pick;name=SOURCES.get(r.get('provider'),{}).get('name','手选资料')
            self.tag_caption.set(f"标签：{name}  ·  {r.get('date','')}  ·  {r.get('album','')}")
        else:self.tag_caption.set("标签：自动匹配")
        if self.cover_pick:
            r=self.cover_pick.get('edition',{});name=SOURCES.get(self.cover_pick.get('provider'),{}).get('name','手选封面')
            self.cover_caption.set(f"封面：{name}  ·  {r.get('date','')}  ·  {r.get('album','')}")
        else:self.cover_caption.set("封面：本地优先 / 自动匹配")

    def clear_choices(self):
        self.tag_pick,self.cover_pick=None,None;self.dirty=True;self._choices_changed()

    def apply(self):
        if not self.items or self.app.busy:return
        chosen={}
        if self.tag_pick:chosen['metadata']=copy.deepcopy(self.tag_pick)
        if self.cover_pick:chosen['cover']=copy.deepcopy(self.cover_pick)
        for key in self.keys:
            old=self.app.selections.get(key,{})
            if not self.cover_pick and self.app.cover_overrides.get(key)==old.get('cover',{}).get('path'):
                self.app.cover_overrides.pop(key,None)
            if chosen:self.app.selections[key]=copy.deepcopy(chosen)
            else:self.app.selections.pop(key,None)
            if self.tag_pick:self.app.overrides.pop(key,None)
        if self.tag_pick:
            from dataclasses import replace
            members={i.rel for i in self.items}
            self.app.items=[replace(i,edits={}) if i.rel in members else i for i in self.app.items]
        self.app._save_profile();self.app._show_items()
        index=next((n for n,i in enumerate(self.app.items) if i.rel==self.items[0].rel),None)
        if index is not None and self.app.preview.exists(str(index)):
            self.app.preview.selection_set(str(index));self.app._selection()
        self.app.status.set("所选标签与封面已加入预览，整理时应用到此专辑。")
        self.message.set("已保存选择。可继续比较，或返回曲库开始整理。")
        self.dirty=False;self.refresh_buttons()

    def refresh_buttons(self):
        if not hasattr(self,'search_button'):return
        busy=self.app.busy
        for w in (self.artist_entry,self.album_entry,self.provider_menu):w.configure(state="disabled" if busy else "normal")
        self.search_button.configure(state="normal" if not busy and self.artist.get().strip() and self.album.get().strip() else "disabled")
        row=self.current() if hasattr(self,'tree') else None
        try:settings=self.app._settings_value()
        except Exception:settings=None
        if settings:
            enabled=set(settings.tag_sources)
            if 'coverartarchive' in settings.cover_sources:enabled.add('musicbrainz')
            if 'itunes' in settings.cover_sources:enabled.add('itunes')
            values=['全部启用来源']+[SOURCES[k]['name'] for k in ('musicbrainz','itunes') if k in enabled]
            self.provider_menu.configure(values=values)
            if self.provider.get() not in values:self.provider.set('全部启用来源')
            if not enabled:self.search_button.configure(state='disabled')
        tag=bool(row and settings and row['provider'] in settings.tag_sources and not busy)
        cover=bool(row and settings and row.get('cover_provider') in settings.cover_sources and row['key'] in self.cover_cache and not busy)
        if hasattr(self,'tag_button'):
            self.tag_button.configure(state="normal" if tag else "disabled")
            self.cover_button.configure(state="normal" if cover else "disabled")
            self.both_button.configure(state="normal" if tag and cover else "disabled")
            self.apply_button.configure(state="normal" if not busy and self.items and self.dirty else "disabled")
            self.clear_button.configure(state="normal" if not busy and (self.tag_pick or self.cover_pick) else "disabled")
