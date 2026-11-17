"""Quiet light-theme desktop workspace, rendered with native Tk + CustomTkinter."""
from i18n import tr
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk
from theme import color, resolved
from PIL import Image, ImageDraw, ImageTk

from catalog import SOURCES
from model import VERSION

BG = color('#F5F6FA')
WHITE = color('#FFFFFF')
INK = color('#202338')
MUTED = color('#85899A')
LINE = color('#E8EAF1')
ACCENT = color('#6556DC')
HOVER = color('#5545C8')
TINT = color('#EEEBFC')
GREEN = color('#2A8C71')
from i18n import get_language
FONT = "Segoe UI" if get_language()=="en" else "Microsoft YaHei UI"


def label(master, text=None, variable=None, size=14, bold=False, color=INK, **kwargs):
    kwargs.setdefault('height',max(18,round(size*1.5)))
    return ctk.CTkLabel(master, text=text or "", textvariable=variable, font=(FONT, size, "bold" if bold else "normal"),
                        text_color=color, anchor="w", **kwargs)


def card(master, **kwargs):
    kwargs.setdefault("bg_color",BG)
    return ctk.CTkFrame(master, fg_color=WHITE, corner_radius=16, border_width=1, border_color=LINE, **kwargs)


class ActionButton(ctk.CTkButton):
    def __init__(self,*args,primary=False,**kwargs):
        self._normal_fg=kwargs.get('fg_color',ACCENT)
        self._disabled_fg=color('#E5E0F6') if primary else color('#F5F3FA')
        if kwargs.get('state')=='disabled':kwargs['fg_color']=self._disabled_fg
        kwargs['text_color_disabled']=color('#AEA4C2')
        super().__init__(*args,**kwargs)

    def configure(self,**kwargs):
        if 'state' in kwargs:
            kwargs['fg_color']=self._disabled_fg if kwargs['state']=='disabled' else self._normal_fg
        return super().configure(**kwargs)


def button(master, text, command, primary=False, width=120, **kwargs):
    return ActionButton(master, primary=primary,text=text, command=command, width=width, height=38, corner_radius=9,
                         fg_color=ACCENT if primary else color('#F3F2FA'), hover_color=HOVER if primary else color('#E9E6F8'),
                         text_color=("#FFFFFF","#171A23") if primary else color('#5E587C'), font=(FONT, 13), **kwargs)


def tree(master, columns, scale):
    host = ctk.CTkFrame(master, fg_color=WHITE, corner_radius=0)
    host.pack(fill="both", expand=True)
    host.rowconfigure(0, weight=1)
    host.columnconfigure(0, weight=1)
    view = ttk.Treeview(host, columns=[c[0] for c in columns], show="headings", selectmode="browse")
    for key, title, width in columns:
        view.heading(key, text=title)
        view.column(key, width=round(width*scale), minwidth=round(45*scale), stretch=True)
    scroll = ctk.CTkScrollbar(host, command=view.yview, button_color=color('#D1CFDF'), button_hover_color=color('#B3AEC9'), width=11)
    horizontal = ctk.CTkScrollbar(host, orientation="horizontal", command=view.xview, button_color=color('#D1CFDF'), height=11)
    view.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
    view.grid(row=0, column=0, sticky="nsew")
    scroll.grid(row=0, column=1, sticky="ns", padx=(3, 0))
    horizontal.grid(row=1, column=0, sticky="ew")
    view.tag_configure("stripe", background=resolved(color('#FAFAFD')))
    return view


class NotebookBridge:
    def __init__(self, app):
        self.app = app

    def select(self, index):
        self.app.show_page({0:"library", 1:"activity", 2:"activity", 3:"settings"}[index])
        if index in (1, 2):
            self.app.activity_tabs.set(tr('整理结果') if index == 1 else tr('运行日志'))


