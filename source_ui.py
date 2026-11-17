"""A staged source list; changing it invalidates the read-only scan."""
from pathlib import Path
from tkinter import filedialog,messagebox

import customtkinter as ctk

from dialogs import center
from i18n import tr
from model import component,source_roots
from ui import BG,WHITE,MUTED,button,label,tree


class SourceManager(ctk.CTkToplevel):
    def __init__(self,app):
        super().__init__(app)
        self.app=app
        self.paths=list(app._source_paths())
        self.title(tr('多个源文件夹'))
        self.geometry("820x520");self.minsize(700,460)
        self.configure(fg_color=BG);self.transient(app);self.grab_set()
        label(self,tr('把多个来源整理成一个曲库'),size=22,bold=True).pack(anchor="w",padx=26,pady=(24,8))
        label(self,tr('可添加不同磁盘的文件夹。相同音频跨来源去重，不同版本仍会保留；列表上方的来源先处理。'),
              size=12,color=MUTED,wraplength=740,justify="left").pack(anchor="w",padx=26,pady=(0,16))
        box=ctk.CTkFrame(self,fg_color=WHITE,corner_radius=12)
        box.pack(fill="both",expand=True,padx=24,pady=(0,14))
        self.listing=tree(box,[("path",tr('源文件夹'),690)],app.scale)
        actions=ctk.CTkFrame(self,fg_color="transparent");actions.pack(fill="x",padx=24,pady=(0,14))
        for title,command in ((tr('添加文件夹'),self.browse),(tr('移除'),self.remove),(tr('上移'),lambda:self.move(-1)),(tr('下移'),lambda:self.move(1))):
            button(actions,title,command,width=110).pack(side="left",padx=(0,8))
        footer=ctk.CTkFrame(self,fg_color="transparent");footer.pack(fill="x",padx=24,pady=(0,22))
        button(footer,tr('应用来源列表'),self.apply,primary=True,width=150).pack(side="right")
        button(footer,tr('取消'),self.destroy,width=90).pack(side="right",padx=10)
        self.refresh();center(app,self)

    def refresh(self,selected=None):
        self.listing.delete(*self.listing.get_children())
        for i,path in enumerate(self.paths):self.listing.insert("", "end",iid=str(i),values=(path,))
        if selected is not None and self.paths:
            key=str(min(selected,len(self.paths)-1));self.listing.selection_set(key);self.listing.see(key)

    def add_path(self,path):
        roots=source_roots([*self.paths,path])
        self.paths=[str(p) for p in roots]
        self.refresh(len(self.paths)-1)

    def browse(self):
        path=filedialog.askdirectory(parent=self,title=tr('添加音乐源文件夹'))
        if path:
            try:self.add_path(path)
            except (ValueError,OSError) as exc:messagebox.showerror(tr('无法添加来源'),str(exc),parent=self)

    def remove(self):
        selected=self.listing.selection()
        if selected:
            i=int(selected[0]);self.paths.pop(i);self.refresh(i)

    def move(self,step):
        selected=self.listing.selection()
        if selected:
            i=int(selected[0]);j=i+step
            if 0<=j<len(self.paths):
                self.paths[i],self.paths[j]=self.paths[j],self.paths[i];self.refresh(j)

    def apply(self):
        try:paths=[str(p) for p in source_roots(self.paths)]
        except (ValueError,OSError) as exc:
            messagebox.showerror(tr('无法应用来源'),str(exc),parent=self);return
        app=self.app
        if paths!=app._source_paths():
            if app.items:app._save_profile()
            app.source.set(paths[0]);app.extra_sources=paths[1:]
            if not app.dest.get():
                first=Path(paths[0]);app.dest.set(str(first.with_name(component(first.name+"_Organized",70))))
            app.items,app.scanned_source=[],None
            app.overrides,app.cover_overrides,app.selections={},{},{}
            app._update_source_count();app.run_button.configure(state="disabled");app._show_items();app._save()
            app.status.set(tr('来源已更新，请重新只读扫描'))
        self.destroy()


def manage_sources(app):
    SourceManager(app)
