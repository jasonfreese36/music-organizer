import dataclasses
import hashlib
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
import urllib.parse
import webbrowser

import customtkinter as ctk
from theme import color, resolved

from catalog import HTTP, state_dir
from inventory import infer_track
from media import make_cover
from model import number, write_atomic
from ui import BG, WHITE, INK, MUTED, LINE, ACCENT, FONT, button, label


def center(app,dialog):
    dialog.update_idletasks()
    x=app.winfo_rootx()+max(0,(app.winfo_width()-dialog.winfo_width())//2)
    y=app.winfo_rooty()+max(0,(app.winfo_height()-dialog.winfo_height())//2)
    dialog.geometry(f"+{x}+{y}")
    dialog.bind("<Escape>",lambda e:dialog.destroy())
    dialog.after(150,dialog.focus_force)


def edit(app):
    index,item=app._selected()
    if item is None or app.busy:return
    track=infer_track(item);current=app.effective_tags(item)
    dialog=ctk.CTkToplevel(app);dialog.title("更正音乐资料");dialog.configure(fg_color=BG)
    dialog.geometry("560x700");dialog.resizable(False,False);dialog.transient(app);dialog.grab_set()
    frame=ctk.CTkFrame(dialog,fg_color=WHITE,corner_radius=16)
    frame.pack(fill="both",expand=True,padx=18,pady=18)
    label(frame,"更正音乐资料",size=22,bold=True).pack(anchor="w",padx=26,pady=(24,5))
    label(frame,item.path.name,size=12,color=MUTED,wraplength=450,justify="left").pack(anchor="w",padx=26,pady=(0,14))
    form=ctk.CTkScrollableFrame(frame,fg_color=WHITE,corner_radius=0)
    form.pack(fill="both",expand=True,padx=18,pady=(0,10));form.grid_columnconfigure(1,weight=1)
    fields=[("title","曲名"),("artist","音轨艺术家"),("tracknumber","轨序"),("discnumber","碟序"),("album","专辑名称"),
            ("albumartist","专辑艺术家"),("date","发行日期"),("genre","风格"),("label","唱片公司"),("catalognumber","目录编号")]
    variables={}
    album_keys={"album","albumartist","date","genre","label","catalognumber"}
    for row,(key,title) in enumerate(fields):
        variable=tk.StringVar(value=current.get(key,""));variables[key]=variable
        label(form,title,size=12,color=color('#8F859F')).grid(row=row,column=0,sticky="w",padx=(5,15),pady=6)
        entry=ctk.CTkEntry(form,textvariable=variable,height=35,corner_radius=8,fg_color=color('#F7F5FB'),border_color=LINE,font=(FONT,13))
        entry.grid(row=row,column=1,sticky="ew",pady=6,padx=(0,5))
        if item.kind!='audio' and key not in album_keys:entry.configure(state='disabled')
    label(frame,"专辑资料应用到同组音轨。曲名与轨序只更正当前音轨。",size=11,color=MUTED,wraplength=460,justify="left").pack(anchor="w",padx=26,pady=(0,15))
    actions=ctk.CTkFrame(frame,fg_color="transparent");actions.pack(fill="x",padx=26,pady=(0,24))
    def save():
        for field in ('tracknumber','discnumber'):
            value=variables[field].get().strip()
            if value and not number(value)[0]:
                messagebox.showerror("编号格式无效","轨序与碟序请填写 1 或 1/12 这样的编号。",parent=dialog);return
        app.overrides[track.edit_key]={k:v.get().strip() for k,v in variables.items() if k in album_keys and v.get().strip()}
        if item.kind=='audio':
            edits=item.edits|{k:v.get().strip() for k,v in variables.items() if k not in album_keys and v.get().strip()}
            app.items[index]=dataclasses.replace(item,tags=item.tags|edits,edits=edits)
        app._save_profile();app._show_items()
        if app.preview.exists(str(index)):app.preview.selection_set(str(index));app._selection()
        dialog.destroy()
    button(actions,"保存到预览",save,primary=True,width=136).pack(side="right")
    button(actions,"取消",dialog.destroy,width=80).pack(side="right",padx=10)
    center(app,dialog)


def cover(app):
    _,item=app._selected()
    if item is None or app.busy:return
    track=infer_track(item);tags=app.effective_tags(item)
    groups=list(dict.fromkeys(infer_track(i).edit_key for i in app._album_items(item)))
    dialog=ctk.CTkToplevel(app);dialog.title("更换专辑封面");dialog.configure(fg_color=BG)
    dialog.geometry("540x390");dialog.resizable(False,False);dialog.transient(app);dialog.grab_set()
    frame=ctk.CTkFrame(dialog,fg_color=WHITE,corner_radius=16)
    frame.pack(fill="both",expand=True,padx=18,pady=18)
    label(frame,"更换专辑封面",size=22,bold=True).pack(anchor="w",padx=25,pady=(24,5))
    label(frame,tags.get('album',''),size=13,color=MUTED,wraplength=450).pack(anchor="w",padx=25,pady=(0,18))
    def assign(picture):
        target=state_dir()/"Manual Covers"/(hashlib.sha256(picture.data).hexdigest()+(".jpg" if picture.mime=="image/jpeg" else ".png"))
        write_atomic(target,picture.data)
        for key in groups:
            app.cover_overrides[key]=str(target)
            if key in app.selections:app.selections[key].pop('cover',None)
        app._save_profile();app._selection();app.status.set("封面已加入预览，整理时内嵌到此专辑。")
    def local():
        path=filedialog.askopenfilename(parent=dialog,title="选择专辑封面",filetypes=[("封面图片","*.jpg *.jpeg *.png *.webp *.tif *.bmp"),("所有文件","*.*")])
        if path:
            try:assign(make_cover(Path(path).read_bytes(),path));dialog.destroy()
            except Exception as exc:messagebox.showerror("封面无法读取",str(exc),parent=dialog)
    button(frame,"选择本地图片",local,primary=True,width=160).pack(anchor="w",padx=25,pady=(0,20))
    label(frame,"或粘贴封面图片的直接链接",size=12,color=MUTED).pack(anchor="w",padx=25,pady=(0,7))
    url=tk.StringVar()
    ctk.CTkEntry(frame,textvariable=url,height=37,placeholder_text="https://…",fg_color=color('#F7F5FB'),border_color=LINE,corner_radius=8,font=(FONT,12)).pack(fill="x",padx=25)
    actions=ctk.CTkFrame(frame,fg_color="transparent");actions.pack(fill="x",padx=25,pady=18)
    def download():
        address=url.get().strip()
        if urllib.parse.urlsplit(address).scheme not in {'http','https'}:
            messagebox.showerror("链接无效","请输入 http 或 https 图片链接。",parent=dialog);return
        dialog.destroy()
        def perform():
            http=HTTP()
            try:
                data=http.fetch(address,app.cancel)
                if not data:raise ValueError("图片链接未返回内容")
                app._emit('manualcover',(groups,make_cover(data,address)))
            finally:http.close()
        app._start(perform,"正在下载并验证封面图片…")
    button(actions,"下载图片",download,width=110).pack(side="left",padx=(0,10))
    def online():dialog.destroy();app._open_lookup()
    button(actions,"从在线发行选用",online,width=156).pack(side="left")
    center(app,dialog)