def styles(app):
    style = ttk.Style(app)
    style.theme_use("clam")
    style.configure(".", font=(FONT, 10), background=resolved(BG), foreground=resolved(INK))
    style.configure("TFrame", background=resolved(BG))
    style.configure("TLabel", background=resolved(BG))
    style.configure("Muted.TLabel", foreground=resolved(MUTED))
    style.configure("Treeview", font=(FONT, 10), rowheight=round(38*app.scale), background=resolved(WHITE), fieldbackground=resolved(WHITE),foreground=resolved(INK),
                    borderwidth=0, relief="flat", lightcolor=resolved(WHITE), darkcolor=resolved(WHITE),bordercolor=resolved(WHITE))
    style.configure("Treeview.Heading", font=(FONT, 9), background=resolved(color('#F7F7FB')), foreground=resolved(color('#88859C')), borderwidth=0,
                    relief="flat", padding=(round(10*app.scale), round(10*app.scale)))
    style.map("Treeview", background=[("selected",resolved(TINT))], foreground=[("selected",resolved(color('#4F439C')))])
    style.map("Treeview.Heading", background=[("active",resolved(color('#F1EFFA')))])
    style.configure("Horizontal.TProgressbar", background=resolved(ACCENT), troughcolor=resolved(color('#EEEDF5')), borderwidth=0,
                    lightcolor=resolved(ACCENT), darkcolor=resolved(ACCENT))
    # Legacy modal controls retain the same palette while their workflows remain compatible.
    style.configure("TButton", padding=(12, 7), background=resolved(TINT), foreground=resolved(INK), borderwidth=0)
    style.configure("Primary.TButton", background=resolved(ACCENT), foreground="#FFFFFF")
    style.map("Primary.TButton", background=[("active",resolved(HOVER))])
    style.configure("TEntry", fieldbackground=resolved(WHITE), padding=(5, 5))


def placeholder(app):
    size = round(148*app.scale)
    im = Image.new("RGB", (size, size), resolved(color('#F4F2FC')))
    draw = ImageDraw.Draw(im)
    p = size/184
    def bounds(box):return tuple(round(x*p) for x in box)
    draw.ellipse(bounds((29,29,155,155)), fill=resolved(color('#DED9F4')))
    draw.ellipse(bounds((45,45,139,139)), fill=resolved(color('#F1EEFB')), outline=resolved(color('#C6BEEB')), width=max(1,round(p)))
    draw.ellipse(bounds((64,64,120,120)), fill=resolved(color('#D7D0F0')))
    draw.ellipse(bounds((81,81,103,103)), fill=resolved(WHITE))
    draw.ellipse(bounds((89,89,95,95)), fill=resolved(color('#B9ACDF')))
    return ImageTk.PhotoImage(im)


