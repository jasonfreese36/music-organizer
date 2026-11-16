"""Paired light/dark colors and live accent recoloring, without rebuilding app state."""
import colorsys
import sys
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

MODES={"跟随系统":"system","浅色":"light","深色":"dark"}
ACCENTS={"鸢尾紫":"violet","海湾蓝":"blue","松石绿":"teal","蔷薇粉":"rose","琥珀橙":"amber"}
BASES={"violet":("#6556DC","#A89BFF"),"blue":("#3068CE","#8AB5FF"),"teal":("#187F77","#6BD1BD"),
       "rose":("#B34B77","#F1A0C2"),"amber":("#A56324","#F1BB7E")}
_accent="violet"


def blend(a,b,t):
    x=[int(a[i:i+2],16) for i in (1,3,5)];y=[int(b[i:i+2],16) for i in (1,3,5)]
    return "#"+"".join(f"{round(v*(1-t)+w*t):02X}" for v,w in zip(x,y))


def palette(key):
    a,d=BASES[key]
    return {
        "#6556DC":(a,d),"#5545C8":(blend(a,"#000000",.15),blend(d,"#FFFFFF",.12)),
        "#EEEBFC":(blend(a,"#FFFFFF",.89),blend(d,"#171A23",.79)),
        "#E5E0F6":(blend(a,"#FFFFFF",.83),blend(d,"#171A23",.88)),
        "#F5F3FA":("#F5F3FA","#272B36"),"#AEA4C2":("#A59BB6","#727889"),
        "#4F439C":(blend(a,"#000000",.18),d),
    }


def color(value):
    value=value.upper()
    if value in palette(_accent):return palette(_accent)[value]
    fixed={"#F5F6FA":"#171A23","#FFFFFF":"#222630","#202338":"#F0F1F6","#85899A":"#A9B0C1",
           "#E8EAF1":"#343A49","#2A8C71":"#7AD6B5","#FAFAFD":"#272C38",
           "#E7F4ED":"#203B33","#348467":"#8AD7B7","#FFF3DD":"#403322","#A57D35":"#E7C17D",
           "#FCEBEF":"#422B35","#AD5F73":"#EEA7B9"}
    if value in fixed:return (value,fixed[value])
    rgb=[int(value[i:i+2],16)/255 for i in (1,3,5)]
    h,l,s=colorsys.rgb_to_hls(*rgb)
    dark="#272B36" if l>.88 else "#3D4050" if l>.72 else "#B7B4C8" if l>.43 else "#D4D0E3"
    return (value,dark)


def resolved(value,mode=None):
    return value[1 if (mode or ctk.get_appearance_mode()).lower()=="dark" else 0] if isinstance(value,(tuple,list)) else value


def walk(root):
    yield root
    # CTkTabview hides its segmented control in its public winfo_children override.
    for child in tk.Misc.winfo_children(root):yield from walk(child)


def set_accent(key,root=None):
    global _accent
    key=key if key in BASES else "violet"
    old=palette(_accent);new=palette(key);_accent=key
    if root is None:return
    substitutions={tuple(v):new[k] for k,v in old.items() if v!=new[k]}
    options=("fg_color","hover_color","text_color","progress_color","border_color","button_color","button_hover_color",
             "selected_color","selected_hover_color","segmented_button_selected_color","segmented_button_selected_hover_color")
    for widget in list(walk(root)):
        if getattr(widget,"_fixed_accent",False):continue
        if not isinstance(widget,ctk.CTkBaseClass) and not isinstance(widget,(ctk.CTk,ctk.CTkToplevel)):continue
        for option in options:
            try:
                value=widget.cget(option)
                replacement=substitutions.get(tuple(value)) if isinstance(value,(tuple,list)) else None
                if replacement:widget.configure(**{option:replacement})
            except (tk.TclError,ValueError,AttributeError):pass
        for attr in ("_normal_fg","_disabled_fg"):
            value=getattr(widget,attr,None)
            if isinstance(value,(tuple,list)) and tuple(value) in substitutions:setattr(widget,attr,substitutions[tuple(value)])
    # Existing imports retain their semantic names; newly opened dialogs must use the new accent too.
    for name in ("ui","lookup_ui","dialogs","advanced_ui","rule_ui","platform_ui"):
        module=sys.modules.get(name)
        if module:
            for alias,hexvalue in (("ACCENT","#6556DC"),("HOVER","#5545C8"),("TINT","#EEEBFC")):
                if hasattr(module,alias):setattr(module,alias,color(hexvalue))


def refresh_native(app):
    if not hasattr(app,"preview"):return
    from ui import styles,placeholder
    styles(app)
    for widget in walk(app):
        if isinstance(widget,ttk.Treeview):widget.tag_configure("stripe",background=resolved(color("#FAFAFD")))
    app.log.configure(bg=resolved(color("#FCFBFE")),fg=resolved(color("#777086")),insertbackground=resolved(color("#202338")),selectbackground=resolved(color("#EEEBFC")))
    app.art_label.configure(bg=resolved(color("#FFFFFF")))
    app.placeholder_photo=placeholder(app)
    if not app.cover_photo:app.art_label.configure(image=app.placeholder_photo)