def build(app, help_text):
    app.configure(fg_color=BG)
    app.grid_columnconfigure(1, weight=1)
    app.grid_rowconfigure(0, weight=1)
    app.nav = {}
    sidebar = ctk.CTkFrame(app, width=192, corner_radius=0, fg_color=WHITE)
    sidebar.grid(row=0, column=0, sticky="nsew")
    sidebar.grid_propagate(False)
    brand = ctk.CTkFrame(sidebar, fg_color="transparent")
    brand.pack(fill="x", padx=24, pady=(32, 33))
    logo = ctk.CTkFrame(brand, width=38, height=38, corner_radius=12, fg_color=ACCENT)
    logo.pack(side="left", padx=(0, 10));logo.pack_propagate(False)
    ctk.CTkLabel(logo, text="♪", font=("Segoe UI", 27), text_color=("#FFFFFF","#171A23")).pack(expand=True)
    label(brand, "Music\nOrganizer", size=16, bold=True, justify="left").pack(side="left")
    label(sidebar, "WORKSPACE", size=10, color=color('#B0ADBF')).pack(anchor="w", padx=28, pady=(0, 10))
    entries = [("library", "▤", tr('曲库整理')), ("online", "⌕", tr('在线资料')), ("sources", "◇", tr('数据源')),
               ("activity", "≡", tr('运行记录')), ("settings", "⚙", tr('高级设置'))]
    for key, icon, title in entries:
        nav = ctk.CTkButton(sidebar, text=f"{icon}     {title}", anchor="w", width=152, height=43, corner_radius=10,
                            fg_color="transparent", hover_color=color('#F4F2FB'), text_color=color('#838096'), font=(FONT,14),
                            command=lambda k=key: app.show_page(k))
        nav.pack(fill="x", padx=18, pady=4)
        app.nav[key] = nav
    bottom = ctk.CTkFrame(sidebar, fg_color=color('#F8F7FC'), corner_radius=12)
    bottom.pack(side="bottom", fill="x", padx=20, pady=22)
    label(bottom, tr('本地曲库，悉心归档'), size=11, color=color('#928BA9')).pack(anchor="w", padx=12, pady=(13, 1))
    label(bottom, f"v{VERSION}  ·  FLAC / MP3 / AAC", size=10, color=color('#ABA5BA')).pack(anchor="w", padx=12, pady=(0, 12))

    body = ctk.CTkFrame(app, fg_color="transparent")
    body.grid(row=0, column=1, sticky="nsew", padx=28, pady=(27, 22))
    body.grid_columnconfigure(0, weight=1)
    body.grid_rowconfigure(1, weight=1)
    header = ctk.CTkFrame(body, fg_color="transparent")
    header.grid(row=0, column=0, sticky="ew", pady=(0, 23))
    app.page_title = tk.StringVar(value=tr('曲库整理'))
    app.page_description = tk.StringVar(value=tr('让每一张专辑，井然有序。'))
    label(header, variable=app.page_title, size=27, bold=True).pack(anchor="w")
    label(header, variable=app.page_description, size=13, color=MUTED).pack(anchor="w", pady=(5, 0))
    app.pages = {}
    holder = ctk.CTkFrame(body, fg_color="transparent")
    holder.grid(row=1, column=0, sticky="nsew")
    holder.rowconfigure(0, weight=1);holder.columnconfigure(0, weight=1)
    for key, _, _ in entries:
        page = ctk.CTkFrame(holder, fg_color="transparent")
        page.grid(row=0, column=0, sticky="nsew")
        app.pages[key] = page
    build_library(app, app.pages["library"])
    from lookup_ui import LookupPanel
    app.lookup_panel = LookupPanel(app.pages["online"], app)
    app.lookup_panel.pack(fill="both", expand=True)
    build_sources(app, app.pages["sources"])
    build_activity(app, app.pages["activity"])
    build_settings(app, app.pages["settings"], help_text)

    footer = card(body)
    footer.grid(row=2, column=0, sticky="ew", pady=(18, 0))
    footer.grid_columnconfigure(0, weight=1)
    line = ctk.CTkFrame(footer, fg_color="transparent")
    line.grid(row=0, column=0, sticky="ew", padx=20, pady=(13, 9))
    label(line, variable=app.progress_text, size=12, color=color('#716B86')).pack(side="left")
    app.source_summary = tk.StringVar(value=tr('2 个标签源 · 2 个封面源'))
    label(line, variable=app.source_summary, size=11, color=color('#9C95B0')).pack(side="right")
    app.progress = ttk.Progressbar(footer, mode="determinate", maximum=100)
    app.progress.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10), ipady=0)
    actions = ctk.CTkFrame(footer, fg_color="transparent")
    actions.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 16))
    actions.grid_columnconfigure(0, weight=1)
    label(actions, variable=app.status, size=11, color=MUTED, wraplength=450, justify="left").grid(row=0,column=0,sticky="w",padx=(0,10))
    app.scan_button = button(actions, tr('只读扫描'), app._scan, width=100)
    app.scan_button.grid(row=0,column=1,padx=(0,8))
    app.cancel_button = button(actions,tr('停止'),app._cancel,width=65,state="disabled")
    app.cancel_button.grid(row=0,column=2,padx=(0,8))
    app.run_button = button(actions,tr('开始整理  →'),app._run,primary=True,width=126,state="disabled")
    app.run_button.grid(row=0,column=3)
    app.notebook = NotebookBridge(app)
    app.show_page("library")


def build_library(app, page):
    page.grid_columnconfigure(0, weight=1)
    page.grid_columnconfigure(1, weight=0)
    page.grid_rowconfigure(2, weight=1)
    paths = card(page)
    paths.grid(row=0,column=0,columnspan=2,sticky="ew",pady=(0,16))
    paths.grid_columnconfigure(1,weight=1)
    for row,(title,var,action) in enumerate(((tr('音乐来源'),app.source,app._browse_source),(tr('整理目标'),app.dest,app._browse_dest))):
        row*=2
        label(paths,title,size=12,color=color('#91899F')).grid(row=row,column=0,padx=(20,15),pady=(16 if row==0 else 7, 7 if row==0 else 16),sticky="w")
        entry=ctk.CTkEntry(paths,textvariable=var,height=36,corner_radius=8,border_width=0,fg_color=color('#F7F7FB'),text_color=color('#625D78'),font=(FONT,12))
        entry.grid(row=row,column=1,sticky="ew",pady=(16 if row==0 else 7,7 if row==0 else 16))
        choose=button(paths,tr('选择目录'),action,width=94)
        choose.grid(row=row,column=2,padx=(10,20),pady=(16 if row==0 else 7,7 if row==0 else 16))
        if row==0:app.src_entry,app.src_button=entry,choose
        else:app.dst_entry,app.dst_button=entry,choose
    label(paths,variable=app.source_summary,size=11,color=MUTED).grid(row=1,column=1,sticky="w",pady=(0,6))
    app.sources_button=button(paths,tr('管理来源'),app._manage_sources,width=94)
    app.sources_button.grid(row=1,column=2,padx=(10,20),pady=(0,6))
    app.summary_files=tk.StringVar(value="—");app.summary_albums=tk.StringVar(value="—");app.summary_size=tk.StringVar(value="—")
    metrics=ctk.CTkFrame(page,fg_color="transparent")
    metrics.grid(row=1,column=0,columnspan=2,sticky="ew",pady=(0,16))
    for i,(var,title) in enumerate(((app.summary_files,tr('音频项目')),(app.summary_albums,tr('专辑分组')),(app.summary_size,tr('源文件大小')))):
        metric=ctk.CTkFrame(metrics,fg_color="transparent")
        metric.pack(side="left",padx=(4,48))
        label(metric,variable=var,size=23,bold=True).pack(side="left",padx=(0,10))
        label(metric,title,size=12,color=MUTED).pack(side="left",pady=(5,0))
    listing=card(page)
    listing.grid(row=2,column=0,sticky="nsew",padx=(0,16))
    listing.grid_columnconfigure(0,weight=1);listing.grid_rowconfigure(1,weight=1)
    top=ctk.CTkFrame(listing,fg_color="transparent")
    top.grid(row=0,column=0,sticky="ew",padx=20,pady=(17,13))
    label(top,tr('音乐文件'),size=15,bold=True).pack(side="left")
    ctk.CTkEntry(top,textvariable=app.filter,placeholder_text=tr('筛选曲名、艺术家或专辑'),width=220,height=33,corner_radius=8,
                 fg_color=color('#F7F7FB'),border_width=0,font=(FONT,12)).pack(side="right")
    label(top,tr('筛选'),size=11,color=MUTED).pack(side="right",padx=(0,10))
    box=ctk.CTkFrame(listing,fg_color=WHITE,corner_radius=0)
    box.grid(row=1,column=0,sticky="nsew",padx=14,pady=(0,12))
    app.preview=tree(box,[("title",tr('曲名 / 文件'),220),("artist",tr('艺术家'),140),("album",tr('专辑'),210),("format",tr('格式'),78),("cover",tr('封面'),55)],app.scale)
    app.preview.bind("<<TreeviewSelect>>",app._selection)
    app.preview.bind("<Double-1>",lambda e:app._edit())
    app.filter.trace_add("write",lambda *a:app._show_items())
    app.empty_state=ctk.CTkFrame(box,fg_color=WHITE)
    label(app.empty_state,tr('从一份音乐目录开始'),size=19,bold=True,color=color('#6C6587')).pack(pady=(0,10))
    label(app.empty_state,tr('扫描后，在这里浏览歌曲、版本与封面。'),size=12,color=color('#AAA4B9')).pack()
    app.empty_state.place(relx=.5,rely=.5,anchor="center")
    info=card(page,width=270)
    info.grid(row=2,column=1,sticky="ns");info.grid_propagate(False)
    info.grid_columnconfigure(0,weight=1);info.grid_rowconfigure(0,weight=1)
    content=ctk.CTkScrollableFrame(info,fg_color=WHITE,corner_radius=0,scrollbar_button_color=color('#D1CFDF'))
    content.grid(row=0,column=0,sticky="nsew",padx=10,pady=(12,0))
    app.placeholder_photo=placeholder(app)
    app.art_label=tk.Label(content,image=app.placeholder_photo,bg=resolved(WHITE),borderwidth=0)
    app.art_label.pack(pady=(8,13))
    app.inspector_title=tk.StringVar(value=tr('尚未选择音轨'))
    label(content,variable=app.inspector_title,size=16,bold=True,wraplength=220,justify="left").pack(anchor="w",padx=12)
    app.selection_sources=tk.StringVar(value=tr('选择一首歌，查看发行资料。'))
    label(content,variable=app.selection_sources,size=11,color=color('#A09AAF'),wraplength=220,justify="left").pack(anchor="w",padx=12,pady=(7,10))
    label(content,variable=app.detail,size=12,color=color('#858096'),wraplength=220,justify="left").pack(anchor="w",padx=12,pady=(0,10))
    actions=ctk.CTkFrame(info,fg_color="transparent")
    actions.grid(row=1,column=0,sticky="ew",padx=22,pady=(10,20));actions.grid_columnconfigure(0,weight=1)
    app.lookup_button=button(actions,tr('查找封面与标签'),app._open_lookup,primary=True,width=226)
    app.lookup_button.grid(row=0,column=0,pady=(0,10),sticky="ew")
    editrow=ctk.CTkFrame(actions,fg_color="transparent")
    editrow.grid(row=1,column=0,sticky="ew");editrow.grid_columnconfigure((0,1),weight=1)
    app.edit_button=button(editrow,tr('编辑标签'),app._edit,width=102)
    app.edit_button.grid(row=0,column=0,padx=(0,6),sticky="ew")
    app.cover_button=button(editrow,tr('更换封面'),app._cover_dialog,width=102)
    app.cover_button.grid(row=0,column=1,padx=(6,0),sticky="ew")


def build_sources(app,page):
    scroll=ctk.CTkScrollableFrame(page,fg_color="transparent",corner_radius=0)
    scroll.pack(fill="both",expand=True)
    scroll.grid_columnconfigure(0,weight=1)
    controls=card(scroll);controls.grid(row=0,column=0,sticky="ew",pady=(0,15))
    label(controls,tr('你信任的音乐资料'),size=17,bold=True).pack(anchor="w",padx=22,pady=(20,5))
    label(controls,tr('分别选择标签与封面来源，或前往在线资料逐张选用发行版本。'),size=12,color=MUTED).pack(anchor="w",padx=22)
    row=ctk.CTkFrame(controls,fg_color="transparent");row.pack(fill="x",padx=22,pady=(16,20))
    switch=ctk.CTkSwitch(row,text=tr('整理时自动联网'),variable=app.online,progress_color=ACCENT,font=(FONT,13))
    switch.pack(side="left");app.setting_widgets.append(switch)
    app.test_sources_button=button(row,tr('测试全部来源'),app._test_sources,primary=True,width=136)
    app.test_sources_button.pack(side="right")
    app.source_cards={}
    for i,(key,source) in enumerate(SOURCES.items(),1):
        panel=card(scroll);panel.grid(row=i,column=0,sticky="ew",pady=(0,12));panel.grid_columnconfigure(1,weight=1)
        icon=ctk.CTkFrame(panel,width=42,height=42,corner_radius=12,fg_color=TINT)
        icon.grid(row=0,column=0,rowspan=2,padx=(22,15),pady=22,sticky="n");icon.grid_propagate(False)
        label(icon,{"musicbrainz":"M","coverartarchive":"C","itunes":"A"}[key],size=19,bold=True,color=ACCENT).place(relx=.5,rely=.5,anchor="center")
        label(panel,source['name'],size=16,bold=True).grid(row=0,column=1,sticky="w",pady=(19,0))
        label(panel,source['description'],size=12,color=MUTED,wraplength=480,justify="left").grid(row=1,column=1,sticky="nw",pady=(2,10))
        roles=ctk.CTkFrame(panel,fg_color="transparent");roles.grid(row=0,column=2,rowspan=2,padx=20,pady=18,sticky="ne")
        for title,mapping in ((tr('标签'),app.tag_enabled),(tr('封面'),app.cover_enabled)):
            if key in mapping:
                w=ctk.CTkCheckBox(roles,text=title,variable=mapping[key],width=74,checkbox_width=18,checkbox_height=18,
                                  corner_radius=5,fg_color=ACCENT,hover_color=HOVER,border_color=color('#C8C2DB'),font=(FONT,12))
                w.pack(side="left",padx=(0,13));app.setting_widgets.append(w)
        status=label(panel,tr('未测试'),size=11,color=color('#9D96AE'),fg_color=color('#F3F1F8'),corner_radius=7,height=27)
        status.grid(row=2,column=1,sticky="w",pady=(0,17))
        detail=label(panel,tr('点击测试，检查实时接口与图片服务。'),size=11,color=color('#A19AAF'),wraplength=500,justify="left")
        detail.grid(row=3,column=1,sticky="w",pady=(0,17))
        action=button(panel,tr('测试连接'),lambda k=key:app._test_sources((k,)),width=102)
        action.grid(row=2,column=2,rowspan=2,padx=20,pady=(0,17),sticky="e")
        app.source_cards[key]=dict(status=status,detail=detail,button=action)
    priorities=card(scroll);priorities.grid(row=4,column=0,sticky="ew",pady=(3,12))
    label(priorities,tr('自动匹配的优先来源'),size=15,bold=True).pack(anchor="w",padx=22,pady=(18,14))
    row=ctk.CTkFrame(priorities,fg_color="transparent");row.pack(fill="x",padx=22,pady=(0,20))
    for title,var,values in ((tr('标签优先'),app.tag_priority,["MusicBrainz","Apple iTunes"]),(tr('封面优先'),app.cover_priority,["Cover Art Archive","Apple iTunes"])):
        label(row,title,size=12,color=MUTED).pack(side="left",padx=(0,10))
        w=ctk.CTkOptionMenu(row,variable=var,values=values,width=185,height=34,corner_radius=8,fg_color=color('#F2F0FA'),
                            button_color=color('#E9E5F7'),button_hover_color=color('#DED7F3'),text_color=color('#675E82'),font=(FONT,12))
        w.pack(side="left",padx=(0,24));app.setting_widgets.append(w)
    label(scroll,tr('本地标签与图片优先保留；手选的发行资料和封面会覆盖自动匹配结果。'),size=11,color=MUTED,wraplength=850,justify="left").grid(row=5,column=0,sticky="w",padx=4,pady=10)


def build_activity(app,page):
    panel=card(page);panel.pack(fill="both",expand=True)
    app.activity_tabs=ctk.CTkTabview(panel,fg_color=WHITE,corner_radius=12,segmented_button_selected_color=TINT,
                                    segmented_button_selected_hover_color=color('#E2DAF6'),segmented_button_unselected_color=color('#F8F7FC'),
                                    segmented_button_unselected_hover_color=color('#E8E3F7'),text_color=color('#766C94'),segmented_button_font=(FONT,13))
    app.activity_tabs.pack(fill="both",expand=True,padx=16,pady=12)
    results=app.activity_tabs.add(tr('整理结果'));logs=app.activity_tabs.add(tr('运行日志'))
    app.result_tree=tree(results,[("status",tr('状态'),75),("title",tr('曲名'),160),("album",tr('专辑'),170),("target",tr('目标路径'),330),
                                 ("issues",tr('提示'),210),("metadata",tr('标签来源'),180),("artwork",tr('封面来源'),180)],app.scale)
    app.result_tree.bind("<Double-1>",app._open_result)
    app.log=tk.Text(logs,wrap="word",bg=resolved(color('#FCFBFE')),fg=resolved(color('#777086')),font=("Consolas",10),relief="flat",state="disabled",highlightthickness=0)
    bar=ctk.CTkScrollbar(logs,command=app.log.yview,width=12);bar.pack(side="right",fill="y")
    app.log.configure(yscrollcommand=bar.set);app.log.pack(fill="both",expand=True)


def build_settings(app,page,help_text):
    from advanced_ui import AdvancedPanel
    app.advanced=AdvancedPanel(page,app,help_text)
    app.advanced.pack(fill="both",expand=True)


PAGE_COPY={
    "library":(tr('曲库整理'),tr('让每一张专辑，井然有序。')),
    "online":(tr('在线资料'),tr('比较发行版本，为标签与封面找到各自合适的来源。')),
    "sources":(tr('数据源'),tr('选择你信任的资料库，检查它们此刻的连接状态。')),
    "activity":(tr('运行记录'),tr('每一次整理，都有迹可循。')),
    "settings":(tr('高级设置'),tr('从外观到命名与转换，用直观规则定义你的曲库。')),
}


def show_page(app,key):
    app.current_page=key
    app.pages[key].tkraise()
    for name,nav in app.nav.items():
        nav.configure(fg_color=TINT if name==key else "transparent",text_color=ACCENT if name==key else color('#838096'))
    title,description=PAGE_COPY[key];app.page_title.set(title);app.page_description.set(description)
    if key=="online":app.lookup_panel.refresh_buttons()
